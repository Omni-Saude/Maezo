"""Tests for SubmitToPayerWorker."""
from __future__ import annotations

import types
from datetime import datetime

import pytest

from healthcare_platform.revenue_cycle.billing.workers.submit_to_payer_worker import SubmitToPayerWorker
from healthcare_platform.shared.domain.exceptions import ClaimSubmissionError
from healthcare_platform.shared.integrations.tiss_client import StubTISSClient, TISSSubmissionResult


@pytest.fixture
def tiss_client():
    """Create stub TISS client."""
    return StubTISSClient()


@pytest.fixture
def worker(tiss_client):
    """Create worker instance."""
    return SubmitToPayerWorker(tiss_client=tiss_client)


@pytest.fixture
def valid_job():
    """Create valid job with required variables."""
    return types.SimpleNamespace(
        variables={
            "tiss_xml": "<tiss><guide>Test Guide</guide></tiss>",
            "payer_id": "PAYER-001",
            "claim_id": "CLAIM-12345"
        }
    )


@pytest.mark.asyncio
async def test_successful_submission(worker, valid_job):
    """Test successful TISS guide submission."""
    result = await worker.execute(valid_job)

    assert result.success is True
    assert result.variables["submission_success"] is True
    assert result.variables["protocol_number"].startswith("STUB-")
    assert result.variables["submission_timestamp"] is not None
    assert result.variables["payer_response_code"] == "OK"


@pytest.mark.asyncio
async def test_missing_tiss_xml(worker, tiss_client):
    """Test error when TISS XML is missing."""
    job = types.SimpleNamespace(
        variables={
            "payer_id": "PAYER-001",
            "claim_id": "CLAIM-12345"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_TISS_XML"
    assert "XML TISS não fornecido" in result.error_message


@pytest.mark.asyncio
async def test_missing_payer_id(worker, tiss_client):
    """Test error when payer ID is missing."""
    job = types.SimpleNamespace(
        variables={
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "claim_id": "CLAIM-12345"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_PAYER_ID"
    assert "operadora" in result.error_message.lower()


@pytest.mark.asyncio
async def test_missing_claim_id(worker, tiss_client):
    """Test error when claim ID is missing."""
    job = types.SimpleNamespace(
        variables={
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_CLAIM_ID"
    assert "fatura" in result.error_message.lower()


@pytest.mark.asyncio
async def test_submission_failure_retryable(worker, tiss_client, monkeypatch):
    """Test handling of submission failure (retryable error)."""
    # Mock client to return failure
    async def mock_submit_guide(guide_xml, payer_id):
        return TISSSubmissionResult(
            success=False,
            protocol_number=None,
            submission_timestamp=None,
            payer_response_code="TIMEOUT",
            payer_response_message="Connection timeout",
            validation_errors=[],
            processing_errors=["Network timeout"]
        )

    monkeypatch.setattr(tiss_client, "submit_guide", mock_submit_guide)

    job = types.SimpleNamespace(
        variables={
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "claim_id": "CLAIM-12345"
        }
    )

    result = await worker.execute(job)

    # Should be BPMN error with retryable ClaimSubmissionError
    assert result.success is False
    assert result.error_code == "CLAIM_SUBMISSION_FAILED"


@pytest.mark.asyncio
async def test_submission_with_validation_errors(worker, tiss_client, monkeypatch):
    """Test handling of validation errors from payer."""
    async def mock_submit_guide(guide_xml, payer_id):
        return TISSSubmissionResult(
            success=False,
            protocol_number=None,
            submission_timestamp=None,
            payer_response_code="VALIDATION_ERROR",
            payer_response_message="Invalid guide format",
            validation_errors=["Missing required field: patient_id"],
            processing_errors=[]
        )

    monkeypatch.setattr(tiss_client, "submit_guide", mock_submit_guide)

    job = types.SimpleNamespace(
        variables={
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "claim_id": "CLAIM-12345"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "CLAIM_SUBMISSION_FAILED"


@pytest.mark.asyncio
async def test_unexpected_exception_handling(worker, tiss_client, monkeypatch):
    """Test handling of unexpected exceptions during submission."""
    async def mock_submit_guide(guide_xml, payer_id):
        raise RuntimeError("Unexpected network error")

    monkeypatch.setattr(tiss_client, "submit_guide", mock_submit_guide)

    job = types.SimpleNamespace(
        variables={
            "tiss_xml": "<tiss><guide>Test</guide></tiss>",
            "payer_id": "PAYER-001",
            "claim_id": "CLAIM-12345"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "CLAIM_SUBMISSION_FAILED"


@pytest.mark.asyncio
async def test_worker_metadata(worker):
    """Test worker metadata and configuration."""
    assert worker._topic == "billing-submit-to-payer"
    assert worker.operation_name == "Submeter guia TISS à operadora"
    assert worker.worker_name == "SubmitToPayerWorker"


@pytest.mark.asyncio
async def test_protocol_number_format(worker, valid_job):
    """Test that protocol number is returned in expected format."""
    result = await worker.execute(valid_job)

    assert result.success is True
    protocol = result.variables["protocol_number"]
    assert isinstance(protocol, str)
    assert len(protocol) > 0


@pytest.mark.asyncio
async def test_submission_timestamp_format(worker, valid_job):
    """Test that submission timestamp is ISO formatted."""
    result = await worker.execute(valid_job)

    assert result.success is True
    timestamp = result.variables["submission_timestamp"]
    assert isinstance(timestamp, str)
    # Should be ISO format
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_multiple_submissions(worker, tiss_client):
    """Test multiple sequential submissions generate unique protocols."""
    job1 = types.SimpleNamespace(
        variables={
            "tiss_xml": "<tiss><guide>Test1</guide></tiss>",
            "payer_id": "PAYER-001",
            "claim_id": "CLAIM-001"
        }
    )
    job2 = types.SimpleNamespace(
        variables={
            "tiss_xml": "<tiss><guide>Test2</guide></tiss>",
            "payer_id": "PAYER-002",
            "claim_id": "CLAIM-002"
        }
    )

    result1 = await worker.execute(job1)
    result2 = await worker.execute(job2)

    assert result1.success is True
    assert result2.success is True
    assert result1.variables["protocol_number"] != result2.variables["protocol_number"]


@pytest.mark.asyncio
async def test_payer_response_message_included(worker, valid_job):
    """Test that payer response message is included in output."""
    result = await worker.execute(valid_job)

    assert result.success is True
    assert "payer_response_message" in result.variables
    assert result.variables["payer_response_message"] == "Stub submission accepted"
