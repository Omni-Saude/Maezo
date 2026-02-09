from __future__ import annotations

from datetime import date

import pytest

from platform.revenue_cycle.collection.enums import ReconciliationPeriod, ReconciliationStatus
from platform.revenue_cycle.collection.exceptions import ReconciliationError
from platform.revenue_cycle.collection.workers.reconcile_monthly_worker import ReconcileMonthlyWorker


@pytest.mark.asyncio
class TestReconcileMonthlyWorker:
    """Tests for ReconcileMonthlyWorker."""

    async def test_reconcile_monthly_success(self):
        """Test successful monthly reconciliation."""
        worker = ReconcileMonthlyWorker()

        task_variables = {
            "month": 1,
            "year": 2024,
            "closed_by": "user@example.com",
        }

        result = await worker.execute(task_variables)

        assert result["reconciliation_id"] is not None
        assert result["status"] == ReconciliationStatus.CLOSED.value
        assert result["period_start"] == "2024-01-01"
        assert result["period_end"] == "2024-01-31"
        assert result["all_payments_allocated"] is True
        assert result["closed_by"] == "user@example.com"
        assert "closed_at" in result

    async def test_reconcile_monthly_invalid_month(self):
        """Test reconciliation with invalid month."""
        worker = ReconcileMonthlyWorker()

        task_variables = {
            "month": 13,
            "year": 2024,
            "closed_by": "user@example.com",
        }

        with pytest.raises(ReconciliationError):
            await worker.execute(task_variables)

    async def test_reconcile_monthly_december(self):
        """Test reconciliation for December (edge case)."""
        worker = ReconcileMonthlyWorker()

        task_variables = {
            "month": 12,
            "year": 2024,
            "closed_by": "user@example.com",
        }

        result = await worker.execute(task_variables)

        assert result["period_start"] == "2024-12-01"
        assert result["period_end"] == "2024-12-31"
