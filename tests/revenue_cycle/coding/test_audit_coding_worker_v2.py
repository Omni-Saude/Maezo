"""Tests for AuditCodingWorker."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from healthcare_platform.revenue_cycle.coding.workers import AuditCodingWorker
from healthcare_platform.shared.domain.exceptions import (
    BpmnErrorException,
    CodingException,
)


@pytest.fixture
def worker_v2(mock_dmn_service):
    """Create AuditCodingWorker instance with mocked DMN service."""
    worker = AuditCodingWorker()
    worker.dmn_service = mock_dmn_service
    return worker


@pytest.fixture
def valid_task_variables():
    """Valid task variables for coding audit."""
    return {
        "encounterId": "enc_123",
        "validatedCid10": ["I21.0", "E11.9"],
        "validatedTuss": ["40101010", "40304361"],
        "rulesApplied": [],
        "codedBy": "coder_001",
        "tenantId": "hospital_a",
    }


@pytest.mark.asyncio
async def test_happy_path_high_score(worker_v2, mock_dmn_service, valid_task_variables):
    """Test happy path: all DMN evaluations return PROSSEGUIR, score >= 80."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR"}

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["auditScore"] == 100
    assert result["auditRecommendation"] == "approve"
    assert result["requiresRevision"] is False
    assert len(result["auditFindings"]) >= 0


@pytest.mark.asyncio
async def test_bloquear_deducts_points(worker_v2, mock_dmn_service, valid_task_variables):
    """Test BLOQUEAR result deducts points from score."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "BLOQUEAR", "acao": "Código sem especificidade", "rule_id": "AUD-SPEC-001"},
        {"resultado": "PROSSEGUIR"},
        {"resultado": "PROSSEGUIR"},
        {"resultado": "PROSSEGUIR"},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["auditScore"] < 100
    assert result["auditScore"] >= 60  # Not below fail threshold
    assert len(result["auditFindings"]) >= 1
    assert result["auditFindings"][0]["severity"] == "ERROR"


@pytest.mark.asyncio
async def test_score_below_threshold_fails(worker_v2, mock_dmn_service, valid_task_variables):
    """Test score < 60 raises AUDIT_FAILED exception."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "BLOQUEAR", "acao": "Specificidade insuficiente"},
        {"resultado": "BLOQUEAR", "acao": "Documentação inadequada"},
        {"resultado": "PROSSEGUIR"},
        {"resultado": "BLOQUEAR", "acao": "Unbundling detectado"},
    ]

    # Act & Assert
    with pytest.raises(BpmnErrorException) as exc_info:
        await worker_v2.execute(valid_task_variables)

    assert exc_info.value.error_code == "AUDIT_FAILED"
    assert "reprovada" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_revisar_recommendation(worker_v2, mock_dmn_service, valid_task_variables):
    """Test REVISAR results produce 'revise' recommendation."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "REVISAR", "acao": "Verificar especificidade"},
        {"resultado": "PROSSEGUIR"},
        {"resultado": "PROSSEGUIR"},
        {"resultado": "PROSSEGUIR"},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["auditScore"] >= 60
    assert result["auditScore"] < 80
    assert result["auditRecommendation"] == "revise"
    assert result["requiresRevision"] is True


@pytest.mark.asyncio
async def test_legacy_5_output_schema_compat(worker_v2, mock_dmn_service, valid_task_variables):
    """Test backward compatibility with old 5-output schema."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"Decisao": "Bloquear", "Justificativa": "Código inespecífico"},
        {"Decisao": "Prosseguir"},
        {"Decisao": "Revisar", "Justificativa": "DRG otimizável"},
        {"Decisao": "Prosseguir"},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["auditScore"] < 100
    assert len(result["auditFindings"]) >= 2


@pytest.mark.asyncio
async def test_invalid_input_missing_codes(worker_v2):
    """Test invalid input: missing required fields."""
    # Arrange
    invalid_vars = {
        "encounterId": "enc_123",
        "validatedCid10": [],  # Empty
        "validatedTuss": ["40101010"],
        "rulesApplied": [],
        "codedBy": "coder_001",
        "tenantId": "hospital_a",
    }

    # Act & Assert
    with pytest.raises(CodingException):
        await worker_v2.execute(invalid_vars)


@pytest.mark.asyncio
async def test_orphan_flag_check(worker_v2):
    """Test that worker is flagged as ORPHAN in docstring."""
    # Assert
    assert "ORPHAN" in worker_v2.__class__.__doc__
    assert "audit_quality/code_specificity" in worker_v2.__class__.__doc__
    assert "audit_quality/unbundling_detection" in worker_v2.__class__.__doc__


@pytest.mark.asyncio
async def test_prior_rule_violations(worker_v2, mock_dmn_service, valid_task_variables):
    """Test prior rule violations deduct points."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR"}
    valid_task_variables["rulesApplied"] = [
        {"passed": False, "rule_id": "RULE-QTY-001"},
        {"passed": False, "rule_id": "RULE-BND-001"},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["auditScore"] < 100
    assert any("Prior Rule Violations" in f["check_name"] for f in result["auditFindings"])


@pytest.mark.asyncio
async def test_dmn_fallback_orphan(worker_v2, mock_dmn_service, valid_task_variables):
    """Test DMN evaluation fallback when tables don't exist (ORPHAN)."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("Table not found")

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert - should complete with base score
    assert result["auditScore"] == 100
    assert result["auditRecommendation"] == "approve"
