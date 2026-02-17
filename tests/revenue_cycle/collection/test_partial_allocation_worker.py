"""Tests for PartialAllocationWorker."""
from __future__ import annotations

from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.partial_allocation_worker import PartialAllocationWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return PartialAllocationWorker()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.partial_allocation_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.partial_allocation_worker.FederatedDMNService')
async def test_partial_allocation_success(mock_dmn_service, mock_tenant, worker):
    """Test partial allocation across multiple claims."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'adjustment_applied': False, 'allocation_valid': True}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "payment_amount": 1500.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": str(uuid4()), "outstanding_amount": 1000.00, "due_date": "2024-01-01"},
            {"claim_id": str(uuid4()), "outstanding_amount": 800.00, "due_date": "2024-01-02"},
        ],
    }

    result = await worker.execute(job)

    assert result.success is True
    assert len(result.variables["allocations"]) == 2
    assert result.variables["total_allocated"] == 1500.00
    assert result.variables["remaining_amount"] == 0.00


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.partial_allocation_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.partial_allocation_worker.FederatedDMNService')
async def test_full_allocation_of_one_claim(mock_dmn_service, mock_tenant, worker):
    """Test full allocation to single claim."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'adjustment_applied': False, 'allocation_valid': True}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": str(uuid4()), "outstanding_amount": 1000.00, "due_date": "2024-01-01"}
        ],
    }

    result = await worker.execute(job)

    assert result.success is True
    assert len(result.variables["allocations"]) == 1
    assert result.variables["total_allocated"] == 1000.00
    assert result.variables["remaining_amount"] == 0.00
    # Check if fully paid
    assert result.variables["allocations"][0]["fully_paid"] is True


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.partial_allocation_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.partial_allocation_worker.FederatedDMNService')
async def test_insufficient_amount_for_all_claims(mock_dmn_service, mock_tenant, worker):
    """Test when payment doesn't cover all claims."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'adjustment_applied': False, 'allocation_valid': True}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "payment_amount": 500.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": str(uuid4()), "outstanding_amount": 1000.00, "due_date": "2024-01-01"},
            {"claim_id": str(uuid4()), "outstanding_amount": 800.00, "due_date": "2024-01-02"},
        ],
    }

    result = await worker.execute(job)

    assert result.success is True
    assert len(result.variables["allocations"]) == 1  # Only first claim partially paid
    assert result.variables["total_allocated"] == 500.00
    assert result.variables["remaining_amount"] == 0.00
    # Check if partially paid
    assert result.variables["allocations"][0]["fully_paid"] is False
