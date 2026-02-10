from __future__ import annotations

from datetime import date, timedelta

import pytest

from healthcare_platform.revenue_cycle.collection.workers.calculate_dso_worker import CalculateDSOWorker


@pytest.mark.asyncio
class TestCalculateDSOWorker:
    """Tests for CalculateDSOWorker."""

    async def test_calculate_dso_success(self):
        """Test successful DSO calculation."""
        worker = CalculateDSOWorker()

        period_start = date.today() - timedelta(days=30)
        period_end = date.today()

        task_variables = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "accounts_receivable": 720000.00,
            "net_revenue": 1400000.00,
        }

        result = await worker.execute(task_variables)

        assert result["dso"] > 0
        assert result["accounts_receivable"] == 720000.00
        assert result["net_revenue"] == 1400000.00
        assert result["period_days"] == 31
        assert result["benchmark_status"] in ["excellent", "good", "acceptable", "needs_improvement", "critical"]

    async def test_calculate_dso_excellent_benchmark(self):
        """Test DSO with excellent benchmark."""
        worker = CalculateDSOWorker()

        period_start = date.today() - timedelta(days=30)
        period_end = date.today()

        task_variables = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "accounts_receivable": 100000.00,
            "net_revenue": 1000000.00,  # Low AR relative to revenue
        }

        result = await worker.execute(task_variables)

        assert result["benchmark_status"] == "excellent"
        assert result["dso"] < 45

    async def test_calculate_dso_zero_revenue(self):
        """Test DSO calculation with zero revenue."""
        worker = CalculateDSOWorker()

        period_start = date.today() - timedelta(days=30)
        period_end = date.today()

        task_variables = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "accounts_receivable": 720000.00,
            "net_revenue": 0.00,
        }

        result = await worker.execute(task_variables)

        assert result["dso"] == 0
