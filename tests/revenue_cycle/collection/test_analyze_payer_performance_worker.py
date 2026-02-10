"""Tests for AnalyzePayerPerformanceWorker."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.workers.analyze_payer_performance_worker import (
    AnalyzePayerPerformanceWorker,
)


@pytest.mark.asyncio
async def test_analyze_payer_performance_success():
    """Test successful payer performance analysis."""
    worker = AnalyzePayerPerformanceWorker()

    task_variables = {
        "payers": [
            {
                "payer_id": "payer-1",
                "payer_name": "Bradesco Saúde",
                "avg_payment_time_days": 25.0,
                "total_claims": 100,
                "denied_claims": 5,
                "amount_billed": 100000.0,
                "amount_collected": 95000.0,
                "days_sales_outstanding": 30.0,
            },
            {
                "payer_id": "payer-2",
                "payer_name": "Amil",
                "avg_payment_time_days": 45.0,
                "total_claims": 80,
                "denied_claims": 12,
                "amount_billed": 80000.0,
                "amount_collected": 68000.0,
                "days_sales_outstanding": 50.0,
            },
        ]
    }

    result = await worker.execute(task_variables)

    assert len(result["payers"]) == 2
    assert result["total_payers_analyzed"] == 2

    # Best performer should be payer-1 (better metrics)
    best = result["best_performer"]
    assert best["payer_id"] == "payer-1"
    assert best["performance_score"] > result["worst_performer"]["performance_score"]

    # Check calculated metrics
    payer1 = result["payers"][0]
    assert payer1["denial_rate"] == 5.0
    assert payer1["collection_rate"] == 95.0


@pytest.mark.asyncio
async def test_analyze_payer_performance_empty():
    """Test handling of empty payers list."""
    worker = AnalyzePayerPerformanceWorker()

    task_variables = {"payers": []}

    result = await worker.execute(task_variables)

    assert result["payers"] == []
    assert result["best_performer"] is None
    assert result["worst_performer"] is None
    assert result["total_payers_analyzed"] == 0


@pytest.mark.asyncio
async def test_analyze_payer_performance_zero_division():
    """Test handling of zero values."""
    worker = AnalyzePayerPerformanceWorker()

    task_variables = {
        "payers": [
            {
                "payer_id": "payer-1",
                "payer_name": "Test Payer",
                "avg_payment_time_days": 30.0,
                "total_claims": 0,  # Zero claims
                "denied_claims": 0,
                "amount_billed": 0.0,  # Zero billed
                "amount_collected": 0.0,
                "days_sales_outstanding": 0.0,
            }
        ]
    }

    result = await worker.execute(task_variables)

    payer = result["payers"][0]
    assert payer["denial_rate"] == 0.0
    assert payer["collection_rate"] == 0.0
