"""Tests for FinalizeAllocationWorker."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.exceptions import PaymentAllocationError
from healthcare_platform.revenue_cycle.collection.workers.finalize_allocation_worker import FinalizeAllocationWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return FinalizeAllocationWorker()


@pytest.mark.asyncio
async def test_finalize_allocation_success(worker):
    """Test successful allocation finalization."""
    task_vars = {
        "allocation_id": "ALLOC-001",
        "locked_by": "system",
        "allocation_data": {},  # Not previously locked
    }

    result = await worker.execute(task_vars)

    assert result["allocation_id"] == "ALLOC-001"
    assert result["status"] == "locked"
    assert result["locked_by"] == "system"
    assert result["finalized"] is True
    assert result["locked_at"] is not None


@pytest.mark.asyncio
async def test_finalize_already_locked_raises_error(worker):
    """Test that finalizing already locked allocation raises error."""
    task_vars = {
        "allocation_id": "ALLOC-002",
        "locked_by": "user-123",
        "force_lock": False,
        "allocation_data": {
            "locked_at": "2024-01-15T10:00:00Z",
            "locked_by": "user-456",
        },
    }

    with pytest.raises(PaymentAllocationError) as exc_info:
        await worker.execute(task_vars)

    assert "já está bloqueada" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_force_lock_overrides(worker):
    """Test that force_lock allows re-locking."""
    task_vars = {
        "allocation_id": "ALLOC-003",
        "locked_by": "admin",
        "force_lock": True,
        "allocation_data": {
            "locked_at": "2024-01-15T10:00:00Z",
            "locked_by": "user-456",
        },
    }

    result = await worker.execute(task_vars)

    assert result["finalized"] is True
    assert result["locked_by"] == "admin"
