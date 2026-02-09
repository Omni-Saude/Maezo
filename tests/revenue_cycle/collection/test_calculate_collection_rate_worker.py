"""Tests for CalculateCollectionRateWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.calculate_collection_rate_worker import (
    CalculateCollectionRateWorker,
)


@pytest.mark.asyncio
async def test_calculate_collection_rate_success():
    """Test successful collection rate calculation."""
    worker = CalculateCollectionRateWorker()

    task_variables = {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "amount_billed": 100000.0,
        "amount_collected": 85000.0,
    }

    result = await worker.execute(task_variables)

    assert result["collection_rate"] == 85.0
    assert result["amount_billed"] == 100000.0
    assert result["amount_collected"] == 85000.0
    assert result["uncollected"] == 15000.0
    assert result["period_start"] == "2024-01-01"
    assert result["period_end"] == "2024-01-31"


@pytest.mark.asyncio
async def test_calculate_collection_rate_with_payer():
    """Test collection rate calculation for specific payer."""
    worker = CalculateCollectionRateWorker()

    task_variables = {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "amount_billed": 50000.0,
        "amount_collected": 48000.0,
        "payer_id": "payer-123",
    }

    result = await worker.execute(task_variables)

    assert result["collection_rate"] == 96.0
    assert result["payer_id"] == "payer-123"
    assert result["uncollected"] == 2000.0


@pytest.mark.asyncio
async def test_calculate_collection_rate_zero_billed():
    """Test handling of zero amount billed."""
    worker = CalculateCollectionRateWorker()

    task_variables = {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "amount_billed": 0.0,
        "amount_collected": 0.0,
    }

    result = await worker.execute(task_variables)

    assert result["collection_rate"] == 0.0
    assert result["uncollected"] == 0.0


@pytest.mark.asyncio
async def test_calculate_collection_rate_overcollection():
    """Test handling of overcollection (refunds, adjustments)."""
    worker = CalculateCollectionRateWorker()

    task_variables = {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "amount_billed": 100000.0,
        "amount_collected": 105000.0,  # Over 100%
    }

    result = await worker.execute(task_variables)

    assert result["collection_rate"] == 105.0
    assert result["uncollected"] == -5000.0  # Negative = overcollection
