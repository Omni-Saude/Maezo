from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from platform.revenue_cycle.collection.enums import ReconciliationStatus
from platform.revenue_cycle.collection.workers.reconcile_daily_worker import ReconcileDailyWorker


@pytest.mark.asyncio
class TestReconcileDailyWorker:
    """Tests for ReconcileDailyWorker."""

    async def test_reconcile_daily_balanced(self):
        """Test daily reconciliation with balanced variance."""
        worker = ReconcileDailyWorker()
        yesterday = date.today() - timedelta(days=1)

        task_variables = {
            "reconciliation_date": yesterday.isoformat(),
            "expected_amount": 50000.00,
            "variance_threshold": 0.01,  # 1%
        }

        result = await worker.execute(task_variables)

        assert result["reconciliation_id"] is not None
        assert result["period_start"] == yesterday.isoformat()
        assert result["period_end"] == yesterday.isoformat()
        assert result["total_expected"] == 50000.00
        assert result["payment_count"] > 0
        assert result["matched_count"] > 0
        assert "variance_percentage" in result

    async def test_reconcile_daily_unbalanced(self):
        """Test daily reconciliation with unbalanced variance."""
        worker = ReconcileDailyWorker()
        yesterday = date.today() - timedelta(days=1)

        task_variables = {
            "reconciliation_date": yesterday.isoformat(),
            "expected_amount": 100000.00,  # Large expected amount
            "variance_threshold": 0.01,
        }

        result = await worker.execute(task_variables)

        # With mocked received amount of 47500.50, this should be unbalanced
        assert result["status"] == ReconciliationStatus.UNBALANCED.value
        assert float(result["variance_percentage"]) > 1.0

    async def test_reconcile_daily_default_date(self):
        """Test reconciliation using default date (yesterday)."""
        worker = ReconcileDailyWorker()

        task_variables = {}

        result = await worker.execute(task_variables)

        yesterday = date.today() - timedelta(days=1)
        assert result["period_start"] == yesterday.isoformat()
        assert result["reconciliation_id"] is not None
