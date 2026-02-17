from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.enums import ReconciliationStatus
from healthcare_platform.revenue_cycle.collection.workers.reconcile_daily_worker import ReconcileDailyWorker


@pytest.mark.asyncio
class TestReconcileDailyWorker:
    """Tests for ReconcileDailyWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_daily_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_daily_worker.FederatedDMNService')
    async def test_reconcile_daily_balanced(self, mock_dmn_class, mock_tenant):
        """Test daily reconciliation with balanced variance."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'status': ReconciliationStatus.BALANCED.value,
            'variancePercentage': 0.4
        }

        worker = ReconcileDailyWorker()
        yesterday = date.today() - timedelta(days=1)

        job = MagicMock()
        job.variables = {
            "reconciliation_date": yesterday.isoformat(),
            "expected_amount": 50000.00,
            "received_amount": 49800.00,
            "payment_count": 12,
            "matched_count": 11,
            "variance_threshold": 0.01,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["reconciliation_id"] is not None
        assert result.variables["period_start"] == yesterday.isoformat()
        assert result.variables["period_end"] == yesterday.isoformat()
        assert result.variables["total_expected"] == 50000.00

    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_daily_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_daily_worker.FederatedDMNService')
    async def test_reconcile_daily_unbalanced(self, mock_dmn_class, mock_tenant):
        """Test daily reconciliation with unbalanced variance."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'status': ReconciliationStatus.UNBALANCED.value,
            'variancePercentage': 5.0
        }

        worker = ReconcileDailyWorker()
        yesterday = date.today() - timedelta(days=1)

        job = MagicMock()
        job.variables = {
            "reconciliation_date": yesterday.isoformat(),
            "expected_amount": 100000.00,
            "received_amount": 95000.00,
            "variance_threshold": 0.01,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["status"] == ReconciliationStatus.UNBALANCED.value
        assert float(result.variables["variance_percentage"]) > 1.0

    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_daily_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_daily_worker.FederatedDMNService')
    async def test_reconcile_daily_default_date(self, mock_dmn_class, mock_tenant):
        """Test reconciliation using default date (yesterday)."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'status': ReconciliationStatus.BALANCED.value,
            'variancePercentage': 0.0
        }

        worker = ReconcileDailyWorker()

        job = MagicMock()
        job.variables = {}

        result = await worker.execute(job)

        yesterday = date.today() - timedelta(days=1)
        assert result.success
        assert result.variables["period_start"] == yesterday.isoformat()
        assert result.variables["reconciliation_id"] is not None
