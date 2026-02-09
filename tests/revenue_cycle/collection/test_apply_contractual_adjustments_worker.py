"""Tests for ApplyContractualAdjustmentsWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.apply_contractual_adjustments_worker import (
    ApplyContractualAdjustmentsWorker,
)


@pytest.fixture
def worker():
    """Create worker instance."""
    return ApplyContractualAdjustmentsWorker()


@pytest.mark.asyncio
async def test_contractual_adjustment_applied(worker):
    """Test successful contractual adjustment."""
    task_vars = {
        "payment_id": "pay-001",
        "claim_id": "claim-001",
        "billed_amount": 1000.00,  # Hospital table
        "contracted_amount": 850.00,  # Payer contracted rate
        "payment_amount": 850.00,
        "currency": "BRL",
        "payer_id": "payer-001",
    }

    result = await worker.execute(task_vars)

    assert result["contractual_discount"] == 150.00
    assert result["discount_percent"] == 15.0
    assert result["adjustment_applied"] is True
    assert result["final_amount"] == 850.00


@pytest.mark.asyncio
async def test_variance_in_payment(worker):
    """Test when payment doesn't match contracted amount."""
    task_vars = {
        "payment_id": "pay-002",
        "claim_id": "claim-002",
        "billed_amount": 1000.00,
        "contracted_amount": 850.00,
        "payment_amount": 800.00,  # Less than contracted
        "currency": "BRL",
        "payer_id": "payer-002",
    }

    result = await worker.execute(task_vars)

    assert result["contractual_discount"] == 150.00
    assert result["adjustment_applied"] is False
    assert result["variance"] == -50.00
