"""
from __future__ import annotations

Tests for Track Appeal Status Worker.

Tests appeal status tracking and follow-up determination.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock

from healthcare_platform.revenue_cycle.glosa.workers.track_appeal_status_worker_v2 import TrackAppealStatusWorker


@pytest.fixture
def mock_tiss_client():
    """Create mock TISS client."""
    client = Mock()
    # Use regular Mock, not AsyncMock - worker calls it synchronously
    client.check_submission_status = Mock()
    return client


@pytest.fixture
def track_appeal_worker(mock_tiss_client):
    """Create TrackAppealStatusWorker instance with mock client."""
    return TrackAppealStatusWorker(tiss_client=mock_tiss_client)


@pytest.fixture
def base_input_variables():
    """Create base input variables for appeal tracking."""
    return {
        "submissionProtocol": "PROTOCOL-2024-999",
        "claimId": "CLAIM-123456",
        "appealDocumentId": "APPEAL-2024-001",
        "submissionTimestamp": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
    }


@pytest.mark.asyncio
async def test_appeal_approved(track_appeal_worker, mock_tiss_client, base_input_variables):
    """Test tracking of approved appeal."""
    # Arrange
    mock_response = {
        "statusCode": "APPROVED",
        "statusMessage": "Recurso aprovado totalmente",
        "responseDate": datetime.now(timezone.utc).isoformat(),
    }
    mock_tiss_client.check_submission_status.return_value = mock_response

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, base_input_variables)

    # Assert
    assert result.success is True
    assert result.variables["appealStatus"] == "APPROVED"
    assert result.variables["followUpRequired"] is False
    assert "aprovado" in result.variables["statusMessage"].lower()
    assert result.variables["payerResponse"] == mock_response

    from healthcare_platform.shared.domain.enums import TISSGuideType
    mock_tiss_client.check_submission_status.assert_called_once_with(
        protocol_number="PROTOCOL-2024-999",
        guide_type=TISSGuideType.SUMMARY,  # Appeals use SUMMARY type
    )


@pytest.mark.asyncio
async def test_appeal_denied(track_appeal_worker, mock_tiss_client, base_input_variables):
    """Test tracking of denied appeal."""
    # Arrange
    mock_response = {
        "statusCode": "DENIED",
        "statusMessage": "Recurso negado - documentação insuficiente",
        "responseDate": datetime.now(timezone.utc).isoformat(),
    }
    mock_tiss_client.check_submission_status.return_value = mock_response

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, base_input_variables)

    # Assert
    assert result.success is True
    assert result.variables["appealStatus"] == "DENIED"
    assert result.variables["followUpRequired"] is False
    assert "negado" in result.variables["statusMessage"].lower()


@pytest.mark.asyncio
async def test_appeal_partially_approved(track_appeal_worker, mock_tiss_client, base_input_variables):
    """Test tracking of partially approved appeal."""
    # Arrange
    mock_response = {
        "statusCode": "PARTIALLY_APPROVED",
        "statusMessage": "Recurso parcialmente aprovado",
        "approvedItems": ["GLOSA-001"],
        "deniedItems": ["GLOSA-002"],
    }
    mock_tiss_client.check_submission_status.return_value = mock_response

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, base_input_variables)

    # Assert
    assert result.success is True
    assert result.variables["appealStatus"] == "PARTIALLY_APPROVED"
    assert result.variables["followUpRequired"] is False
    assert "parcialmente" in result.variables["statusMessage"].lower()


@pytest.mark.asyncio
async def test_follow_up_required(track_appeal_worker, mock_tiss_client, base_input_variables):
    """Test follow-up required when threshold exceeded."""
    # Arrange - submission 20 days ago (exceeds 15-day threshold)
    old_submission = base_input_variables.copy()
    old_submission["submissionTimestamp"] = (
        datetime.now(timezone.utc) - timedelta(days=20)
    ).isoformat()

    mock_response = {
        "statusCode": "RECEIVED",
        "statusMessage": "Recurso recebido, em análise",
    }
    mock_tiss_client.check_submission_status.return_value = mock_response

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, old_submission)

    # Assert
    assert result.success is True
    assert result.variables["appealStatus"] == "PENDING"
    assert result.variables["followUpRequired"] is True
    assert result.variables["elapsedDays"] == 20
    assert "excedido" in result.variables["statusMessage"].lower()


@pytest.mark.asyncio
async def test_appeal_still_pending(track_appeal_worker, mock_tiss_client, base_input_variables):
    """Test appeal still pending within threshold."""
    # Arrange - recent submission (5 days ago)
    mock_response = {
        "statusCode": "IN_ANALYSIS",
        "statusMessage": "Em análise",
    }
    mock_tiss_client.check_submission_status.return_value = mock_response

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, base_input_variables)

    # Assert
    assert result.success is True
    assert result.variables["appealStatus"] == "IN_REVIEW"
    assert result.variables["followUpRequired"] is False
    assert result.variables["elapsedDays"] == 5
    assert "análise" in result.variables["statusMessage"].lower()


@pytest.mark.asyncio
async def test_pending_info_requires_follow_up(track_appeal_worker, mock_tiss_client, base_input_variables):
    """Test that PENDING_INFO status always requires follow-up."""
    # Arrange - recent submission but pending additional info
    mock_response = {
        "statusCode": "PENDING_INFO",
        "statusMessage": "Aguardando informações adicionais",
        "requiredDocuments": ["Relatório médico atualizado"],
    }
    mock_tiss_client.check_submission_status.return_value = mock_response

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, base_input_variables)

    # Assert
    assert result.success is True
    assert result.variables["appealStatus"] == "IN_REVIEW"
    assert result.variables["followUpRequired"] is True


@pytest.mark.asyncio
async def test_missing_protocol(track_appeal_worker, mock_tiss_client, base_input_variables):
    """Test validation error when protocol is missing."""
    # Arrange
    invalid_vars = base_input_variables.copy()
    del invalid_vars["submissionProtocol"]

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, invalid_vars)

    # Assert
    assert result.success is False
    assert "protocolo" in result.error_message.lower()
    mock_tiss_client.check_submission_status.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_status_code(track_appeal_worker, mock_tiss_client, base_input_variables):
    """Test handling of unknown status code from payer."""
    # Arrange
    mock_response = {
        "statusCode": "UNKNOWN_CODE",
        "statusMessage": "Status desconhecido",
    }
    mock_tiss_client.check_submission_status.return_value = mock_response

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, base_input_variables)

    # Assert
    assert result.success is True
    assert result.variables["appealStatus"] == "UNKNOWN"  # Unknown codes map to UNKNOWN
    assert "desconhecido" in result.variables["statusMessage"].lower()


@pytest.mark.asyncio
async def test_elapsed_days_calculation(track_appeal_worker, mock_tiss_client):
    """Test accurate elapsed days calculation."""
    # Arrange - exactly 10 days ago
    timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    input_vars = {
        "submissionProtocol": "PROTOCOL-TEST",
        "claimId": "CLAIM-123",
        "appealDocumentId": "APPEAL-123",
        "submissionTimestamp": timestamp,
    }

    mock_response = {
        "statusCode": "RECEIVED",
        "statusMessage": "Recebido",
    }
    mock_tiss_client.check_submission_status.return_value = mock_response

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, input_vars)

    # Assert
    assert result.success is True
    assert result.variables["elapsedDays"] == 10


@pytest.mark.asyncio
async def test_invalid_timestamp_defaults_to_zero_days(track_appeal_worker, mock_tiss_client, base_input_variables):
    """Test that invalid timestamp defaults to 0 elapsed days."""
    # Arrange
    invalid_vars = base_input_variables.copy()
    invalid_vars["submissionTimestamp"] = "invalid-timestamp"

    mock_response = {
        "statusCode": "RECEIVED",
        "statusMessage": "Recebido",
    }
    mock_tiss_client.check_submission_status.return_value = mock_response

    mock_job = Mock()

    # Act
    result = await track_appeal_worker.process_task(mock_job, invalid_vars)

    # Assert
    assert result.success is True
    assert result.variables["elapsedDays"] == 0
