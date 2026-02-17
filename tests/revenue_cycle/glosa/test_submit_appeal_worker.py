"""
from __future__ import annotations

Tests for Submit Appeal Worker.

Tests appeal submission via TISS protocol with various scenarios.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

from healthcare_platform.revenue_cycle.glosa.workers.submit_appeal_worker_v2 import SubmitAppealWorker
from healthcare_platform.shared.domain.exceptions import GlosaException
from healthcare_platform.shared.integrations.tiss_client import TISSGuideDTO, TISSSubmissionResult


@pytest.fixture
def mock_tiss_client():
    """Create mock TISS client."""
    client = Mock()
    # Use regular Mock, not AsyncMock - worker calls it synchronously
    client.submit_guide = Mock()
    return client


@pytest.fixture
def submit_appeal_worker(mock_tiss_client, mock_dmn_service):
    """Create SubmitAppealWorker instance with mock client."""
    return SubmitAppealWorker(tiss_client=mock_tiss_client, dmn_service=mock_dmn_service)


@pytest.fixture
def valid_input_variables():
    """Create valid input variables for appeal submission."""
    return {
        "appealDocumentId": "APPEAL-2024-001",
        "claimId": "CLAIM-123456",
        "eligibleGlosas": [
            {
                "glosaId": "GLOSA-001",
                "itemCode": "40101012",
                "deniedAmount": "250.00",
                "reasonCode": "INCOMPLETE_DOC",
            },
            {
                "glosaId": "GLOSA-002",
                "itemCode": "40101020",
                "deniedAmount": "180.00",
                "reasonCode": "NOT_AUTHORIZED",
            },
        ],
        "appealLetter": "Documentação complementar anexada conforme solicitado.",
        "payerId": "PAYER-789",
        "providerId": "PROVIDER-456",
    }


@pytest.mark.asyncio
async def test_successful_submission(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test successful appeal submission."""
    # Arrange
    mock_result = TISSSubmissionResult(
        success=True,
        protocol_number="PROTOCOL-2024-999",
        payer_response_code="SUCCESS",  # Correct attribute name
        payer_response_message="Recurso recebido com sucesso",
    )
    mock_tiss_client.submit_guide.return_value = mock_result

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, valid_input_variables)

    # Assert
    assert result.success is True
    assert result.variables["submissionProtocol"] == "PROTOCOL-2024-999"
    assert result.variables["submissionSuccess"] is True
    assert result.variables["payerResponseCode"] == "SUCCESS"
    assert "submissionTimestamp" in result.variables

    # Verify TISS client called with correct parameters
    mock_tiss_client.submit_guide.assert_called_once()
    call_args = mock_tiss_client.submit_guide.call_args[0][0]
    assert isinstance(call_args, TISSGuideDTO)
    from healthcare_platform.shared.domain.enums import TISSGuideType
    assert call_args.guide_type == TISSGuideType.SUMMARY  # Appeals use SUMMARY type
    assert call_args.guide_number == "APPEAL-2024-001"
    assert call_args.payer_id == "PAYER-789"
    assert call_args.provider_id == "PROVIDER-456"
    assert len(call_args.items) == 2


@pytest.mark.asyncio
async def test_submission_failure_retries(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test submission failure handling (v2 doesn't retry, returns requiresReview)."""
    # Arrange - transient error
    failure_result = TISSSubmissionResult(
        success=False,
        protocol_number="",
        payer_response_code="TIMEOUT",  # Correct attribute name
        payer_response_message="Timeout na comunicação",
    )

    mock_tiss_client.submit_guide.return_value = failure_result

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, valid_input_variables)

    # Assert - v2 returns success with requiresReview for transient errors
    assert result.success is True
    assert result.variables["submissionSuccess"] is False
    assert result.variables["payerResponseCode"] == "TIMEOUT"
    assert result.variables.get("requiresReview") is True  # DMN may set this
    assert mock_tiss_client.submit_guide.call_count == 1  # No retries in v2


@pytest.mark.asyncio
async def test_submission_exhausts_retries(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test submission failure after exhausting retries."""
    # Arrange - always fail with transient error
    failure_result = TISSSubmissionResult(
        success=False,
        protocol_number="",
        payer_response_code="CONNECTION_ERROR",  # Correct attribute name
        payer_response_message="Erro de conexão",
    )

    mock_tiss_client.submit_guide.return_value = failure_result

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, valid_input_variables)

    # Assert
    # V2 worker returns success with requiresReview=True instead of failing
    assert result.success is True
    assert result.variables["submissionSuccess"] is False
    assert result.variables["payerResponseCode"] == "CONNECTION_ERROR"
    assert mock_tiss_client.submit_guide.call_count == 1  # No retries in v2


@pytest.mark.asyncio
async def test_missing_appeal_document(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test validation error when appeal document ID is missing."""
    # Arrange
    invalid_vars = valid_input_variables.copy()
    del invalid_vars["appealDocumentId"]

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, invalid_vars)

    # Assert
    assert result.success is False
    assert "documento de recurso" in result.error_message.lower()
    mock_tiss_client.submit_guide.assert_not_called()


@pytest.mark.asyncio
async def test_missing_claim_id(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test validation error when claim ID is missing."""
    # Arrange
    invalid_vars = valid_input_variables.copy()
    del invalid_vars["claimId"]

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, invalid_vars)

    # Assert
    assert result.success is False
    assert "conta" in result.error_message.lower()


@pytest.mark.asyncio
async def test_empty_glosas_list(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test validation error when no eligible glosas provided."""
    # Arrange
    invalid_vars = valid_input_variables.copy()
    invalid_vars["eligibleGlosas"] = []

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, invalid_vars)

    # Assert
    assert result.success is False
    assert "elegível" in result.error_message.lower()


@pytest.mark.asyncio
async def test_tiss_integration(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test TISS integration with proper guide construction."""
    # Arrange
    mock_result = TISSSubmissionResult(
        success=True,
        protocol_number="PROTOCOL-TEST",
        response_code="SUCCESS",
        response_message="OK",
    )
    mock_tiss_client.submit_guide.return_value = mock_result

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, valid_input_variables)

    # Assert - verify guide structure
    call_args = mock_tiss_client.submit_guide.call_args[0][0]
    assert call_args.payer_id == "PAYER-789"
    assert call_args.provider_id == "PROVIDER-456"
    # Appeals use SUMMARY guide type, not "APPEAL"
    from healthcare_platform.shared.domain.enums import TISSGuideType
    assert call_args.guide_type == TISSGuideType.SUMMARY

    # Verify items are passed through
    assert len(call_args.items) == 2
    assert call_args.items == valid_input_variables["eligibleGlosas"]


@pytest.mark.asyncio
async def test_submission_with_non_transient_error(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test submission with non-transient error (no retry)."""
    # Arrange - permanent error
    failure_result = TISSSubmissionResult(
        success=False,
        protocol_number="",
        payer_response_code="INVALID_FORMAT",  # Correct attribute name
        payer_response_message="Formato de guia inválido",
    )

    mock_tiss_client.submit_guide.return_value = failure_result

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, valid_input_variables)

    # Assert - V2 returns success with requiresReview instead of failing
    assert result.success is True
    assert result.variables["submissionSuccess"] is False
    assert result.variables["payerResponseCode"] == "INVALID_FORMAT"
    assert mock_tiss_client.submit_guide.call_count == 1
