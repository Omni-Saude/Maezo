"""Tests for CalculateRevenueCycleTimeWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker import (
    CalculateRevenueCycleTimeWorker,
)


@pytest.mark.asyncio
async def test_calculate_revenue_cycle_time_success():
    """Test successful revenue cycle time calculation."""
    worker = CalculateRevenueCycleTimeWorker()

    task_variables = {
        "encounters": [
            {
                "encounter_date": "2024-01-01T00:00:00Z",
                "payment_date": "2024-01-30T00:00:00Z",
                "payer_id": "payer-1",
            },
            {
                "encounter_date": "2024-01-05T00:00:00Z",
                "payment_date": "2024-02-04T00:00:00Z",
                "payer_id": "payer-1",
            },
            {
                "encounter_date": "2024-01-10T00:00:00Z",
                "payment_date": "2024-02-25T00:00:00Z",
                "payer_id": "payer-2",
            },
        ]
    }

    result = await worker.execute(task_variables)

    assert "avg_cycle_time_days" in result
    assert result["min_cycle_time_days"] == 29
    assert result["max_cycle_time_days"] == 46
    assert result["total_encounters"] == 3
    assert "by_payer" in result
    assert "payer-1" in result["by_payer"]
    assert "payer-2" in result["by_payer"]


@pytest.mark.asyncio
async def test_calculate_revenue_cycle_time_single_payer():
    """Test revenue cycle time for specific payer."""
    worker = CalculateRevenueCycleTimeWorker()

    task_variables = {
        "encounters": [
            {
                "encounter_date": "2024-01-01T00:00:00Z",
                "payment_date": "2024-01-30T00:00:00Z",
                "payer_id": "payer-1",
            },
            {
                "encounter_date": "2024-01-05T00:00:00Z",
                "payment_date": "2024-02-04T00:00:00Z",
                "payer_id": "payer-1",
            },
            {
                "encounter_date": "2024-01-10T00:00:00Z",
                "payment_date": "2024-02-25T00:00:00Z",
                "payer_id": "payer-2",
            },
        ],
        "payer_id": "payer-1",
    }

    result = await worker.execute(task_variables)

    assert result["total_encounters"] == 2
    assert result["payer_id"] == "payer-1"
    assert "by_payer" not in result


@pytest.mark.asyncio
async def test_calculate_revenue_cycle_time_empty():
    """Test handling of empty encounters list."""
    worker = CalculateRevenueCycleTimeWorker()

    task_variables = {"encounters": []}

    result = await worker.execute(task_variables)

    assert result["avg_cycle_time_days"] == 0.0
    assert result["total_encounters"] == 0


@pytest.mark.asyncio
async def test_calculate_revenue_cycle_time_filtered_out():
    """Test handling when all encounters are filtered out."""
    worker = CalculateRevenueCycleTimeWorker()

    task_variables = {
        "encounters": [
            {
                "encounter_date": "2024-01-01T00:00:00Z",
                "payment_date": "2024-01-30T00:00:00Z",
                "payer_id": "payer-1",
            }
        ],
        "payer_id": "payer-999",  # No matches
    }

    result = await worker.execute(task_variables)

    assert result["total_encounters"] == 0
