"""Tests for ExtractClinicalDataWorkerV2."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from healthcare_platform.revenue_cycle.coding.workers import ExtractClinicalDataWorkerV2
from healthcare_platform.shared.domain.exceptions import (
    BpmnErrorException,
    CodingException,
    ExternalServiceException,
)


@pytest.fixture
def mock_fhir_client():
    """Mock FHIR client."""
    mock = MagicMock()
    mock.get_encounter = AsyncMock()
    mock.search = AsyncMock()
    return mock


@pytest.fixture
def worker_v2(mock_fhir_client, mock_dmn_service):
    """Create ExtractClinicalDataWorkerV2 instance with mocked dependencies."""
    worker = ExtractClinicalDataWorkerV2(fhir_client=mock_fhir_client)
    worker.dmn_service = mock_dmn_service
    return worker


@pytest.fixture
def valid_task_variables():
    """Valid task variables for clinical data extraction."""
    return {
        "encounter_id": "enc_123",
        "tenant_id": "hospital_a",
    }


@pytest.fixture
def mock_encounter():
    """Mock FHIR encounter resource."""
    return {
        "resourceType": "Encounter",
        "id": "enc_123",
        "status": "in-progress",
        "class": {"code": "AMB"},
        "diagnosis": [
            {
                "rank": 1,
                "condition": {"reference": "Condition/cond_123"},
            }
        ],
    }


@pytest.fixture
def mock_conditions():
    """Mock FHIR Condition resources."""
    return [
        {
            "resourceType": "Condition",
            "id": "cond_123",
            "code": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/sid/icd-10",
                        "code": "I21.0",
                        "display": "Infarto agudo do miocárdio",
                    }
                ]
            },
            "clinicalStatus": {"coding": [{"code": "active"}]},
        }
    ]


@pytest.mark.asyncio
async def test_happy_path_extract_all_data(
    worker_v2, mock_fhir_client, mock_dmn_service, valid_task_variables, mock_encounter, mock_conditions
):
    """Test happy path: successfully extract all clinical data."""
    # Arrange
    mock_fhir_client.get_encounter.return_value = mock_encounter
    mock_fhir_client.search.side_effect = [
        mock_conditions,  # Conditions
        [],               # Procedures
        [],               # DocumentReferences
        [],               # MedicationRequests
    ]
    mock_dmn_service.evaluate.side_effect = [
        {"encounter_class": "ambulatorio"},
        {"primary_code": "I21.0"},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["encounter_class"] == "ambulatorio"
    assert result["primary_diagnosis"] == "I21.0"
    assert len(result["extracted_diagnoses"]) == 1
    assert result["extracted_diagnoses"][0]["code"] == "I21.0"


@pytest.mark.asyncio
async def test_encounter_not_found_raises_bpmn_error(
    worker_v2, mock_fhir_client, valid_task_variables
):
    """Test encounter not found raises ENCOUNTER_NOT_FOUND BPMN error."""
    # Arrange
    mock_fhir_client.get_encounter.side_effect = ExternalServiceException(
        "Not found", service_name="fhir", operation="get_encounter", status_code=404
    )

    # Act & Assert
    with pytest.raises(BpmnErrorException) as exc_info:
        await worker_v2.execute(valid_task_variables)

    assert exc_info.value.error_code == "ENCOUNTER_NOT_FOUND"
    assert "não encontrado" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_fhir_service_error_raises_external_exception(
    worker_v2, mock_fhir_client, valid_task_variables
):
    """Test FHIR service error raises ExternalServiceException."""
    # Arrange
    mock_fhir_client.get_encounter.side_effect = ExternalServiceException(
        "Service unavailable", service_name="fhir", operation="get_encounter", status_code=503
    )

    # Act & Assert
    with pytest.raises(ExternalServiceException):
        await worker_v2.execute(valid_task_variables)


@pytest.mark.asyncio
async def test_invalid_input_missing_encounter_id(worker_v2):
    """Test invalid input: missing encounter_id."""
    # Arrange
    invalid_vars = {
        "encounter_id": "",  # Empty
        "tenant_id": "hospital_a",
    }

    # Act & Assert
    with pytest.raises(CodingException) as exc_info:
        await worker_v2.execute(invalid_vars)

    assert exc_info.value.bpmn_error_code == "CODING_ERROR"


@pytest.mark.asyncio
async def test_dmn_encounter_class_mapping(
    worker_v2, mock_fhir_client, mock_dmn_service, valid_task_variables, mock_encounter
):
    """Test DMN encounter class mapping is used."""
    # Arrange
    mock_encounter["class"]["code"] = "IMP"  # Inpatient
    mock_fhir_client.get_encounter.return_value = mock_encounter
    mock_fhir_client.search.return_value = []
    mock_dmn_service.evaluate.side_effect = [
        {"encounter_class": "internacao"},  # DMN maps IMP to internacao
        {"primary_code": ""},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["encounter_class"] == "internacao"
    assert mock_dmn_service.evaluate.call_count == 2


@pytest.mark.asyncio
async def test_dmn_primary_diagnosis_priority(
    worker_v2, mock_fhir_client, mock_dmn_service, valid_task_variables, mock_encounter, mock_conditions
):
    """Test DMN determines primary diagnosis priority."""
    # Arrange
    mock_fhir_client.get_encounter.return_value = mock_encounter
    mock_fhir_client.search.side_effect = [mock_conditions, [], [], []]
    mock_dmn_service.evaluate.side_effect = [
        {"encounter_class": "ambulatorio"},
        {"primary_code": "I21.0"},  # DMN selects I21.0
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["primary_diagnosis"] == "I21.0"


@pytest.mark.asyncio
async def test_fallback_primary_diagnosis(
    worker_v2, mock_fhir_client, mock_dmn_service, valid_task_variables, mock_encounter, mock_conditions
):
    """Test fallback to first diagnosis when DMN doesn't return primary."""
    # Arrange
    mock_fhir_client.get_encounter.return_value = mock_encounter
    mock_fhir_client.search.side_effect = [mock_conditions, [], [], []]
    mock_dmn_service.evaluate.side_effect = [
        {"encounter_class": "ambulatorio"},
        {"primary_code": ""},  # DMN doesn't return primary
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert - fallback to first diagnosis
    assert result["primary_diagnosis"] == "I21.0"


@pytest.mark.asyncio
async def test_dmn_fallback_uses_defaults(
    worker_v2, mock_fhir_client, mock_dmn_service, valid_task_variables, mock_encounter
):
    """Test DMN fallback when tables don't exist uses defaults."""
    # Arrange
    mock_fhir_client.get_encounter.return_value = mock_encounter
    mock_fhir_client.search.return_value = []
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("Table not found")

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert - should use defaults
    assert result["encounter_class"] == "ambulatorio"  # Default
    assert result["primary_diagnosis"] == ""


@pytest.mark.asyncio
async def test_extract_procedures_and_medications(
    worker_v2, mock_fhir_client, mock_dmn_service, valid_task_variables, mock_encounter
):
    """Test extraction of procedures and medications."""
    # Arrange
    mock_procedures = [
        {
            "resourceType": "Procedure",
            "code": {"coding": [{"code": "40101010", "display": "Consulta"}]},
            "status": "completed",
        }
    ]
    mock_medications = [
        {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [{"code": "MED123", "display": "Aspirina"}]
            },
            "status": "active",
        }
    ]

    mock_fhir_client.get_encounter.return_value = mock_encounter
    mock_fhir_client.search.side_effect = [
        [],                # Conditions
        mock_procedures,   # Procedures
        [],                # DocumentReferences
        mock_medications,  # MedicationRequests
    ]
    mock_dmn_service.evaluate.side_effect = [
        {"encounter_class": "ambulatorio"},
        {"primary_code": ""},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert len(result["extracted_procedures"]) == 1
    assert result["extracted_procedures"][0]["code"] == "40101010"
    assert len(result["medications"]) == 1
    assert result["medications"][0]["code"] == "MED123"


@pytest.mark.asyncio
async def test_fhir_search_failures_graceful_fallback(
    worker_v2, mock_fhir_client, mock_dmn_service, valid_task_variables, mock_encounter
):
    """Test FHIR search failures don't crash worker, return empty lists."""
    # Arrange
    mock_fhir_client.get_encounter.return_value = mock_encounter
    mock_fhir_client.search.side_effect = ExternalServiceException(
        "Search failed", service_name="fhir", operation="search"
    )
    mock_dmn_service.evaluate.side_effect = [
        {"encounter_class": "ambulatorio"},
        {"primary_code": ""},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert - should complete with empty data
    assert len(result["extracted_diagnoses"]) == 0
    assert len(result["extracted_procedures"]) == 0
    assert result["clinical_notes"] == ""
