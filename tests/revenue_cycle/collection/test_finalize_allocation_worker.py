"""Tests for FinalizeAllocationWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.exceptions import PaymentAllocationError
from healthcare_platform.revenue_cycle.collection.workers.finalize_allocation_worker import FinalizeAllocationWorker


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.finalize_allocation_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.finalize_allocation_worker.FederatedDMNService")
async def test_finalize_allocation_success(mock_dmn_service_cls, mock_tenant):
    """Test successful allocation finalization."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    worker = FinalizeAllocationWorker()
    job = MagicMock()
    job.variables = {
        "allocation_id": "ALLOC-001",
        "locked_by": "system",
        "allocation_data": {},  # Not previously locked
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["allocation_id"] == "ALLOC-001"
    assert result.variables["status"] == "locked"
    assert result.variables["locked_by"] == "system"
    assert result.variables["finalized"] is True
    assert result.variables["locked_at"] is not None


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.finalize_allocation_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.finalize_allocation_worker.FederatedDMNService")
async def test_finalize_already_locked_raises_error(mock_dmn_service_cls, mock_tenant):
    """Test that finalizing already locked allocation raises error."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    worker = FinalizeAllocationWorker()
    job = MagicMock()
    job.variables = {
        "allocation_id": "ALLOC-002",
        "locked_by": "user-123",
        "force_lock": False,
        "allocation_data": {
            "locked_at": "2024-01-15T10:00:00Z",
            "locked_by": "user-456",
        },
    }

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "PAYMENT_ALLOCATION_FAILED"
    assert "já está bloqueada" in result.error_message.lower()


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.finalize_allocation_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.finalize_allocation_worker.FederatedDMNService")
async def test_force_lock_overrides(mock_dmn_service_cls, mock_tenant):
    """Test that force_lock allows re-locking."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    worker = FinalizeAllocationWorker()
    job = MagicMock()
    job.variables = {
        "allocation_id": "ALLOC-003",
        "locked_by": "admin",
        "force_lock": True,
        "allocation_data": {
            "locked_at": "2024-01-15T10:00:00Z",
            "locked_by": "user-456",
        },
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["finalized"] is True
    assert result.variables["locked_by"] == "admin"
