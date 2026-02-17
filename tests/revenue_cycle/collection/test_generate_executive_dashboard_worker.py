"""Tests for GenerateExecutiveDashboardWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.generate_executive_dashboard_worker import (
    GenerateExecutiveDashboardWorker,
)


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_executive_dashboard_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_executive_dashboard_worker.FederatedDMNService")
async def test_generate_executive_dashboard_success(mock_dmn_service_cls, mock_tenant):
    """Test successful dashboard generation."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    worker = GenerateExecutiveDashboardWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    assert result.variables["collection_rate"] == 85.5
    assert result.variables["dso"] == 45.2
    assert result.variables["total_ar"] == 500000.0
    assert result.variables["current_month_collected"] == 250000.0

    # Check aging distribution
    assert len(result.variables["aging_distribution"]) == 3
    aging_total = sum(a["percentage"] for a in result.variables["aging_distribution"])
    assert pytest.approx(aging_total, 0.1) == 100.0

    # Check top payers (should have 3)
    assert len(result.variables["top_payers"]) == 3
    assert result.variables["top_payers"][0]["payer_name"] == "Bradesco"  # Highest collected

    # Check revenue forecast
    assert result.variables["revenue_forecast"] > 0


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_executive_dashboard_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_executive_dashboard_worker.FederatedDMNService")
async def test_generate_executive_dashboard_minimal(mock_dmn_service_cls, mock_tenant):
    """Test dashboard generation with minimal data."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    worker = GenerateExecutiveDashboardWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    assert result.variables["collection_rate"] == 80.0
    assert len(result.variables["top_payers"]) == 1
    # Forecast should be based on current month + 5%
    assert result.variables["revenue_forecast"] == pytest.approx(5250.0, 0.1)


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_executive_dashboard_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_executive_dashboard_worker.FederatedDMNService")
async def test_generate_executive_dashboard_zero_aging(mock_dmn_service_cls, mock_tenant):
    """Test handling of zero aging amounts."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    worker = GenerateExecutiveDashboardWorker()
    job = MagicMock()
    job.variables = {
        "collection_rate": 90.0,
        "dso": 30.0,
        "aging_buckets": [],  # Empty aging
        "payers": [],
        "total_ar": 0.0,
        "current_month_collected": 0.0,
        "historical_collections": [1000.0, 2000.0, 3000.0],
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["aging_distribution"] == []
    assert result.variables["top_payers"] == []
    assert result.variables["revenue_forecast"] > 0
