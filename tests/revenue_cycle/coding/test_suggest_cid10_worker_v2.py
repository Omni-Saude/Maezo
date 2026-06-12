"""Tests for SuggestCid10Worker (thin DMN-federated worker)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.revenue_cycle.coding.workers import SuggestCid10Worker
from healthcare_platform.shared.domain.exceptions import CodingException
from tests.fixtures.workers import mock_dmn_service


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker with mocked DMN service."""
    return SuggestCid10Worker(dmn_service=mock_dmn_service)


async def test_suggest_cid10_happy_path(worker, mock_dmn_service):
    """Test CID-10 suggestion with valid inputs."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        # confidence_boosting
        {"suggestions": [{"code": "J18.9", "description": "Pneumonia", "confidence": 0.85}]},
        # format_validation
        {"valid_suggestions": [{"code": "J18.9", "description": "Pneumonia", "confidence": 0.85}]},
    ]

    task_vars = {
        "clinical_notes": "Patient presents with pneumonia symptoms",
        "extracted_diagnoses": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["cid10_count"] == 1
    assert result["primary_cid10"] == "J18.9"
    assert len(result["suggested_cid10_codes"]) == 1
    assert mock_dmn_service.evaluate.call_count == 2


async def test_suggest_cid10_empty_input_raises_error(worker):
    """Test that empty clinical notes and diagnoses raises CodingException."""
    # Arrange
    task_vars = {
        "clinical_notes": "",
        "extracted_diagnoses": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act & Assert
    with pytest.raises(CodingException) as exc:
        await worker.execute(task_vars)
    assert "insuficientes" in str(exc.value).lower()


async def test_suggest_cid10_dmn_fallback(worker, mock_dmn_service):
    """Test graceful DMN fallback when tables don't exist."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("DMN table not found")

    task_vars = {
        "clinical_notes": "Patient has diabetes",
        "extracted_diagnoses": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert - should handle gracefully with empty results
    assert result["cid10_count"] == 0
    assert result["primary_cid10"] == ""
    assert result["suggested_cid10_codes"] == []


async def test_suggest_cid10_multiple_suggestions(worker, mock_dmn_service):
    """Test multiple CID-10 suggestions."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "suggestions": [
                {"code": "E11.9", "description": "Diabetes tipo 2", "confidence": 0.88},
                {"code": "E10.9", "description": "Diabetes tipo 1", "confidence": 0.45},
            ]
        },
        {
            "valid_suggestions": [
                {"code": "E11.9", "description": "Diabetes tipo 2", "confidence": 0.88},
                {"code": "E10.9", "description": "Diabetes tipo 1", "confidence": 0.45},
            ]
        },
    ]

    task_vars = {
        "clinical_notes": "diabetes mellitus",
        "extracted_diagnoses": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["cid10_count"] == 2
    assert result["primary_cid10"] == "E11.9"


async def test_suggest_cid10_with_extracted_diagnoses(worker, mock_dmn_service):
    """Test CID-10 suggestion with pre-extracted diagnoses."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"suggestions": [{"code": "I10", "description": "Hipertensão", "confidence": 0.95}]},
        {"valid_suggestions": [{"code": "I10", "description": "Hipertensão", "confidence": 0.95}]},
    ]

    task_vars = {
        "clinical_notes": "Follow-up visit",
        "extracted_diagnoses": [{"code": "I10", "display": "Essential hypertension"}],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["cid10_count"] == 1
    assert result["primary_cid10"] == "I10"


async def test_suggest_cid10_format_validation_filters_invalid(worker, mock_dmn_service):
    """Test that format validation filters out invalid codes."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "suggestions": [
                {"code": "J18.9", "description": "Valid", "confidence": 0.85},
                {"code": "INVALID", "description": "Invalid", "confidence": 0.70},
            ]
        },
        {"valid_suggestions": [{"code": "J18.9", "description": "Valid", "confidence": 0.85}]},
    ]

    task_vars = {
        "clinical_notes": "pneumonia",
        "extracted_diagnoses": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "HOSPITAL_A",
    }

    # Act
    result = await worker.execute(task_vars)

    # Assert
    assert result["cid10_count"] == 1
    assert result["suggested_cid10_codes"][0]["code"] == "J18.9"
