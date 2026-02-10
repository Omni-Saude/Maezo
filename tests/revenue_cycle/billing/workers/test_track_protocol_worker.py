"""Tests for TrackProtocolWorker."""
from __future__ import annotations

import types
from datetime import datetime

import pytest

from healthcare_platform.revenue_cycle.billing.workers.track_protocol_worker import TrackProtocolWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return TrackProtocolWorker()


@pytest.fixture
def valid_job():
    """Create valid job with required variables."""
    return types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "payer_id": "PAYER-001",
            "submission_timestamp": "2025-01-15T10:30:00Z"
        }
    )


@pytest.mark.asyncio
async def test_successful_protocol_tracking(worker, valid_job):
    """Test successful protocol tracking."""
    result = await worker.execute(valid_job)

    assert result.success is True
    assert result.variables["protocol_tracked"] is True
    assert result.variables["tracking_id"].startswith("TRACK-")


@pytest.mark.asyncio
async def test_missing_claim_id(worker):
    """Test error when claim ID is missing."""
    job = types.SimpleNamespace(
        variables={
            "protocol_number": "PROTO-2025-001",
            "payer_id": "PAYER-001"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_CLAIM_ID"
    assert "fatura" in result.error_message.lower()


@pytest.mark.asyncio
async def test_missing_protocol_number(worker):
    """Test error when protocol number is missing."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "payer_id": "PAYER-001"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_PROTOCOL_NUMBER"
    assert "protocolo" in result.error_message.lower()


@pytest.mark.asyncio
async def test_empty_protocol_number(worker):
    """Test error when protocol number is empty string."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "   ",  # Whitespace only
            "payer_id": "PAYER-001"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_PROTOCOL_NUMBER"


@pytest.mark.asyncio
async def test_missing_payer_id(worker):
    """Test error when payer ID is missing."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001"
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_PAYER_ID"
    assert "operadora" in result.error_message.lower()


@pytest.mark.asyncio
async def test_protocol_retrieval(worker, valid_job):
    """Test that tracked protocol can be retrieved."""
    result = await worker.execute(valid_job)

    assert result.success is True
    protocol_number = valid_job.variables["protocol_number"]

    # Retrieve the stored record
    record = worker.get_protocol_record(protocol_number)

    assert record is not None
    assert record["claim_id"] == "CLAIM-12345"
    assert record["protocol_number"] == protocol_number
    assert record["payer_id"] == "PAYER-001"
    assert "tracking_id" in record
    assert "tracked_at" in record


@pytest.mark.asyncio
async def test_tracking_id_uniqueness(worker):
    """Test that each tracking generates a unique tracking ID."""
    job1 = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-001",
            "protocol_number": "PROTO-001",
            "payer_id": "PAYER-001"
        }
    )
    job2 = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-002",
            "protocol_number": "PROTO-002",
            "payer_id": "PAYER-001"
        }
    )

    result1 = await worker.execute(job1)
    result2 = await worker.execute(job2)

    assert result1.success is True
    assert result2.success is True
    assert result1.variables["tracking_id"] != result2.variables["tracking_id"]


@pytest.mark.asyncio
async def test_protocol_overwrite(worker):
    """Test that re-tracking same protocol overwrites previous record."""
    job1 = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-001",
            "protocol_number": "PROTO-SAME",
            "payer_id": "PAYER-001"
        }
    )
    job2 = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-002",
            "protocol_number": "PROTO-SAME",  # Same protocol
            "payer_id": "PAYER-002"
        }
    )

    result1 = await worker.execute(job1)
    result2 = await worker.execute(job2)

    assert result1.success is True
    assert result2.success is True

    # Should retrieve the latest record
    record = worker.get_protocol_record("PROTO-SAME")
    assert record["claim_id"] == "CLAIM-002"
    assert record["payer_id"] == "PAYER-002"


@pytest.mark.asyncio
async def test_protocol_not_found(worker):
    """Test retrieval of non-existent protocol."""
    record = worker.get_protocol_record("NON-EXISTENT-PROTO")
    assert record is None


@pytest.mark.asyncio
async def test_submission_timestamp_stored(worker):
    """Test that submission timestamp is stored in record."""
    timestamp = "2025-01-15T14:30:00Z"
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-TS",
            "payer_id": "PAYER-001",
            "submission_timestamp": timestamp
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    record = worker.get_protocol_record("PROTO-TS")
    assert record["submission_timestamp"] == timestamp


@pytest.mark.asyncio
async def test_submission_timestamp_optional(worker):
    """Test that submission timestamp is optional."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-NO-TS",
            "payer_id": "PAYER-001"
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    record = worker.get_protocol_record("PROTO-NO-TS")
    assert record["submission_timestamp"] is None


@pytest.mark.asyncio
async def test_tracked_at_timestamp(worker, valid_job):
    """Test that tracked_at timestamp is automatically generated."""
    result = await worker.execute(valid_job)

    assert result.success is True
    record = worker.get_protocol_record(valid_job.variables["protocol_number"])
    tracked_at = record["tracked_at"]

    # Should be valid ISO timestamp
    datetime.fromisoformat(tracked_at.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_worker_metadata(worker):
    """Test worker metadata and configuration."""
    assert worker._topic == "billing-track-protocol"
    assert worker.operation_name == "Registrar protocolo de submissão"
    assert worker.worker_name == "TrackProtocolWorker"


@pytest.mark.asyncio
async def test_tracking_counter_increment(worker):
    """Test that tracking counter increments properly."""
    initial_counter = worker._tracking_counter

    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-COUNT",
            "payer_id": "PAYER-001"
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert worker._tracking_counter == initial_counter + 1


@pytest.mark.asyncio
async def test_multiple_protocols_stored(worker):
    """Test that multiple protocols are stored independently."""
    for i in range(5):
        job = types.SimpleNamespace(
            variables={
                "claim_id": f"CLAIM-{i}",
                "protocol_number": f"PROTO-{i}",
                "payer_id": f"PAYER-{i}"
            }
        )
        result = await worker.execute(job)
        assert result.success is True

    # Verify all protocols are retrievable
    for i in range(5):
        record = worker.get_protocol_record(f"PROTO-{i}")
        assert record is not None
        assert record["claim_id"] == f"CLAIM-{i}"
