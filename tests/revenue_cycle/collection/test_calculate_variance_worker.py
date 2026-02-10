"""Tests for CalculateVarianceWorker."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker import CalculateVarianceWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return CalculateVarianceWorker()


@pytest.mark.asyncio
async def test_positive_variance_overpayment(worker):
    """Test positive variance (overpayment)."""
    task_vars = {
        "expected_amount": 1000.00,
        "actual_amount": 1100.00,
        "currency": "BRL",
    }

    result = await worker.execute(task_vars)

    assert result["variance"] == 100.00
    assert result["variance_percent"] == 10.0
    assert result["is_positive"] is True
    assert result["is_negative"] is False
    assert result["is_exact"] is False


@pytest.mark.asyncio
async def test_negative_variance_underpayment(worker):
    """Test negative variance (underpayment)."""
    task_vars = {
        "expected_amount": 1000.00,
        "actual_amount": 900.00,
        "currency": "BRL",
    }

    result = await worker.execute(task_vars)

    assert result["variance"] == -100.00
    assert result["variance_percent"] == -10.0
    assert result["is_positive"] is False
    assert result["is_negative"] is True


@pytest.mark.asyncio
async def test_exact_match(worker):
    """Test exact amount match."""
    task_vars = {
        "expected_amount": 1000.00,
        "actual_amount": 1000.00,
        "currency": "BRL",
    }

    result = await worker.execute(task_vars)

    assert result["variance"] == 0.00
    assert result["is_exact"] is True
    assert result["tolerance_met"] is True


@pytest.mark.asyncio
async def test_within_tolerance(worker):
    """Test amount within 1% tolerance."""
    task_vars = {
        "expected_amount": 1000.00,
        "actual_amount": 1005.00,  # 0.5% variance
        "currency": "BRL",
    }

    result = await worker.execute(task_vars)

    assert result["tolerance_met"] is True
