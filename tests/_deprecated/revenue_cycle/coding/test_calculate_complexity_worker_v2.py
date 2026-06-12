"""Tests for CalculateComplexityWorkerV2."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from healthcare_platform.revenue_cycle.coding.workers import CalculateComplexityWorkerV2
from healthcare_platform.shared.domain.exceptions import CodingException


@pytest.fixture
def worker_v2(mock_dmn_service):
    """Create CalculateComplexityWorkerV2 instance with mocked DMN service."""
    worker = CalculateComplexityWorkerV2()
    worker.dmn_service = mock_dmn_service
    return worker


@pytest.fixture
def valid_task_variables():
    """Valid task variables for complexity calculation."""
    return {
        "encounterId": "enc_123",
        "validatedCid10": ["I21.0", "E11.9"],
        "validatedTuss": ["40101010", "40304361"],
        "encounterClass": "ambulatorio",
        "patientAge": 65,
        "comorbidities": ["I50.0"],
        "tenantId": "hospital_a",
    }


@pytest.mark.asyncio
async def test_happy_path_low_complexity(worker_v2, mock_dmn_service, valid_task_variables):
    """Test happy path: DMN returns values resulting in LOW complexity."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"contribution": 1.0},  # diagnosis_count
        {"age_factor": 0.8},    # age_factors
        {"weight": 0.5},        # encounter_class_weight
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["complexityScore"] == 2  # 1.0 + 0.8 + 0.5 = 2.3 -> 2
    assert result["complexityLevel"] == "LOW"
    assert result["suggestedDRG"] == "DRG-001"
    assert len(result["complexityFactors"]) == 3


@pytest.mark.asyncio
async def test_high_complexity_elderly_patient(worker_v2, mock_dmn_service, valid_task_variables):
    """Test HIGH complexity for elderly patient with multiple diagnoses."""
    # Arrange
    valid_task_variables["patientAge"] = 82
    valid_task_variables["validatedCid10"] = ["I21.0", "E11.9", "I50.0", "J44.0"]
    mock_dmn_service.evaluate.side_effect = [
        {"contribution": 2.0},  # diagnosis_count
        {"age_factor": 1.6},    # age_factors (elderly)
        {"weight": 0.5},        # encounter_class_weight
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["complexityScore"] >= 4
    assert result["complexityLevel"] in ("MODERATE", "HIGH")


@pytest.mark.asyncio
async def test_very_high_complexity_internacao(worker_v2, mock_dmn_service, valid_task_variables):
    """Test VERY_HIGH complexity for inpatient with high burden."""
    # Arrange
    valid_task_variables["encounterClass"] = "internacao"
    valid_task_variables["validatedCid10"] = ["I21.0", "I50.0", "N18.0", "E11.0"]
    valid_task_variables["comorbidities"] = ["C77.0", "B20.0"]
    mock_dmn_service.evaluate.side_effect = [
        {"contribution": 3.0},  # diagnosis_count
        {"age_factor": 1.3},    # age_factors
        {"weight": 2.0},        # encounter_class_weight (internacao)
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["complexityScore"] >= 6
    assert result["complexityLevel"] in ("HIGH", "VERY_HIGH")
    assert result["suggestedDRG"] in ("DRG-003", "DRG-004")


@pytest.mark.asyncio
async def test_invalid_input_missing_encounter_id(worker_v2):
    """Test invalid input: missing encounterId."""
    # Arrange
    invalid_vars = {
        "encounterId": "",  # Empty
        "validatedCid10": ["I21.0"],
        "validatedTuss": ["40101010"],
        "encounterClass": "ambulatorio",
        "patientAge": 50,
        "tenantId": "hospital_a",
    }

    # Act & Assert
    with pytest.raises(CodingException) as exc_info:
        await worker_v2.execute(invalid_vars)

    assert exc_info.value.bpmn_error_code == "CODING_ERROR"


@pytest.mark.asyncio
async def test_invalid_input_missing_encounter_class(worker_v2):
    """Test invalid input: missing encounterClass."""
    # Arrange
    invalid_vars = {
        "encounterId": "enc_123",
        "validatedCid10": ["I21.0"],
        "validatedTuss": ["40101010"],
        "encounterClass": "",  # Empty
        "patientAge": 50,
        "tenantId": "hospital_a",
    }

    # Act & Assert
    with pytest.raises(CodingException):
        await worker_v2.execute(invalid_vars)


@pytest.mark.asyncio
async def test_dmn_fallback_uses_defaults(worker_v2, mock_dmn_service, valid_task_variables):
    """Test DMN fallback when tables don't exist uses default calculations."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("Table not found")

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert - should complete with default fallback logic
    assert result["complexityScore"] >= 1
    assert result["complexityLevel"] in ("LOW", "MODERATE", "HIGH", "VERY_HIGH")
    assert result["suggestedDRG"].startswith("DRG-")


@pytest.mark.asyncio
async def test_all_complexity_levels(worker_v2, mock_dmn_service, valid_task_variables):
    """Test all complexity level thresholds."""
    # Test LOW (score <= 3)
    mock_dmn_service.evaluate.side_effect = [
        {"contribution": 0.5}, {"age_factor": 0.8}, {"weight": 0.5}
    ]
    result = await worker_v2.execute(valid_task_variables)
    assert result["complexityLevel"] == "LOW"

    # Test MODERATE (4-6)
    mock_dmn_service.evaluate.side_effect = [
        {"contribution": 2.0}, {"age_factor": 1.2}, {"weight": 1.5}
    ]
    result = await worker_v2.execute(valid_task_variables)
    assert result["complexityLevel"] == "MODERATE"

    # Test HIGH (7-9)
    mock_dmn_service.evaluate.side_effect = [
        {"contribution": 3.0}, {"age_factor": 1.5}, {"weight": 2.0}
    ]
    result = await worker_v2.execute(valid_task_variables)
    assert result["complexityLevel"] in ("HIGH", "VERY_HIGH")


@pytest.mark.asyncio
async def test_complexity_factors_structure(worker_v2, mock_dmn_service, valid_task_variables):
    """Test complexity factors have correct structure."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"contribution": 1.0},
        {"age_factor": 1.0},
        {"weight": 0.5},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert len(result["complexityFactors"]) == 3
    for factor in result["complexityFactors"]:
        assert "factor" in factor
        assert "weight" in factor
        assert "contribution" in factor
        assert isinstance(factor["contribution"], (int, float))
