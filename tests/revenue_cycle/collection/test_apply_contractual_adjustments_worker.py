"""Tests for ApplyContractualAdjustmentsWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from healthcare_platform.revenue_cycle.collection.workers.apply_contractual_adjustments_worker import (
    ApplyContractualAdjustmentsWorker,
)


@pytest.fixture
def worker():
    """Create worker instance."""
    return ApplyContractualAdjustmentsWorker()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.apply_contractual_adjustments_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.apply_contractual_adjustments_worker.FederatedDMNService')
async def test_contractual_adjustment_applied(MockDMNService, mock_tenant):
    """Test successful contractual adjustment."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'allocationId': 'alloc-123'
    }

    worker = ApplyContractualAdjustmentsWorker()
    job = MagicMock()
    job.key = 'job-key-123'
    job.variables = {
        "payment_id": str(uuid4()),
        "claim_id": str(uuid4()),
        "billed_amount": 1000.00,  # Hospital table
        "contracted_amount": 850.00,  # Payer contracted rate
        "payment_amount": 850.00,
        "currency": "BRL",
        "payer_id": str(uuid4()),
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["contractual_discount"] == 150.00
    assert result.variables["discount_percent"] == 15.0
    assert result.variables["adjustment_applied"] is True
    assert result.variables["final_amount"] == 850.00


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.apply_contractual_adjustments_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.apply_contractual_adjustments_worker.FederatedDMNService')
async def test_variance_in_payment(MockDMNService, mock_tenant):
    """Test when payment doesn't match contracted amount."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'allocationId': 'alloc-456'
    }

    worker = ApplyContractualAdjustmentsWorker()
    job = MagicMock()
    job.key = 'job-key-456'
    job.variables = {
        "payment_id": str(uuid4()),
        "claim_id": str(uuid4()),
        "billed_amount": 1000.00,
        "contracted_amount": 850.00,
        "payment_amount": 800.00,  # Less than contracted
        "currency": "BRL",
        "payer_id": str(uuid4()),
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["contractual_discount"] == 150.00
    assert result.variables["adjustment_applied"] is False
    assert result.variables["variance"] == -50.00
