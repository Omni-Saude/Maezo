"""Tests for ApplyCodingRulesWorkerV2."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from healthcare_platform.revenue_cycle.coding.workers import ApplyCodingRulesWorkerV2
from healthcare_platform.shared.domain.exceptions import (
    BpmnErrorException,
    CodingException,
)


@pytest.fixture
def worker_v2(mock_dmn_service):
    """Create ApplyCodingRulesWorkerV2 instance with mocked DMN service."""
    worker = ApplyCodingRulesWorkerV2()
    worker.dmn_service = mock_dmn_service
    return worker


@pytest.fixture
def valid_task_variables():
    """Valid task variables for coding rules."""
    return {
        "validatedCid10": ["I21.0", "E11.9"],
        "validatedTuss": ["40101010", "40304361"],
        "encounterClass": "ambulatorio",
        "encounterId": "enc_123",
        "tenantId": "hospital_a",
    }


@pytest.mark.asyncio
async def test_happy_path_prosseguir(worker_v2, mock_dmn_service, valid_task_variables):
    """Test happy path: all DMN evaluations return PROSSEGUIR."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR"}

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["rulesPassed"] is True
    assert len(result["ruleViolations"]) == 0
    assert len(result["modifiersRequired"]) == 0
    assert mock_dmn_service.evaluate.call_count == 4  # 4 DMN tables


@pytest.mark.asyncio
async def test_bloquear_raises_exception(worker_v2, mock_dmn_service, valid_task_variables):
    """Test BLOQUEAR result raises BpmnErrorException."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "Quantidade de procedimentos excede o limite",
        "rule_id": "RULE-QTY-001",
    }

    # Act & Assert
    with pytest.raises(BpmnErrorException) as exc_info:
        await worker_v2.execute(valid_task_variables)

    assert exc_info.value.error_code == "CODING_RULE_VIOLATION"
    assert "erro(s) encontrado(s)" in exc_info.value.message


@pytest.mark.asyncio
async def test_revisar_warning(worker_v2, mock_dmn_service, valid_task_variables):
    """Test REVISAR result adds warning violation but passes."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "PROSSEGUIR"},
        {"resultado": "PROSSEGUIR"},
        {"resultado": "REVISAR", "acao": "Modificador requerido", "rule_id": "RULE-MOD-001"},
        {"resultado": "PROSSEGUIR"},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["rulesPassed"] is True  # No ERROR severity
    assert len(result["ruleViolations"]) == 1
    assert result["ruleViolations"][0]["severity"] == "WARNING"
    assert result["ruleViolations"][0]["rule_id"] == "RULE-MOD-001"


@pytest.mark.asyncio
async def test_legacy_5_output_schema_compat(worker_v2, mock_dmn_service, valid_task_variables):
    """Test backward compatibility with old 5-output schema (Prosseguir/Bloquear/Revisar)."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"Decisao": "Prosseguir"},
        {"Decisao": "Bloquear", "Justificativa": "Bundling violation", "rule_id": "LEGACY-BND"},
        {"Decisao": "Prosseguir"},
        {"Decisao": "Prosseguir"},
    ]

    # Act & Assert
    with pytest.raises(BpmnErrorException):
        await worker_v2.execute(valid_task_variables)


@pytest.mark.asyncio
async def test_invalid_input_missing_codes(worker_v2):
    """Test invalid input: missing CID-10 or TUSS codes."""
    # Arrange
    invalid_vars = {
        "validatedCid10": [],
        "validatedTuss": ["40101010"],
        "encounterClass": "ambulatorio",
        "encounterId": "enc_123",
        "tenantId": "hospital_a",
    }

    # Act & Assert
    with pytest.raises(CodingException) as exc_info:
        await worker_v2.execute(invalid_vars)

    assert exc_info.value.bpmn_error_code == "CODING_ERROR"


@pytest.mark.asyncio
async def test_orphan_flag_check(worker_v2):
    """Test that worker is flagged as ORPHAN in docstring."""
    # Assert
    assert "ORPHAN" in worker_v2.__class__.__doc__
    assert "coding_rules/quantity_limits" in worker_v2.__class__.__doc__
    assert "coding_rules/bundling_validation" in worker_v2.__class__.__doc__


@pytest.mark.asyncio
async def test_dmn_fallback_orphan(worker_v2, mock_dmn_service, valid_task_variables):
    """Test DMN evaluation fallback when tables don't exist (ORPHAN)."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("Table not found")

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert - should complete without errors (fallback to empty results)
    assert result["rulesPassed"] is True
    assert len(result["ruleViolations"]) == 0


@pytest.mark.asyncio
async def test_modifier_extraction(worker_v2, mock_dmn_service, valid_task_variables):
    """Test modifier extraction from DMN results."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "PROSSEGUIR"},
        {"resultado": "PROSSEGUIR"},
        {
            "resultado": "REVISAR",
            "acao": "Procedimento requer modificador -51",
            "rule_id": "RULE-MOD-001",
        },
        {"resultado": "PROSSEGUIR"},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert len(result["modifiersRequired"]) == 1
    assert "modificador -51" in result["modifiersRequired"][0].lower()
