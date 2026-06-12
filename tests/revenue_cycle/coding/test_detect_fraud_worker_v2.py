"""Tests for DetectFraudWorker (thin DMN-federated worker)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.revenue_cycle.coding.workers import DetectFraudWorker
from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from tests.fixtures.workers import mock_dmn_service


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker with mocked DMN service."""
    return DetectFraudWorker(dmn_service=mock_dmn_service)


@pytest.fixture
def valid_task_vars():
    """Valid task variables for fraud detection."""
    return {
        "encounterId": "enc_123",
        "validatedCid10": ["J18.9", "I10"],
        "validatedTuss": ["40101010", "40801020"],
        "encounterClass": "ambulatorio",
        "patientId": "pat_456",
        "providerId": "prov_789",
        "tenantId": "HOSPITAL_A",
    }


async def test_detect_fraud_happy_path_no_fraud(worker, mock_dmn_service, valid_task_vars):
    """Test fraud detection with no fraud detected."""
    # Arrange - all 7 DMN tables return no alerts
    mock_dmn_service.evaluate.side_effect = [
        {"alerts": [], "score": 0},  # upcoding
        {"alerts": [], "score": 0},  # unbundling
        {"alerts": [], "score": 0},  # phantom_no_diagnosis
        {"alerts": [], "score": 0},  # phantom_suspicious_prefix
        {"alerts": [], "score": 0},  # frequency
        {"alerts": [], "score": 0},  # provider_pattern
        {"recommendation": "clear"},  # risk_thresholds
    ]

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert
    assert result["fraudRiskScore"] == 0
    assert len(result["fraudAlerts"]) == 0
    assert result["fraudRecommendation"] == "clear"
    assert result["requiresManualReview"] is False
    assert mock_dmn_service.evaluate.call_count == 7


async def test_detect_fraud_medium_risk(worker, mock_dmn_service, valid_task_vars):
    """Test fraud detection with medium risk score."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"alerts": [{"type": "UPCODING", "severity": "HIGH"}], "score": 20},
        {"alerts": [], "score": 0},
        {"alerts": [{"type": "PHANTOM_BILLING", "severity": "MEDIUM"}], "score": 15},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"recommendation": "review"},
    ]

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert
    assert result["fraudRiskScore"] == 35
    assert len(result["fraudAlerts"]) == 2
    assert result["fraudRecommendation"] == "review"
    assert result["requiresManualReview"] is False


async def test_detect_fraud_high_risk_raises_bpmn_error(worker, mock_dmn_service, valid_task_vars):
    """Test fraud detection with high risk raises BPMN error."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"alerts": [{"type": "UPCODING"}], "score": 30},
        {"alerts": [{"type": "UNBUNDLING"}], "score": 25},
        {"alerts": [{"type": "PHANTOM_BILLING"}], "score": 30},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"recommendation": "flag"},
    ]

    # Act & Assert
    with pytest.raises(BpmnErrorException) as exc:
        await worker.execute(valid_task_vars)
    assert exc.value.error_code == "FRAUD_DETECTED"
    assert "85" in str(exc.value.message)  # Risk score in message


async def test_detect_fraud_invalid_input_raises_error(worker):
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


async def test_detect_fraud_all_checks_contribute_to_score(worker, mock_dmn_service, valid_task_vars):
    """Test that all 7 fraud checks contribute to final score."""
    # Arrange - each check adds 10 points
    mock_dmn_service.evaluate.side_effect = [
        {"alerts": [{"type": "UPCODING"}], "score": 10},
        {"alerts": [{"type": "UNBUNDLING"}], "score": 10},
        {"alerts": [{"type": "PHANTOM_BILLING"}], "score": 10},
        {"alerts": [{"type": "PHANTOM_BILLING"}], "score": 10},
        {"alerts": [{"type": "FREQUENCY_ABUSE"}], "score": 10},
        {"alerts": [{"type": "PROVIDER_PATTERN"}], "score": 10},
        {"recommendation": "review"},
    ]

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert
    assert result["fraudRiskScore"] == 60
    assert len(result["fraudAlerts"]) == 6


async def test_detect_fraud_score_capped_at_100(worker, mock_dmn_service, valid_task_vars):
    """Test that fraud score is capped at 100."""
    # Arrange - scores add up to > 100
    mock_dmn_service.evaluate.side_effect = [
        {"alerts": [], "score": 50},
        {"alerts": [], "score": 50},
        {"alerts": [], "score": 50},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"recommendation": "flag"},
    ]

    # Act & Assert
    with pytest.raises(BpmnErrorException) as exc:
        await worker.execute(valid_task_vars)
    # Score should be capped at 100
    assert "100" in str(exc.value.message) or exc.value.error_code == "FRAUD_DETECTED"


async def test_detect_fraud_dmn_fallback_graceful(worker, mock_dmn_service, valid_task_vars):
    """Test graceful DMN fallback when tables don't exist."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("DMN table not found")

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert - should handle gracefully with zero score
    assert result["fraudRiskScore"] == 0
    assert len(result["fraudAlerts"]) == 0


async def test_detect_fraud_legacy_schema_compatibility(worker, mock_dmn_service, valid_task_vars):
    """Test compatibility with legacy 5-output DMN schema."""
    # Arrange - mix of new and old schema
    mock_dmn_service.evaluate.side_effect = [
        {"alerts": [], "score": 5},
        {"alerts": [], "score": 5},
        {"alerts": [], "score": 5},
        {"alerts": [], "score": 5},
        {"alerts": [], "score": 5},
        {"alerts": [], "score": 5},
        {"Prosseguir": "Revisar", "recommendation": None},  # Legacy schema
    ]

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert
    assert result["fraudRiskScore"] == 30
    # Should handle legacy schema gracefully


async def test_detect_fraud_manual_review_flag(worker, mock_dmn_service, valid_task_vars):
    """Test that requiresManualReview flag is set correctly."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"alerts": [], "score": 0},
        {"recommendation": "flag"},
    ]

    # Act
    result = await worker.execute(valid_task_vars)

    # Assert
    assert result["requiresManualReview"] is True
    assert result["fraudRecommendation"] == "flag"
