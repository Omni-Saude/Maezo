"""Tests for FinalizeCodingWorkerV2 (thin DMN-federated worker)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.revenue_cycle.coding.workers import FinalizeCodingWorkerV2
from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from tests.fixtures.workers import mock_dmn_service


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker with mocked DMN service."""
    return FinalizeCodingWorkerV2(dmn_service=mock_dmn_service)


@pytest.fixture
def valid_task_vars():
    """Valid task variables for finalization."""
    return {
        "encounterId": "enc_123",
        "validatedCid10": ["J18.9", "I10"],
        "validatedTuss": ["40101010", "40801020"],
        "auditRecommendation": "approve",
        "auditScore": 95,
        "complexityScore": 75,
        "complexityLevel": "MODERATE",
        "fraudRecommendation": "clear",
        "codedBy": "coder_001",
        "tenantId": "HOSPITAL_A",
    }


async def test_finalize_coding_happy_path(worker, mock_dmn_service, valid_task_vars):
    """Test coding finalization with all gates passing."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "PROSSEGUIR"},  # audit_approval
        {"resultado": "PROSSEGUIR"},  # fraud_clearance
    ]

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert
    assert result["codingFinalized"] is True
    assert len(result["finalCid10"]) == 2
    assert len(result["finalTuss"]) == 2
    assert "codingSummary" in result
    assert result["codingSummary"]["status"] == "CODED"
    assert mock_dmn_service.evaluate.call_count == 2


async def test_finalize_coding_audit_not_approved(worker, mock_dmn_service, valid_task_vars):
    """Test BPMN error when audit is not approved."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {"resultado": "BLOQUEAR"}

    # Act & Assert
    with pytest.raises(BpmnErrorException) as exc:
        await worker.execute(valid_task_vars)
    assert exc.value.error_code == "CODING_NOT_APPROVED"


async def test_finalize_coding_fraud_blocked(worker, mock_dmn_service, valid_task_vars):
    """Test BPMN error when fraud blocks finalization."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "PROSSEGUIR"},  # audit passes
        {"resultado": "BLOQUEAR"},  # fraud blocks
    ]

    # Act & Assert
    with pytest.raises(BpmnErrorException) as exc:
        await worker.execute(valid_task_vars)
    assert exc.value.error_code == "FRAUD_BLOCK"


async def test_finalize_coding_legacy_schema_prosseguir(worker, mock_dmn_service, valid_task_vars):
    """Test legacy 5-output schema (Prosseguir instead of PROSSEGUIR)."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"Prosseguir": "Prosseguir"},  # Legacy schema
        {"Prosseguir": "Prosseguir"},
    ]

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert
    assert result["codingFinalized"] is True


async def test_finalize_coding_legacy_schema_bloquear(worker, mock_dmn_service, valid_task_vars):
    """Test legacy 5-output schema (Bloquear instead of BLOQUEAR)."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {"Prosseguir": "Bloquear"}

    # Act & Assert
    with pytest.raises(BpmnErrorException):
        await worker.execute(valid_task_vars)


async def test_finalize_coding_invalid_input_raises_error(worker):
    """Test that invalid input raises CodingException."""
    # Arrange
    task_vars = {
        "encounterId": "",  # Invalid: empty string
        "validatedCid10": [],
        "validatedTuss": [],
    }

    # Act & Assert
    with pytest.raises(CodingException) as exc:
        await worker.execute(task_vars)
    assert "inválidos" in str(exc.value).lower()


async def test_finalize_coding_dmn_fallback(worker, mock_dmn_service, valid_task_vars):
    """Test graceful DMN fallback when tables don't exist."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("DMN table not found")

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert - should proceed with empty DMN results
    assert result["codingFinalized"] is True


async def test_finalize_coding_summary_structure(worker, mock_dmn_service, valid_task_vars):
    """Test coding summary contains all required fields."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "PROSSEGUIR"},
        {"resultado": "PROSSEGUIR"},
    ]

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert
    summary = result["codingSummary"]
    assert summary["encounterId"] == "enc_123"
    assert len(summary["cid10Codes"]) == 2
    assert len(summary["tussCodes"]) == 2
    assert summary["auditRecommendation"] == "approve"
    assert summary["auditScore"] == 95
    assert summary["complexityScore"] == 75
    assert summary["complexityLevel"] == "MODERATE"
    assert summary["fraudRecommendation"] == "clear"
    assert summary["codedBy"] == "coder_001"
    assert "finalizedAt" in summary
    assert summary["status"] == "CODED"


async def test_finalize_coding_timestamp_format(worker, mock_dmn_service, valid_task_vars):
    """Test that timestamp is in ISO-8601 format."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "PROSSEGUIR"},
        {"resultado": "PROSSEGUIR"},
    ]

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert
    timestamp = result["codingTimestamp"]
    assert "T" in timestamp  # ISO format includes T separator
    assert timestamp.endswith(("Z", "+00:00"))  # UTC timezone
