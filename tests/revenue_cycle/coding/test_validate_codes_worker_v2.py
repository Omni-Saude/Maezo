"""Tests for ValidateCodesWorker (thin DMN-federated worker)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.revenue_cycle.coding.workers import ValidateCodesWorker
from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from tests.fixtures.workers import mock_dmn_service


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker with mocked DMN service."""
    return ValidateCodesWorker(dmn_service=mock_dmn_service)


async def test_validate_codes_happy_path(worker, mock_dmn_service):
    """Test code validation with all valid codes."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"validated_cid10": [{"code": "J18.9"}], "errors": []},  # cid10_format
        {"errors": []},  # cid10_incompatibility
        {"format_valid_tuss": [{"code": "40101010"}], "errors": []},  # tuss_format
        {"validated_tuss": [{"code": "40101010"}], "errors": []},  # tuss_coverage
        {"errors": []},  # tuss_cid10_requirements
    ]

    task_vars = {
        "suggested_cid10_codes": [{"code": "J18.9", "description": "Pneumonia"}],
        "suggested_tuss_codes": [{"code": "40101010", "name": "Consulta"}],
        "encounter_id": "enc_123",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["all_valid"] is True
    assert len(result["validated_cid10"]) == 1
    assert len(result["validated_tuss"]) == 1
    assert len(result["validation_errors"]) == 0
    assert mock_dmn_service.evaluate.call_count == 5


async def test_validate_codes_empty_input_raises_error(worker):
    """Test that empty code lists raises CodingException."""
    # Arrange
    task_vars = {
        "suggested_cid10_codes": [],
        "suggested_tuss_codes": [],
        "encounter_id": "enc_123",
        "tenant_id": "HOSPITAL_A",
    }

    # Act & Assert
    with pytest.raises(CodingException) as exc:
        await worker.execute(task_vars)
    assert "nenhum código" in str(exc.value).lower()


async def test_validate_codes_cid10_format_errors(worker, mock_dmn_service):
    """Test CID-10 format validation errors."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "validated_cid10": [],
            "errors": [{"code": "INVALID", "code_type": "CID10", "error_type": "FORMAT"}],
        },
        {"errors": []},
        {"format_valid_tuss": [{"code": "40101010"}], "errors": []},
        {"validated_tuss": [{"code": "40101010"}], "errors": []},
        {"errors": []},
    ]

    task_vars = {
        "suggested_cid10_codes": [{"code": "INVALID"}],
        "suggested_tuss_codes": [{"code": "40101010"}],
        "encounter_id": "enc_123",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["all_valid"] is False
    assert len(result["validation_errors"]) == 1
    assert result["validation_errors"][0]["error_type"] == "FORMAT"


async def test_validate_codes_all_cid10_invalid_raises_bpmn_error(worker, mock_dmn_service):
    """Test that all invalid CID-10 codes raises BPMN error."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "validated_cid10": [],
            "errors": [{"code": "BAD", "code_type": "CID10", "error_type": "FORMAT"}],
        },
        {"errors": []},
        {"format_valid_tuss": [], "errors": []},
        {"validated_tuss": [], "errors": []},
        {"errors": []},
    ]

    task_vars = {
        "suggested_cid10_codes": [{"code": "BAD"}],
        "suggested_tuss_codes": [],
        "encounter_id": "enc_123",
        "tenant_id": "HOSPITAL_A",
    }

    # Act & Assert
    with pytest.raises(BpmnErrorException) as exc:
        await worker.execute(task_vars)
    assert exc.value.error_code == "INVALID_CID10_CODE"


async def test_validate_codes_all_tuss_invalid_raises_bpmn_error(worker, mock_dmn_service):
    """Test that all invalid TUSS codes raises BPMN error."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"validated_cid10": [], "errors": []},
        {"errors": []},
        {
            "format_valid_tuss": [],
            "errors": [{"code": "BAD", "code_type": "TUSS", "error_type": "FORMAT"}],
        },
        {"validated_tuss": [], "errors": []},
        {"errors": []},
    ]

    task_vars = {
        "suggested_cid10_codes": [],
        "suggested_tuss_codes": [{"code": "BAD"}],
        "encounter_id": "enc_123",
        "tenant_id": "HOSPITAL_A",
    }

    # Act & Assert
    with pytest.raises(BpmnErrorException) as exc:
        await worker.execute(task_vars)
    assert exc.value.error_code == "INVALID_TUSS_CODE"


async def test_validate_codes_incompatible_cid10(worker, mock_dmn_service):
    """Test CID-10 incompatibility check."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"validated_cid10": [{"code": "E10"}, {"code": "E11"}], "errors": []},
        {
            "errors": [
                {"code": "E10/E11", "code_type": "CID10", "error_type": "INCOMPATIBLE"}
            ]
        },
        {"format_valid_tuss": [], "errors": []},
        {"validated_tuss": [], "errors": []},
        {"errors": []},
    ]

    task_vars = {
        "suggested_cid10_codes": [{"code": "E10"}, {"code": "E11"}],
        "suggested_tuss_codes": [],
        "encounter_id": "enc_123",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["all_valid"] is False
    assert len(result["validation_errors"]) == 1
    assert "E10/E11" in result["validation_errors"][0]["code"]


async def test_validate_codes_dmn_fallback(worker, mock_dmn_service):
    """Test graceful DMN fallback when tables don't exist."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("DMN table not found")

    task_vars = {
        "suggested_cid10_codes": [{"code": "J18.9"}],
        "suggested_tuss_codes": [{"code": "40101010"}],
        "encounter_id": "enc_123",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert - should handle gracefully with empty results
    assert result["all_valid"] is True  # No errors means valid
    assert len(result["validated_cid10"]) == 0
    assert len(result["validated_tuss"]) == 0


async def test_validate_codes_tuss_cid10_requirements(worker, mock_dmn_service):
    """Test TUSS-CID10 requirement check."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"validated_cid10": [{"code": "J18.9"}], "errors": []},
        {"errors": []},
        {"format_valid_tuss": [{"code": "31003036"}], "errors": []},
        {"validated_tuss": [{"code": "31003036"}], "errors": []},
        {
            "errors": [
                {"code": "31003036", "code_type": "TUSS", "error_type": "MISSING_DIAGNOSIS"}
            ]
        },
    ]

    task_vars = {
        "suggested_cid10_codes": [{"code": "J18.9"}],
        "suggested_tuss_codes": [{"code": "31003036"}],  # Appendectomy requires K35
        "encounter_id": "enc_123",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["all_valid"] is False
    assert len(result["validation_errors"]) == 1
    assert result["validation_errors"][0]["error_type"] == "MISSING_DIAGNOSIS"
