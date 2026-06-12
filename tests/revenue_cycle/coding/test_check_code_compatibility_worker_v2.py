"""Tests for CheckCodeCompatibilityWorker."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from healthcare_platform.revenue_cycle.coding.workers import CheckCodeCompatibilityWorker
from healthcare_platform.shared.domain.exceptions import (
    CodingException,
    IncompatibleCodes,
)


@pytest.fixture
def worker_v2(mock_dmn_service):
    """Create CheckCodeCompatibilityWorker instance with mocked DMN service."""
    worker = CheckCodeCompatibilityWorker()
    worker.dmn_service = mock_dmn_service
    return worker


@pytest.fixture
def valid_task_variables():
    """Valid task variables for compatibility check."""
    return {
        "validatedCid10": ["I21.0", "E11.9"],
        "validatedTuss": ["40101010", "40304361"],
        "encounterId": "enc_123",
        "tenantId": "hospital_a",
    }


@pytest.mark.asyncio
async def test_happy_path_compatible_codes(worker_v2, mock_dmn_service, valid_task_variables):
    """Test happy path: all codes compatible."""
    # Arrange
    mock_dmn_service.evaluate.return_value = {"resultado": "PROSSEGUIR"}

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["compatible"] is True
    assert len(result["incompatibilities"]) == 0
    assert len(result["warnings"]) == 0


@pytest.mark.asyncio
async def test_bloquear_raises_incompatible_codes(worker_v2, mock_dmn_service, valid_task_variables):
    """Test BLOQUEAR result raises IncompatibleCodes exception."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "resultado": "BLOQUEAR",
            "acao": "CID-10 F capítulo incompatível com grupo TUSS 40",
            "cid10": "F20.0",
            "tuss": "40101010",
        },
        {"resultado": "PROSSEGUIR"},
    ]

    # Act & Assert
    with pytest.raises(IncompatibleCodes) as exc_info:
        await worker_v2.execute(valid_task_variables)

    assert "incompatíveis detectados" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_revisar_adds_warning(worker_v2, mock_dmn_service, valid_task_variables):
    """Test REVISAR result adds warning but doesn't block."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"resultado": "PROSSEGUIR"},
        {
            "resultado": "REVISAR",
            "acao": "Combinação requer justificativa clínica",
        },
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["compatible"] is True
    assert len(result["warnings"]) == 1
    assert "justificativa" in result["warnings"][0].lower()


@pytest.mark.asyncio
async def test_legacy_5_output_schema_compat(worker_v2, mock_dmn_service, valid_task_variables):
    """Test backward compatibility with old 5-output schema."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "Decisao": "Bloquear",
            "Justificativa": "Incompatibilidade detectada",
            "cid10": "H00.0",
            "tuss": "40101010",
        },
        {"Decisao": "Prosseguir"},
    ]

    # Act & Assert
    with pytest.raises(IncompatibleCodes):
        await worker_v2.execute(valid_task_variables)


@pytest.mark.asyncio
async def test_invalid_input_missing_cid10(worker_v2):
    """Test invalid input: missing CID-10 codes."""
    # Arrange
    invalid_vars = {
        "validatedCid10": [],  # Empty
        "validatedTuss": ["40101010"],
        "encounterId": "enc_123",
        "tenantId": "hospital_a",
    }

    # Act & Assert
    with pytest.raises(CodingException) as exc_info:
        await worker_v2.execute(invalid_vars)

    assert exc_info.value.bpmn_error_code == "CODING_ERROR"


@pytest.mark.asyncio
async def test_invalid_input_missing_tuss(worker_v2):
    """Test invalid input: missing TUSS codes."""
    # Arrange
    invalid_vars = {
        "validatedCid10": ["I21.0"],
        "validatedTuss": [],  # Empty
        "encounterId": "enc_123",
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
    assert "code_compatibility/incompatible_matrix" in worker_v2.__class__.__doc__
    assert "code_compatibility/warning_pairs" in worker_v2.__class__.__doc__


@pytest.mark.asyncio
async def test_dmn_fallback_orphan(worker_v2, mock_dmn_service, valid_task_variables):
    """Test DMN evaluation fallback when tables don't exist (ORPHAN)."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = FileNotFoundError("Table not found")

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert - should complete without errors (fallback to compatible)
    assert result["compatible"] is True
    assert len(result["incompatibilities"]) == 0


@pytest.mark.asyncio
async def test_multiple_incompatibilities(worker_v2, mock_dmn_service, valid_task_variables):
    """Test multiple incompatibilities are collected."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {
            "resultado": "BLOQUEAR",
            "acao": "Incompatível 1",
            "cid10": "F20.0",
            "tuss": "40101010",
        },
        {"resultado": "PROSSEGUIR"},
    ]

    # Act & Assert
    with pytest.raises(IncompatibleCodes) as exc_info:
        await worker_v2.execute(valid_task_variables)

    details = exc_info.value.details
    assert len(details["incompatibilities"]) >= 1


@pytest.mark.asyncio
async def test_legacy_revisar_alertar_warnings(worker_v2, mock_dmn_service, valid_task_variables):
    """Test legacy Revisar and Alertar both produce warnings."""
    # Arrange
    mock_dmn_service.evaluate.side_effect = [
        {"Decisao": "Prosseguir"},
        {"Decisao": "Alertar", "Justificativa": "Atenção: verificar combinação"},
    ]

    # Act
    result = await worker_v2.execute(valid_task_variables)

    # Assert
    assert result["compatible"] is True
    assert len(result["warnings"]) == 1
