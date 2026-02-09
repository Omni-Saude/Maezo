"""Tests for HandleUnderpaymentWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.exceptions import UnderpaymentError
from platform.revenue_cycle.collection.workers.handle_underpayment_worker import HandleUnderpaymentWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return HandleUnderpaymentWorker()


@pytest.mark.asyncio
async def test_underpayment_is_glosa(worker):
    """Test underpayment that matches known glosa amount."""
    task_vars = {
        "payment_id": "pay-001",
        "claim_id": "claim-001",
        "payment_amount": 900.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "glosa_amount": 100.00,  # Matches underpayment
    }

    result = await worker.execute(task_vars)

    assert result["underpayment_amount"] == 100.00
    assert result["is_glosa"] is True
    assert result["requires_collection"] is False


@pytest.mark.asyncio
async def test_underpayment_requires_collection(worker):
    """Test underpayment that requires collection action."""
    task_vars = {
        "payment_id": "pay-002",
        "claim_id": "claim-002",
        "payment_amount": 800.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "glosa_amount": 0.00,
    }

    with pytest.raises(UnderpaymentError) as exc_info:
        await worker.execute(task_vars)

    error = exc_info.value
    assert error.details["underpayment_amount"] == 200.00
    assert error.details["requires_collection"] is True


@pytest.mark.asyncio
async def test_small_underpayment_no_collection(worker):
    """Test small underpayment below collection threshold."""
    task_vars = {
        "payment_id": "pay-003",
        "claim_id": "claim-003",
        "payment_amount": 995.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "glosa_amount": 0.00,
    }

    result = await worker.execute(task_vars)

    assert result["underpayment_amount"] == 5.00
    assert result["requires_collection"] is False
