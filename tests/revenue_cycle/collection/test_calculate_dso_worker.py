from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.calculate_dso_worker import CalculateDSOWorker


@pytest.mark.asyncio
class TestCalculateDSOWorker:
    """Tests for CalculateDSOWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_dso_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_dso_worker.FederatedDMNService')
    async def test_calculate_dso_success(self, MockDMNService, mock_tenant):
        """Test successful DSO calculation."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'benchmarkStatus': 'good',
            'calculatedAt': '2024-01-01T00:00:00Z'
        }

        worker = CalculateDSOWorker()
        period_start = date.today() - timedelta(days=30)
        period_end = date.today()

        job = MagicMock()
        job.variables = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "accounts_receivable": 720000.00,
            "net_revenue": 1400000.00,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["dso"] > 0
        assert result.variables["accounts_receivable"] == 720000.00
        assert result.variables["net_revenue"] == 1400000.00
        assert result.variables["period_days"] == 31
        assert result.variables["benchmark_status"] in ["excellent", "good", "acceptable", "needs_improvement", "critical"]

    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_dso_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_dso_worker.FederatedDMNService')
    async def test_calculate_dso_excellent_benchmark(self, MockDMNService, mock_tenant):
        """Test DSO with excellent benchmark."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'benchmarkStatus': 'excellent',
            'calculatedAt': '2024-01-01T00:00:00Z'
        }

        worker = CalculateDSOWorker()
        period_start = date.today() - timedelta(days=30)
        period_end = date.today()

        job = MagicMock()
        job.variables = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "accounts_receivable": 100000.00,
            "net_revenue": 1000000.00,  # Low AR relative to revenue
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["benchmark_status"] == "excellent"
        assert result.variables["dso"] < 45

    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_dso_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.calculate_dso_worker.FederatedDMNService')
    async def test_calculate_dso_zero_revenue(self, MockDMNService, mock_tenant):
        """Test DSO calculation with zero revenue."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'benchmarkStatus': 'critical',
            'calculatedAt': '2024-01-01T00:00:00Z'
        }

        worker = CalculateDSOWorker()
        period_start = date.today() - timedelta(days=30)
        period_end = date.today()

        job = MagicMock()
        job.variables = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "accounts_receivable": 720000.00,
            "net_revenue": 0.00,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["dso"] == 0.0
