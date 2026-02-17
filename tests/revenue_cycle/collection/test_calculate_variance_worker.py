"""Tests for CalculateVarianceWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker import CalculateVarianceWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return CalculateVarianceWorker()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker.FederatedDMNService')
async def test_positive_variance_overpayment(MockDMNService, mock_tenant):
    """Test positive variance (overpayment)."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateVarianceWorker()
    job = MagicMock()
    job.variables = {
        "expected_amount": 1000.00,
        "actual_amount": 1100.00,
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["variance"] == 100.00
    assert result.variables["variance_percent"] == 10.0
    assert result.variables["is_positive"] is True
    assert result.variables["is_negative"] is False
    assert result.variables["is_exact"] is False


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker.FederatedDMNService')
async def test_negative_variance_underpayment(MockDMNService, mock_tenant):
    """Test negative variance (underpayment)."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateVarianceWorker()
    job = MagicMock()
    job.variables = {
        "expected_amount": 1000.00,
        "actual_amount": 900.00,
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["variance"] == -100.00
    assert result.variables["variance_percent"] == -10.0
    assert result.variables["is_positive"] is False
    assert result.variables["is_negative"] is True


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker.FederatedDMNService')
async def test_exact_match(MockDMNService, mock_tenant):
    """Test exact amount match."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateVarianceWorker()
    job = MagicMock()
    job.variables = {
        "expected_amount": 1000.00,
        "actual_amount": 1000.00,
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["variance"] == 0.00
    assert result.variables["is_exact"] is True
    assert result.variables["tolerance_met"] is True


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_variance_worker.FederatedDMNService')
async def test_within_tolerance(MockDMNService, mock_tenant):
    """Test amount within 1% tolerance."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateVarianceWorker()
    job = MagicMock()
    job.variables = {
        "expected_amount": 1000.00,
        "actual_amount": 1005.00,  # 0.5% variance
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["tolerance_met"] is True
