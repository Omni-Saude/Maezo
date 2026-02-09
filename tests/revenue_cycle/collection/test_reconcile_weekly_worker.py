from __future__ import annotations

from datetime import date, timedelta

import pytest

from platform.revenue_cycle.collection.enums import ReconciliationPeriod
from platform.revenue_cycle.collection.workers.reconcile_weekly_worker import ReconcileWeeklyWorker


@pytest.mark.asyncio
class TestReconcileWeeklyWorker:
    """Tests for ReconcileWeeklyWorker."""

    async def test_reconcile_weekly_with_trend(self):
        """Test weekly reconciliation with trend calculation."""
        worker = ReconcileWeeklyWorker()

        today = date.today()
        week_start = today - timedelta(days=today.weekday() + 7)

        task_variables = {
            "week_start": week_start.isoformat(),
            "previous_week_total": 320000.00,
        }

        result = await worker.execute(task_variables)

        assert result["reconciliation_id"] is not None
        assert result["period_start"] == week_start.isoformat()
        assert result["daily_reconciliations"] == 7
        assert "week_over_week_change" in result
        assert result["trend"] in ["up", "down", "flat"]

    async def test_reconcile_weekly_default_week(self):
        """Test reconciliation using default week."""
        worker = ReconcileWeeklyWorker()

        task_variables = {}

        result = await worker.execute(task_variables)

        assert result["reconciliation_id"] is not None
        assert result["total_expected"] > 0
        assert result["total_received"] > 0

    async def test_reconcile_weekly_upward_trend(self):
        """Test weekly reconciliation with upward trend."""
        worker = ReconcileWeeklyWorker()

        task_variables = {
            "previous_week_total": 300000.00,  # Lower than mocked current
        }

        result = await worker.execute(task_variables)

        assert float(result["week_over_week_change"]) > 0
        assert result["trend"] == "up"
