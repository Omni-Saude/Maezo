"""Tests for CalculateCollectionRateWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.calculate_collection_rate_worker import (
    CalculateCollectionRateWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_collection_rate_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_collection_rate_worker.FederatedDMNService')
async def test_calculate_collection_rate_success(MockDMNService, mock_tenant):
    """Test successful collection rate calculation."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateCollectionRateWorker()
    job = MagicMock()
    job.variables = {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "amount_billed": 100000.0,
        "amount_collected": 85000.0,
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["collection_rate"] == 85.0
    assert result.variables["amount_billed"] == 100000.0
    assert result.variables["amount_collected"] == 85000.0
    assert result.variables["uncollected"] == 15000.0
    assert result.variables["period_start"] == "2024-01-01"
    assert result.variables["period_end"] == "2024-01-31"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_collection_rate_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_collection_rate_worker.FederatedDMNService')
async def test_calculate_collection_rate_with_payer(MockDMNService, mock_tenant):
    """Test collection rate calculation for specific payer."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateCollectionRateWorker()
    job = MagicMock()
    job.variables = {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "amount_billed": 50000.0,
        "amount_collected": 48000.0,
        "payer_id": "payer-123",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["collection_rate"] == 96.0
    assert result.variables["payer_id"] == "payer-123"
    assert result.variables["uncollected"] == 2000.0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_collection_rate_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_collection_rate_worker.FederatedDMNService')
async def test_calculate_collection_rate_zero_billed(MockDMNService, mock_tenant):
    """Test handling of zero amount billed."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateCollectionRateWorker()
    job = MagicMock()
    job.variables = {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "amount_billed": 0.0,
        "amount_collected": 0.0,
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["collection_rate"] == 0.0
    assert result.variables["uncollected"] == 0.0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_collection_rate_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_collection_rate_worker.FederatedDMNService')
async def test_calculate_collection_rate_overcollection(MockDMNService, mock_tenant):
    """Test handling of overcollection (refunds, adjustments)."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateCollectionRateWorker()
    job = MagicMock()
    job.variables = {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "amount_billed": 100000.0,
        "amount_collected": 105000.0,  # Over 100%
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["collection_rate"] == 105.0
    assert result.variables["uncollected"] == -5000.0  # Negative = overcollection
