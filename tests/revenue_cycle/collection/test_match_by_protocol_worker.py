"""Tests for MatchByProtocolWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.match_by_protocol_worker import MatchByProtocolWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return MatchByProtocolWorker()


@pytest.mark.asyncio
async def test_match_by_protocol_success(worker):
    """Test successful protocol match."""
    task_vars = {
        "payment_id": "pay-001",
        "protocol_number": "TISS-12345",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {
                "claim_id": "claim-001",
                "protocol_number": "TISS-12345",
                "total_amount": 1000.00,
            }
        ],
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is True
    assert result["claim_id"] == "claim-001"
    assert result["allocation_id"] == "ALLOC-pay-001-claim-001"
    assert result["protocol_number"] == "TISS-12345"


@pytest.mark.asyncio
async def test_protocol_not_found(worker):
    """Test when protocol is not found."""
    task_vars = {
        "payment_id": "pay-002",
        "protocol_number": "TISS-99999",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {
                "claim_id": "claim-001",
                "protocol_number": "TISS-12345",
                "total_amount": 1000.00,
            }
        ],
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is False
    assert result["claim_id"] is None
    assert result["allocation_id"] is None
