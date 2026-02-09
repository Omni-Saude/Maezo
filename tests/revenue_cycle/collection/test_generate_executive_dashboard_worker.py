"""Tests for GenerateExecutiveDashboardWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.generate_executive_dashboard_worker import (
    GenerateExecutiveDashboardWorker,
)


@pytest.mark.asyncio
async def test_generate_executive_dashboard_success():
    """Test successful dashboard generation."""
    worker = GenerateExecutiveDashboardWorker()

    task_variables = {
        "collection_rate": 85.5,
        "dso": 45.2,
        "aging_buckets": [
            {"bucket": "0-30", "amount": 50000.0, "count": 100},
            {"bucket": "31-60", "amount": 30000.0, "count": 50},
            {"bucket": "61-90", "amount": 20000.0, "count": 30},
        ],
        "payers": [
            {
                "payer_id": "payer-1",
                "payer_name": "Bradesco",
                "amount_collected": 100000.0,
                "collection_rate": 90.0,
            },
            {
                "payer_id": "payer-2",
                "payer_name": "Amil",
                "amount_collected": 80000.0,
                "collection_rate": 85.0,
            },
            {
                "payer_id": "payer-3",
                "payer_name": "Unimed",
                "amount_collected": 75000.0,
                "collection_rate": 88.0,
            },
        ],
        "total_ar": 500000.0,
        "current_month_collected": 250000.0,
        "historical_collections": [240000.0, 245000.0, 250000.0],
    }

    result = await worker.execute(task_variables)

    assert result["collection_rate"] == 85.5
    assert result["dso"] == 45.2
    assert result["total_ar"] == 500000.0
    assert result["current_month_collected"] == 250000.0

    # Check aging distribution
    assert len(result["aging_distribution"]) == 3
    aging_total = sum(a["percentage"] for a in result["aging_distribution"])
    assert pytest.approx(aging_total, 0.1) == 100.0

    # Check top payers (should have 3)
    assert len(result["top_payers"]) == 3
    assert result["top_payers"][0]["payer_name"] == "Bradesco"  # Highest collected

    # Check revenue forecast
    assert result["revenue_forecast"] > 0


@pytest.mark.asyncio
async def test_generate_executive_dashboard_minimal():
    """Test dashboard generation with minimal data."""
    worker = GenerateExecutiveDashboardWorker()

    task_variables = {
        "collection_rate": 80.0,
        "dso": 40.0,
        "aging_buckets": [
            {"bucket": "0-30", "amount": 10000.0, "count": 10},
        ],
        "payers": [
            {
                "payer_id": "payer-1",
                "payer_name": "Test Payer",
                "amount_collected": 5000.0,
                "collection_rate": 80.0,
            }
        ],
        "total_ar": 20000.0,
        "current_month_collected": 5000.0,
        "historical_collections": [],  # No history
    }

    result = await worker.execute(task_variables)

    assert result["collection_rate"] == 80.0
    assert len(result["top_payers"]) == 1
    # Forecast should be based on current month + 5%
    assert result["revenue_forecast"] == pytest.approx(5250.0, 0.1)


@pytest.mark.asyncio
async def test_generate_executive_dashboard_zero_aging():
    """Test handling of zero aging amounts."""
    worker = GenerateExecutiveDashboardWorker()

    task_variables = {
        "collection_rate": 90.0,
        "dso": 30.0,
        "aging_buckets": [],  # Empty aging
        "payers": [],
        "total_ar": 0.0,
        "current_month_collected": 0.0,
        "historical_collections": [1000.0, 2000.0, 3000.0],
    }

    result = await worker.execute(task_variables)

    assert result["aging_distribution"] == []
    assert result["top_payers"] == []
    assert result["revenue_forecast"] > 0
