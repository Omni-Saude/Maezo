"""Tests for SuggestTussWorkerV2 (thin DMN-federated worker)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.revenue_cycle.coding.workers import SuggestTussWorkerV2
from healthcare_platform.shared.domain.exceptions import CodingException
from tests.fixtures.workers import mock_dmn_service


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker with mocked DMN service."""
    return SuggestTussWorkerV2(dmn_service=mock_dmn_service)


async def test_suggest_tuss_happy_path(worker, mock_dmn_service):
    """Test TUSS suggestion with valid inputs."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        # cid10_correlation
        {"raw_suggestions": [{"code": "40101010", "name": "Consulta médica", "confidence": 0.85}]},
        # format_validation
        {"validated_tuss": [{"code": "40101010", "name": "Consulta médica", "confidence": 0.85}]},
    ]

    task_vars = {
        "extracted_procedures": [{"code": "CONSULT", "display": "Medical consultation"}],
        "suggested_cid10_codes": [{"code": "J18.9"}],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["tuss_count"] == 1
    assert len(result["suggested_tuss_codes"]) == 1
    assert result["suggested_tuss_codes"][0]["code"] == "40101010"
    assert mock_dmn_service.evaluate.call_count == 2


async def test_suggest_tuss_empty_input_raises_error(worker):
    """Test that empty procedures and CID-10 raises CodingException."""
    # Arrange
    task_vars = {
        "extracted_procedures": [],
        "suggested_cid10_codes": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act & Assert
    with pytest.raises(CodingException) as exc:
        await worker.execute(task_vars)
    assert "insuficientes" in str(exc.value).lower()


async def test_suggest_tuss_dmn_fallback(worker, mock_dmn_service):
    """Test graceful DMN fallback when tables don't exist."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("DMN table not found")

    task_vars = {
        "extracted_procedures": [{"code": "ECG", "display": "Electrocardiogram"}],
        "suggested_cid10_codes": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert - should handle gracefully with empty results
    assert result["tuss_count"] == 0
    assert result["suggested_tuss_codes"] == []


async def test_suggest_tuss_cid10_correlation(worker, mock_dmn_service):
    """Test TUSS suggestion correlated with CID-10 codes."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "raw_suggestions": [
                {"code": "40801020", "name": "Radiografia de tórax", "confidence": 0.85},
                {"code": "40304361", "name": "Hemograma completo", "confidence": 0.80},
            ]
        },
        {
            "validated_tuss": [
                {"code": "40801020", "name": "Radiografia de tórax", "confidence": 0.85},
                {"code": "40304361", "name": "Hemograma completo", "confidence": 0.80},
            ]
        },
    ]

    task_vars = {
        "extracted_procedures": [],
        "suggested_cid10_codes": [{"code": "J18.9", "description": "Pneumonia"}],
        "encounter_class": "internacao",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["tuss_count"] == 2
    assert any(t["code"] == "40801020" for t in result["suggested_tuss_codes"])


async def test_suggest_tuss_format_validation_filters_invalid(worker, mock_dmn_service):
    """Test that format validation filters out invalid TUSS codes."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "raw_suggestions": [
                {"code": "40101010", "name": "Valid", "confidence": 0.85},
                {"code": "INVALID", "name": "Invalid", "confidence": 0.70},
            ]
        },
        {"validated_tuss": [{"code": "40101010", "name": "Valid", "confidence": 0.85}]},
    ]

    task_vars = {
        "extracted_procedures": [{"code": "CONSULT", "display": "Consultation"}],
        "suggested_cid10_codes": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["tuss_count"] == 1
    assert result["suggested_tuss_codes"][0]["code"] == "40101010"


async def test_suggest_tuss_multiple_procedures(worker, mock_dmn_service):
    """Test TUSS suggestion with multiple procedures."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "raw_suggestions": [
                {"code": "40101010", "name": "Consulta", "confidence": 0.85},
                {"code": "40101030", "name": "ECG", "confidence": 0.90},
            ]
        },
        {
            "validated_tuss": [
                {"code": "40101010", "name": "Consulta", "confidence": 0.85},
                {"code": "40101030", "name": "ECG", "confidence": 0.90},
            ]
        },
    ]

    task_vars = {
        "extracted_procedures": [
            {"code": "CONSULT", "display": "Consultation"},
            {"code": "ECG", "display": "Electrocardiogram"},
        ],
        "suggested_cid10_codes": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["tuss_count"] == 2


async def test_suggest_tuss_with_encounter_context(worker, mock_dmn_service):
    """Test TUSS suggestion respects encounter class context."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"raw_suggestions": [{"code": "31001010", "name": "Internação", "confidence": 0.75}]},
        {"validated_tuss": [{"code": "31001010", "name": "Internação", "confidence": 0.75}]},
    ]

    task_vars = {
        "extracted_procedures": [{"code": "ADMISSION", "display": "Hospital admission"}],
        "suggested_cid10_codes": [],
        "encounter_class": "internacao",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["tuss_count"] == 1
    assert "31001010" in result["suggested_tuss_codes"][0]["code"]
