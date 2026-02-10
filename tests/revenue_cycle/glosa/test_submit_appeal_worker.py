"""
Tests for Submit Appeal Worker.

Tests appeal submission via TISS protocol with various scenarios.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

from healthcare_platform.revenue_cycle.glosa.workers.submit_appeal_worker import SubmitAppealWorker
from healthcare_platform.shared.domain.exceptions import GlosaException
from healthcare_platform.shared.integrations.tiss_client import TISSGuideDTO, TISSSubmissionResult


@pytest.fixture
def mock_tiss_client():
    """Create mock TISS client."""
    client = Mock()
    client.submit_guide = AsyncMock()
    return client


@pytest.fixture
def submit_appeal_worker(mock_tiss_client):
    """Create SubmitAppealWorker instance with mock client."""
    return SubmitAppealWorker(tiss_client=mock_tiss_client)


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
        response_code="SUCCESS",
        response_message="Recurso recebido com sucesso",
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
    assert call_args.guide_type == "APPEAL"
    assert call_args.guide_number == "APPEAL-2024-001"
    assert call_args.claim_id == "CLAIM-123456"
    assert len(call_args.items) == 2


@pytest.mark.asyncio
async def test_submission_failure_retries(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test submission failure with retry logic."""
    # Arrange - fail twice with transient errors, succeed on third try
    failure_result = TISSSubmissionResult(
        success=False,
        protocol_number="",
        response_code="TIMEOUT",
        response_message="Timeout na comunicação",
    )
    success_result = TISSSubmissionResult(
        success=True,
        protocol_number="PROTOCOL-2024-888",
        response_code="SUCCESS",
        response_message="Recurso recebido",
    )

    mock_tiss_client.submit_guide.side_effect = [
        failure_result,
        failure_result,
        success_result,
    ]

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, valid_input_variables)

    # Assert
    assert result.success is True
    assert result.variables["submissionProtocol"] == "PROTOCOL-2024-888"
    assert mock_tiss_client.submit_guide.call_count == 3


@pytest.mark.asyncio
async def test_submission_exhausts_retries(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test submission failure after exhausting retries."""
    # Arrange - always fail with transient error
    failure_result = TISSSubmissionResult(
        success=False,
        protocol_number="",
        response_code="CONNECTION_ERROR",
        response_message="Erro de conexão",
    )

    mock_tiss_client.submit_guide.return_value = failure_result

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, valid_input_variables)

    # Assert
    assert result.success is False
    assert "Falha ao enviar recurso após" in result.error_message
    assert mock_tiss_client.submit_guide.call_count == 3


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
    assert call_args.additional_data["appealLetter"] == valid_input_variables["appealLetter"]

    # Verify items include all required fields
    for item in call_args.items:
        assert "glosaId" in item
        assert "itemCode" in item
        assert "deniedAmount" in item
        assert "reasonCode" in item
        assert "justification" in item


@pytest.mark.asyncio
async def test_submission_with_non_transient_error(submit_appeal_worker, mock_tiss_client, valid_input_variables):
    """Test submission with non-transient error (no retry)."""
    # Arrange - permanent error
    failure_result = TISSSubmissionResult(
        success=False,
        protocol_number="",
        response_code="INVALID_FORMAT",
        response_message="Formato de guia inválido",
    )

    mock_tiss_client.submit_guide.return_value = failure_result

    mock_job = Mock()

    # Act
    result = await submit_appeal_worker.process_task(mock_job, valid_input_variables)

    # Assert - should fail immediately without retry for non-transient errors
    assert result.success is False
    assert result.variables["submissionSuccess"] is False
    assert result.variables["payerResponseCode"] == "INVALID_FORMAT"
    assert mock_tiss_client.submit_guide.call_count == 1
