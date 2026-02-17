"""Tests for AnalyzePayerPerformanceWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.analyze_payer_performance_worker import (
    AnalyzePayerPerformanceWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.analyze_payer_performance_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.analyze_payer_performance_worker.FederatedDMNService')
async def test_analyze_payer_performance_success(MockDMNService, mock_tenant):
    """Test successful payer performance analysis."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'payerMetrics': [
            {
                "payer_id": "payer-1",
                "payer_name": "Bradesco Saúde",
                "denial_rate": 5.0,
                "collection_rate": 95.0,
                "performance_score": 92.0
            },
            {
                "payer_id": "payer-2",
                "payer_name": "Amil",
                "denial_rate": 15.0,
                "collection_rate": 85.0,
                "performance_score": 75.0
            }
        ],
        'bestPerformer': {"payer_id": "payer-1", "performance_score": 92.0},
        'worstPerformer': {"payer_id": "payer-2", "performance_score": 75.0}
    }

    worker = AnalyzePayerPerformanceWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    assert len(result.variables["payers"]) == 2
    assert result.variables["total_payers_analyzed"] == 2

    # Best performer should be payer-1 (better metrics)
    best = result.variables["best_performer"]
    assert best["payer_id"] == "payer-1"
    assert best["performance_score"] > result.variables["worst_performer"]["performance_score"]

    # Check calculated metrics
    payer1 = result.variables["payers"][0]
    assert payer1["denial_rate"] == 5.0
    assert payer1["collection_rate"] == 95.0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.analyze_payer_performance_worker.get_required_tenant', return_value='test-tenant')
async def test_analyze_payer_performance_empty(mock_tenant):
    """Test handling of empty payers list."""
    worker = AnalyzePayerPerformanceWorker()
    job = MagicMock()
    job.variables = {"payers": []}

    result = await worker.execute(job)

    assert result.success
    assert result.variables["payers"] == []
    assert result.variables["best_performer"] is None
    assert result.variables["worst_performer"] is None
    assert result.variables["total_payers_analyzed"] == 0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.analyze_payer_performance_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.analyze_payer_performance_worker.FederatedDMNService')
async def test_analyze_payer_performance_zero_division(MockDMNService, mock_tenant):
    """Test handling of zero values."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'payerMetrics': [
            {
                "payer_id": "payer-1",
                "payer_name": "Test Payer",
                "denial_rate": 0.0,
                "collection_rate": 0.0,
                "performance_score": 0.0
            }
        ],
        'bestPerformer': {"payer_id": "payer-1", "performance_score": 0.0},
        'worstPerformer': {"payer_id": "payer-1", "performance_score": 0.0}
    }

    worker = AnalyzePayerPerformanceWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    payer = result.variables["payers"][0]
    assert payer["denial_rate"] == 0.0
    assert payer["collection_rate"] == 0.0
