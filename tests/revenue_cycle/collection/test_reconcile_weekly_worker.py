from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.reconcile_weekly_worker import ReconcileWeeklyWorker


@pytest.mark.asyncio
class TestReconcileWeeklyWorker:
    """Tests for ReconcileWeeklyWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_weekly_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_weekly_worker.FederatedDMNService')
    async def test_reconcile_weekly_with_trend(self, mock_dmn_class, mock_tenant):
        """Test weekly reconciliation with trend calculation."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'status': 'BALANCED',
            'variancePercentage': 0.5
        }

        worker = ReconcileWeeklyWorker()

        today = date.today()
        week_start = today - timedelta(days=today.weekday() + 7)

        job = MagicMock()
        job.variables = {
            "week_start": week_start.isoformat(),
            "previous_week_total": 320000.00,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["reconciliation_id"] is not None
        assert result.variables["period_start"] == week_start.isoformat()
        assert result.variables["daily_reconciliations"] == 7

    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_weekly_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_weekly_worker.FederatedDMNService')
    async def test_reconcile_weekly_default_week(self, mock_dmn_class, mock_tenant):
        """Test reconciliation using default week."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'status': 'BALANCED',
            'variancePercentage': 1.0
        }

        worker = ReconcileWeeklyWorker()

        job = MagicMock()
        job.variables = {}

        result = await worker.execute(job)

        assert result.success
        assert result.variables["reconciliation_id"] is not None
        assert result.variables["total_expected"] > 0
        assert result.variables["total_received"] > 0

    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_weekly_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_weekly_worker.FederatedDMNService')
    async def test_reconcile_weekly_upward_trend(self, mock_dmn_class, mock_tenant):
        """Test weekly reconciliation with upward trend."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'status': 'BALANCED',
            'variancePercentage': 0.5
        }

        worker = ReconcileWeeklyWorker()

        job = MagicMock()
        job.variables = {
            "previous_week_total": 300000.00,
            "received_amount": 332500.75,
        }

        result = await worker.execute(job)

        assert result.success
        # Current received (332500.75) > previous (300000) = upward trend
