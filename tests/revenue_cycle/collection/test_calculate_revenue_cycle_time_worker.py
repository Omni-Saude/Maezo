"""Tests for CalculateRevenueCycleTimeWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker import (
    CalculateRevenueCycleTimeWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker.FederatedDMNService')
async def test_calculate_revenue_cycle_time_success(MockDMNService, mock_tenant):
    """Test successful revenue cycle time calculation."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateRevenueCycleTimeWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    assert "avg_cycle_time_days" in result.variables
    assert result.variables["min_cycle_time_days"] == 29
    assert result.variables["max_cycle_time_days"] == 46
    assert result.variables["total_encounters"] == 3


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker.FederatedDMNService')
async def test_calculate_revenue_cycle_time_single_payer(MockDMNService, mock_tenant):
    """Test revenue cycle time for specific payer."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateRevenueCycleTimeWorker()
    job = MagicMock()
    job.variables = {
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

    result = await worker.execute(job)

    assert result.success
    assert result.variables["total_encounters"] == 2
    assert result.variables["payer_id"] == "payer-1"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker.get_required_tenant', return_value='test-tenant')
async def test_calculate_revenue_cycle_time_empty(mock_tenant):
    """Test handling of empty encounters list."""
    worker = CalculateRevenueCycleTimeWorker()
    job = MagicMock()
    job.variables = {"encounters": []}

    result = await worker.execute(job)

    assert result.success
    assert result.variables["avg_cycle_time_days"] == 0.0
    assert result.variables["total_encounters"] == 0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker.FederatedDMNService')
async def test_calculate_revenue_cycle_time_filtered_out(MockDMNService, mock_tenant):
    """Test handling when all encounters are filtered out."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateRevenueCycleTimeWorker()
    job = MagicMock()
    job.variables = {
        "encounters": [
            {
                "encounter_date": "2024-01-01T00:00:00Z",
                "payment_date": "2024-01-30T00:00:00Z",
                "payer_id": "payer-1",
            }
        ],
        "payer_id": "payer-999",  # No matches
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["total_encounters"] == 0
