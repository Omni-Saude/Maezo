"""Tests for EscalateUnmatchedWorker."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.exceptions import UnmatchedPaymentError
from healthcare_platform.revenue_cycle.collection.workers.escalate_unmatched_worker import EscalateUnmatchedWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return EscalateUnmatchedWorker()


@pytest.mark.asyncio
async def test_escalate_unmatched_raises_error(worker):
    """Test that unmatched payment raises error for manual review."""
    task_vars = {
        "payment_id": "pay-001",
        "payment_amount": 1500.00,
        "currency": "BRL",
        "payer_id": "payer-001",
        "attempted_strategies": ["protocol", "invoice", "patient"],
        "payment_date": "2024-01-15",
        "transaction_id": "TXN-12345",
        "notes": "Unable to match automatically",
    }

    with pytest.raises(UnmatchedPaymentError) as exc_info:
        await worker.execute(task_vars)

    error = exc_info.value
    assert "revisão manual" in str(error).lower()
    assert error.details["escalation_id"].startswith("ESC-")
    assert error.details["requires_manual_review"] is True
    assert error.details["status"] == "escalated"


@pytest.mark.asyncio
async def test_escalation_includes_context(worker):
    """Test that escalation includes full context."""
    task_vars = {
        "payment_id": "pay-002",
        "payment_amount": 2000.00,
        "currency": "BRL",
        "payer_id": "payer-002",
        "attempted_strategies": ["protocol", "invoice"],
        "transaction_id": "TXN-67890",
    }

    with pytest.raises(UnmatchedPaymentError) as exc_info:
        await worker.execute(task_vars)

    context = exc_info.value.details["context"]
    assert context["payment_id"] == "pay-002"
    assert context["payment_amount"] == 2000.00
    assert len(context["attempted_strategies"]) == 2
