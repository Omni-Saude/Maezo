"""Tests for HandleOverpaymentWorker."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.exceptions import OverpaymentError
from healthcare_platform.revenue_cycle.collection.workers.handle_overpayment_worker import HandleOverpaymentWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return HandleOverpaymentWorker()


@pytest.mark.asyncio
async def test_overpayment_raises_error(worker):
    """Test that overpayment raises OverpaymentError."""
    task_vars = {
        "payment_id": "pay-001",
        "claim_id": "claim-001",
        "payment_amount": 1200.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "payer_id": "payer-001",
    }

    with pytest.raises(OverpaymentError) as exc_info:
        await worker.execute(task_vars)

    error = exc_info.value
    assert "revisão manual" in str(error).lower()
    assert error.details["overpayment_amount"] == 200.00
    assert error.details["credit_note_id"] is not None
    assert error.details["requires_review"] is True


@pytest.mark.asyncio
async def test_overpayment_creates_credit_note(worker):
    """Test that credit note is created for overpayment."""
    task_vars = {
        "payment_id": "pay-002",
        "claim_id": "claim-002",
        "payment_amount": 1500.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "payer_id": "payer-002",
    }

    with pytest.raises(OverpaymentError) as exc_info:
        await worker.execute(task_vars)

    assert exc_info.value.details["credit_note_id"].startswith("CN-")
    assert exc_info.value.details["overpayment_amount"] == 500.00
