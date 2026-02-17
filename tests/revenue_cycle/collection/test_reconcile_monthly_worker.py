from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.enums import ReconciliationStatus
from healthcare_platform.revenue_cycle.collection.workers.reconcile_monthly_worker import ReconcileMonthlyWorker


@pytest.mark.asyncio
class TestReconcileMonthlyWorker:
    """Tests for ReconcileMonthlyWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_monthly_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_monthly_worker.FederatedDMNService')
    async def test_reconcile_monthly_success(self, mock_dmn_class, mock_tenant):
        """Test successful monthly reconciliation."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'status': ReconciliationStatus.CLOSED.value
        }

        worker = ReconcileMonthlyWorker()

        job = MagicMock()
        job.variables = {
            "month": 1,
            "year": 2024,
            "closed_by": "user@example.com",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["reconciliation_id"] is not None
        assert result.variables["status"] == ReconciliationStatus.CLOSED.value
        assert result.variables["period_start"] == "2024-01-01"
        assert result.variables["period_end"] == "2024-01-31"
        assert result.variables["closed_by"] == "user@example.com"
        assert "closed_at" in result.variables

    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_monthly_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.reconcile_monthly_worker.FederatedDMNService')
    async def test_reconcile_monthly_december(self, mock_dmn_class, mock_tenant):
        """Test reconciliation for December (edge case)."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'status': ReconciliationStatus.CLOSED.value
        }

        worker = ReconcileMonthlyWorker()

        job = MagicMock()
        job.variables = {
            "month": 12,
            "year": 2024,
            "closed_by": "user@example.com",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["period_start"] == "2024-12-01"
        assert result.variables["period_end"] == "2024-12-31"
