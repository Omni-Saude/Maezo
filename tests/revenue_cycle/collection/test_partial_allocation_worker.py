"""Tests for PartialAllocationWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.partial_allocation_worker import PartialAllocationWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return PartialAllocationWorker()


@pytest.mark.asyncio
async def test_partial_allocation_success(worker):
    """Test partial allocation across multiple claims."""
    task_vars = {
        "payment_id": "pay-001",
        "payment_amount": 1500.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": "claim-001", "outstanding_amount": 1000.00, "due_date": "2024-01-01"},
            {"claim_id": "claim-002", "outstanding_amount": 800.00, "due_date": "2024-01-02"},
        ],
    }

    result = await worker.execute(task_vars)

    assert len(result["allocations"]) == 2
    assert result["total_allocated"] == 1500.00
    assert result["remaining_amount"] == 0.00
    assert result["claims_paid"] == 1  # claim-001 fully paid
    assert result["claims_partial"] == 1  # claim-002 partially paid


@pytest.mark.asyncio
async def test_full_allocation_of_one_claim(worker):
    """Test full allocation to single claim."""
    task_vars = {
        "payment_id": "pay-002",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": "claim-001", "outstanding_amount": 1000.00, "due_date": "2024-01-01"}
        ],
    }

    result = await worker.execute(task_vars)

    assert len(result["allocations"]) == 1
    assert result["total_allocated"] == 1000.00
    assert result["remaining_amount"] == 0.00
    assert result["claims_paid"] == 1
    assert result["claims_partial"] == 0


@pytest.mark.asyncio
async def test_insufficient_amount_for_all_claims(worker):
    """Test when payment doesn't cover all claims."""
    task_vars = {
        "payment_id": "pay-003",
        "payment_amount": 500.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": "claim-001", "outstanding_amount": 1000.00, "due_date": "2024-01-01"},
            {"claim_id": "claim-002", "outstanding_amount": 800.00, "due_date": "2024-01-02"},
        ],
    }

    result = await worker.execute(task_vars)

    assert len(result["allocations"]) == 1  # Only first claim partially paid
    assert result["total_allocated"] == 500.00
    assert result["remaining_amount"] == 0.00
    assert result["claims_paid"] == 0
    assert result["claims_partial"] == 1
