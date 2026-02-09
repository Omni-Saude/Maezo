"""Tests for HandleAcknowledgmentWorker."""
from __future__ import annotations

import types

import pytest

from platform.revenue_cycle.billing.workers.handle_acknowledgment_worker import HandleAcknowledgmentWorker
from platform.shared.domain.enums import BillingStatus


@pytest.fixture
def worker():
    """Create worker instance."""
    return HandleAcknowledgmentWorker()


@pytest.fixture
def ack_job():
    """Create ACK job."""
    return types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-001",
            "claim_id": "CLAIM-12345",
            "acknowledgment_type": "ACK",
            "response_code": "OK",
            "response_message": "Accepted successfully"
        }
    )


@pytest.fixture
def nack_job():
    """Create NACK job."""
    return types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-002",
            "claim_id": "CLAIM-67890",
            "acknowledgment_type": "NACK",
            "response_code": "VALIDATION_ERROR",
            "response_message": "Invalid patient ID",
            "errors": ["Patient ID not found", "Missing authorization"]
        }
    )


@pytest.mark.asyncio
async def test_handle_ack(worker, ack_job):
    """Test handling of positive acknowledgment (ACK)."""
    result = await worker.execute(ack_job)

    assert result.success is True
    assert result.variables["acknowledged"] is True
    assert result.variables["billing_status"] == BillingStatus.ACKNOWLEDGED.value
    assert result.variables["requires_resubmission"] is False
    assert result.variables["rejection_reasons"] == []


@pytest.mark.asyncio
async def test_handle_nack(worker, nack_job):
    """Test handling of negative acknowledgment (NACK)."""
    result = await worker.execute(nack_job)

    assert result.success is True
    assert result.variables["acknowledged"] is False
    assert result.variables["billing_status"] == BillingStatus.DENIED.value
    assert result.variables["requires_resubmission"] is False
    assert len(result.variables["rejection_reasons"]) > 0
    assert "Invalid patient ID" in result.variables["rejection_reasons"]


@pytest.mark.asyncio
async def test_missing_protocol_number(worker):
    """Test error when protocol number is missing."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "acknowledgment_type": "ACK"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_PROTOCOL_NUMBER"
    assert "protocolo" in result.error_message.lower()


@pytest.mark.asyncio
async def test_missing_claim_id(worker):
    """Test error when claim ID is missing."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-001",
            "acknowledgment_type": "ACK"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_CLAIM_ID"
    assert "fatura" in result.error_message.lower()


@pytest.mark.asyncio
async def test_invalid_acknowledgment_type(worker):
    """Test error with invalid acknowledgment type."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-001",
            "claim_id": "CLAIM-12345",
            "acknowledgment_type": "INVALID"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "INVALID_ACKNOWLEDGMENT_TYPE"


@pytest.mark.asyncio
async def test_acknowledgment_type_case_insensitive(worker):
    """Test that acknowledgment type is case insensitive."""
    job_lower = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-001",
            "claim_id": "CLAIM-12345",
            "acknowledgment_type": "ack",
            "response_code": "OK"
        }
    )

    result = await worker.execute(job_lower)

    assert result.success is True
    assert result.variables["acknowledged"] is True


@pytest.mark.asyncio
async def test_nack_with_retryable_error(worker):
    """Test NACK with retryable error code."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-003",
            "claim_id": "CLAIM-99999",
            "acknowledgment_type": "NACK",
            "response_code": "TIMEOUT",
            "response_message": "Connection timeout"
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["acknowledged"] is False
    assert result.variables["requires_resubmission"] is True
    assert result.variables["billing_status"] == BillingStatus.SUBMITTED.value


@pytest.mark.asyncio
async def test_nack_with_service_unavailable(worker):
    """Test NACK with service unavailable (retryable)."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-004",
            "claim_id": "CLAIM-88888",
            "acknowledgment_type": "NACK",
            "response_code": "SERVICE_UNAVAILABLE",
            "response_message": "Service temporarily unavailable"
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["requires_resubmission"] is True
    assert result.variables["billing_status"] == BillingStatus.SUBMITTED.value


@pytest.mark.asyncio
async def test_nack_with_rate_limit(worker):
    """Test NACK with rate limit (retryable)."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-005",
            "claim_id": "CLAIM-77777",
            "acknowledgment_type": "NACK",
            "response_code": "RATE_LIMIT",
            "response_message": "Rate limit exceeded"
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["requires_resubmission"] is True


@pytest.mark.asyncio
async def test_nack_with_permanent_rejection(worker):
    """Test NACK with permanent rejection."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-006",
            "claim_id": "CLAIM-66666",
            "acknowledgment_type": "NACK",
            "response_code": "INVALID_CLAIM",
            "response_message": "Claim data invalid"
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["acknowledged"] is False
    assert result.variables["requires_resubmission"] is False
    assert result.variables["billing_status"] == BillingStatus.DENIED.value


@pytest.mark.asyncio
async def test_nack_rejection_reasons_from_errors(worker):
    """Test that rejection reasons include both message and errors."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-007",
            "claim_id": "CLAIM-55555",
            "acknowledgment_type": "NACK",
            "response_code": "MULTIPLE_ERRORS",
            "response_message": "Multiple validation errors",
            "errors": ["Error 1", "Error 2", "Error 3"]
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    reasons = result.variables["rejection_reasons"]
    assert "Multiple validation errors" in reasons
    assert "Error 1" in reasons
    assert "Error 2" in reasons
    assert "Error 3" in reasons
    assert len(reasons) == 4


@pytest.mark.asyncio
async def test_nack_without_errors_list(worker):
    """Test NACK when errors list is not provided."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-008",
            "claim_id": "CLAIM-44444",
            "acknowledgment_type": "NACK",
            "response_code": "ERROR",
            "response_message": "General error"
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    reasons = result.variables["rejection_reasons"]
    assert len(reasons) == 1
    assert "General error" in reasons


@pytest.mark.asyncio
async def test_ack_without_response_message(worker):
    """Test ACK without response message."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-009",
            "claim_id": "CLAIM-33333",
            "acknowledgment_type": "ACK",
            "response_code": "OK"
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["acknowledged"] is True


@pytest.mark.asyncio
async def test_worker_metadata(worker):
    """Test worker metadata and configuration."""
    assert worker._topic == "billing-handle-acknowledgment"
    assert worker.operation_name == "Processar confirmação da operadora"
    assert worker.worker_name == "HandleAcknowledgmentWorker"


@pytest.mark.asyncio
async def test_nack_empty_errors_list(worker):
    """Test NACK with empty errors list."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-010",
            "claim_id": "CLAIM-22222",
            "acknowledgment_type": "NACK",
            "response_code": "ERROR",
            "response_message": "Error occurred",
            "errors": []
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    reasons = result.variables["rejection_reasons"]
    assert len(reasons) == 1
    assert "Error occurred" in reasons
