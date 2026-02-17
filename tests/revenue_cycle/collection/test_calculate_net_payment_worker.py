"""Tests for CalculateNetPaymentWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker import (
    CalculateNetPaymentWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.FederatedDMNService')
async def test_calculate_net_payment_success(MockDMNService, mock_tenant):
    """Test successful net payment calculation."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateNetPaymentWorker()
    job = MagicMock()
    job.variables = {
        "gross_amount": "1000.00",
        "bank_fees": "10.00",
        "tax_withholding": "40.00",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["net_amount"] == "950.00"
    assert result.variables["bank_fees"] == "10.00"
    assert result.variables["tax_withholding"] == "40.00"
    assert result.variables["currency"] == "BRL"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.FederatedDMNService')
async def test_calculate_net_payment_no_fees(MockDMNService, mock_tenant):
    """Test calculation with no fees or taxes."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateNetPaymentWorker()
    job = MagicMock()
    job.variables = {
        "gross_amount": "500.00",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["net_amount"] == "500.00"
    assert result.variables["bank_fees"] == "0"
    assert result.variables["tax_withholding"] == "0"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.FederatedDMNService')
async def test_calculate_net_payment_negative_result(MockDMNService, mock_tenant):
    """Test calculation fails when net amount would be negative."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateNetPaymentWorker()
    job = MagicMock()
    job.variables = {
        "gross_amount": "100.00",
        "bank_fees": "50.00",
        "tax_withholding": "60.00",  # Total deductions exceed gross
    }

    result = await worker.execute(job)

    assert not result.success
    assert result.error_code == 'NEGATIVE_NET_AMOUNT'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.FederatedDMNService')
async def test_calculate_net_payment_zero_gross(MockDMNService, mock_tenant):
    """Test calculation with zero gross amount."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateNetPaymentWorker()
    job = MagicMock()
    job.variables = {
        "gross_amount": "0.00",
        "bank_fees": "0.00",
        "tax_withholding": "0.00",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["net_amount"] == "0.00"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker.FederatedDMNService')
async def test_calculate_net_payment_invalid_amount_format(MockDMNService, mock_tenant):
    """Test calculation fails with invalid amount format."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CalculateNetPaymentWorker()
    job = MagicMock()
    job.variables = {
        "gross_amount": "invalid",
    }

    # The worker will catch the Decimal conversion error and return a failure result
    result = await worker.execute(job)
    assert not result.success
