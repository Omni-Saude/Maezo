"""Tests for RetryFailedSubmissionWorker."""
from __future__ import annotations

import types

import pytest

from healthcare_platform.revenue_cycle.billing.workers.retry_failed_submission_worker_v2 import RetryFailedSubmissionWorker
from healthcare_platform.shared.integrations.tiss_client import StubTISSClient, TISSSubmissionResult

from unittest.mock import Mock


@pytest.fixture
def mock_dmn_service():
    """Create mock DMN service."""
    dmn_service = Mock()
    # Default DMN response: PROSSEGUIR (allow processing)
    dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Processar com sucesso",
        "risco": "BAIXO"
    }
    return dmn_service


@pytest.fixture
def tiss_client():
    """Create stub TISS client."""
    return StubTISSClient()


@pytest.fixture
def worker(tiss_client, mock_dmn_service):
    """Create worker instance."""
    return RetryFailedSubmissionWorker(
        tiss_client=tiss_client,
        dmn_service=mock_dmn_service
    )


@pytest.fixture
def retry_job():
    """Create retry job."""
    return types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "tiss_xml": "<tiss><guide>Test Guide</guide></tiss>",
            "payer_id": "PAYER-001",
            "attempt_number": 1,
            "max_attempts": 5,
            "last_error": "Connection timeout"
        }
    )


@pytest.mark.asyncio
async def test_successful_retry(worker, retry_job):
    """Test successful retry on first attempt."""
    result = await worker.execute(retry_job)

    assert result.success is True
    assert result.variables["retry_success"] is True
    assert result.variables["protocol_number"].startswith("STUB-")
    assert result.variables["next_attempt_number"] == 2
    assert result.variables["backoff_ms"] == 0
    assert result.variables["max_attempts_reached"] is False


@pytest.mark.asyncio
async def test_missing_claim_id(worker):
    """Test error when claim ID is missing."""
    job = types.SimpleNamespace(
        variables={
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "attempt_number": 1
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_CLAIM_ID"


@pytest.mark.asyncio
async def test_missing_tiss_xml(worker):
    """Test error when TISS XML is missing."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "payer_id": "PAYER-001",
            "attempt_number": 1
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_TISS_XML"


@pytest.mark.asyncio
async def test_missing_payer_id(worker):
    """Test error when payer ID is missing."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "attempt_number": 1
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_PAYER_ID"


@pytest.mark.asyncio
async def test_max_attempts_reached(worker):
    """Test behavior when max attempts already reached."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "attempt_number": 5,
            "max_attempts": 5,
            "last_error": "All previous attempts failed"
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["retry_success"] is False
    assert result.variables["protocol_number"] is None
    assert result.variables["max_attempts_reached"] is True
    assert result.variables["backoff_ms"] == 0


@pytest.mark.asyncio
async def test_exponential_backoff_calculation(worker):
    """Test exponential backoff calculation for different attempts."""
    test_cases = [
        (1, 2000),    # 2^1 * 1000 = 2000
        (2, 4000),    # 2^2 * 1000 = 4000
        (3, 8000),    # 2^3 * 1000 = 8000
        (4, 16000),   # 2^4 * 1000 = 16000
        (5, 32000),   # 2^5 * 1000 = 32000
        (10, 300000), # 2^10 * 1000 = 1024000, capped at 300000
    ]

    for attempt, expected_backoff in test_cases:
        job = types.SimpleNamespace(
            variables={
                "claim_id": "CLAIM-12345",
                "tiss_xml": "<tiss><guide>Test</guide></tiss>",
                "payer_id": "PAYER-001",
                "attempt_number": attempt,
                "max_attempts": 15
            }
        )

        # Mock failure to trigger backoff
        async def mock_submit_failure(guide_xml, payer_id):
            return TISSSubmissionResult(
                success=False,
                protocol_number=None,
                payer_response_code="ERROR",
                payer_response_message="Temporary failure"
            )

        original_submit = worker._tiss_client.submit_guide
        worker._tiss_client.submit_guide = mock_submit_failure

        result = await worker.execute(job)

        worker._tiss_client.submit_guide = original_submit

        assert result.success is True
        assert result.variables["backoff_ms"] == expected_backoff


@pytest.mark.asyncio
async def test_retry_failure_increments_attempt(worker, tiss_client, monkeypatch):
    """Test that failed retry increments attempt number."""
    async def mock_submit_failure(guide_xml, payer_id):
        return TISSSubmissionResult(
            success=False,
            protocol_number=None,
            payer_response_code="ERROR",
            payer_response_message="Submission failed"
        )

    monkeypatch.setattr(tiss_client, "submit_guide", mock_submit_failure)

    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "attempt_number": 2,
            "max_attempts": 5
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["retry_success"] is False
    assert result.variables["next_attempt_number"] == 3
    assert result.variables["max_attempts_reached"] is False


@pytest.mark.asyncio
async def test_last_attempt_marks_exhausted(worker, tiss_client, monkeypatch):
    """Test that last failed attempt marks max_attempts_reached."""
    async def mock_submit_failure(guide_xml, payer_id):
        return TISSSubmissionResult(
            success=False,
            protocol_number=None,
            payer_response_code="ERROR"
        )

    monkeypatch.setattr(tiss_client, "submit_guide", mock_submit_failure)

    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "attempt_number": 4,
            "max_attempts": 5
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["max_attempts_reached"] is True


@pytest.mark.asyncio
async def test_default_max_attempts(worker):
    """Test default max_attempts value."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "attempt_number": 1
            # max_attempts not provided
        }
    )

    result = await worker.execute(job)

    # Should use default of 5
    assert result.success is True


@pytest.mark.asyncio
async def test_unexpected_exception_handling(worker, tiss_client, monkeypatch):
    """Test handling of unexpected exceptions during retry."""
    async def mock_submit_exception(guide_xml, payer_id):
        raise RuntimeError("Unexpected network error")

    monkeypatch.setattr(tiss_client, "submit_guide", mock_submit_exception)

    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "attempt_number": 1,
            "max_attempts": 5
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["retry_success"] is False
    assert "last_error" in result.variables


@pytest.mark.asyncio
async def test_worker_metadata(worker):
    """Test worker metadata and configuration."""
    assert worker._topic == "billing-retry-failed-submission"
    assert worker.operation_name == "Retentar submissão falhada"
    assert worker.worker_name == "RetryFailedSubmissionWorker"


@pytest.mark.asyncio
async def test_successful_retry_clears_backoff(worker, retry_job):
    """Test that successful retry sets backoff to 0."""
    result = await worker.execute(retry_job)

    assert result.success is True
    assert result.variables["retry_success"] is True
    assert result.variables["backoff_ms"] == 0


@pytest.mark.asyncio
async def test_last_error_stored_on_failure(worker, tiss_client, monkeypatch):
    """Test that last error is stored when retry fails."""
    error_message = "Custom error message"

    async def mock_submit_failure(guide_xml, payer_id):
        return TISSSubmissionResult(
            success=False,
            protocol_number=None,
            payer_response_code="ERROR",
            payer_response_message=error_message
        )

    monkeypatch.setattr(tiss_client, "submit_guide", mock_submit_failure)

    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "attempt_number": 1,
            "max_attempts": 5
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["last_error"] == error_message


@pytest.mark.asyncio
async def test_backoff_cap_at_5_minutes(worker):
    """Test that backoff is capped at 300000ms (5 minutes)."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "attempt_number": 20,  # Very high attempt
            "max_attempts": 25
        }
    )

    # Mock failure to trigger backoff
    async def mock_submit_failure(guide_xml, payer_id):
        return TISSSubmissionResult(success=False)

    original_submit = worker._tiss_client.submit_guide
    worker._tiss_client.submit_guide = mock_submit_failure

    result = await worker.execute(job)

    worker._tiss_client.submit_guide = original_submit

    assert result.success is True
    assert result.variables["backoff_ms"] == 300000
