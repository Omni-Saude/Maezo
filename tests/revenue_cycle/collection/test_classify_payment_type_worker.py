"""Tests for ClassifyPaymentTypeWorker."""
from __future__ import annotations

from decimal import Decimal

import pytest

from platform.revenue_cycle.collection.workers.classify_payment_type_worker import (
    ClassifyPaymentTypeWorker,
)


@pytest.mark.asyncio
async def test_classify_payment_full():
    """Test classification as full payment."""
    worker = ClassifyPaymentTypeWorker()

    task_vars = {
        "net_amount": "1000.00",
        "expected_amount": "1000.00",
    }

    result = await worker.execute(task_vars)

    assert result["payment_type"] == "full"
    assert "ratio" in result["classification_reason"]


@pytest.mark.asyncio
async def test_classify_payment_partial():
    """Test classification as partial payment."""
    worker = ClassifyPaymentTypeWorker()

    task_vars = {
        "net_amount": "500.00",
        "expected_amount": "1000.00",
    }

    result = await worker.execute(task_vars)

    assert result["payment_type"] == "partial"
    assert "0.5" in result["payment_ratio"]


@pytest.mark.asyncio
async def test_classify_payment_advance_no_expected():
    """Test classification as advance when no expected amount."""
    worker = ClassifyPaymentTypeWorker()

    task_vars = {
        "net_amount": "1000.00",
    }

    result = await worker.execute(task_vars)

    assert result["payment_type"] == "advance"
    assert result["classification_reason"] == "no_expected_amount"


@pytest.mark.asyncio
async def test_classify_payment_advance_zero_expected():
    """Test classification as advance when expected is zero."""
    worker = ClassifyPaymentTypeWorker()

    task_vars = {
        "net_amount": "500.00",
        "expected_amount": "0",
    }

    result = await worker.execute(task_vars)

    assert result["payment_type"] == "advance"


@pytest.mark.asyncio
async def test_classify_payment_full_with_threshold():
    """Test classification uses configurable threshold."""
    worker = ClassifyPaymentTypeWorker(full_threshold=Decimal("0.98"))

    task_vars = {
        "net_amount": "970.00",
        "expected_amount": "1000.00",
    }

    result = await worker.execute(task_vars)

    # 97% is below 98% threshold, should be partial
    assert result["payment_type"] == "partial"


@pytest.mark.asyncio
async def test_classify_payment_overpayment():
    """Test classification when payment exceeds expected."""
    worker = ClassifyPaymentTypeWorker()

    task_vars = {
        "net_amount": "1200.00",
        "expected_amount": "1000.00",
    }

    result = await worker.execute(task_vars)

    # Ratio 1.2 > 0.95 threshold = full payment
    assert result["payment_type"] == "full"
    assert "1.2" in result["payment_ratio"]
