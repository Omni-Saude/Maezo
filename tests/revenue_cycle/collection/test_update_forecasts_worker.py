from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.update_forecasts_worker import UpdateForecastsWorker


@pytest.mark.asyncio
class TestUpdateForecastsWorker:
    """Tests for UpdateForecastsWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.update_forecasts_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.update_forecasts_worker.FederatedDMNService')
    async def test_update_forecasts_success(self, mock_dmn_class, mock_tenant):
        """Test successful forecast update."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'totalForecast': 250000.00,
            'confidence': 0.85
        }

        worker = UpdateForecastsWorker()

        forecast_start = date.today()
        forecast_end = date.today() + timedelta(days=28)

        job = MagicMock()
        job.variables = {
            "forecast_start": forecast_start.isoformat(),
            "forecast_end": forecast_end.isoformat(),
            "current_ar": 720000.00,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["forecast_start"] == forecast_start.isoformat()
        assert result.variables["forecast_end"] == forecast_end.isoformat()
        assert result.variables["current_ar"] == 720000.00
        assert result.variables["total_forecast"] > 0
        assert result.variables["confidence"] == 0.85

    @patch('healthcare_platform.revenue_cycle.collection.workers.update_forecasts_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.update_forecasts_worker.FederatedDMNService')
    async def test_update_forecasts_with_custom_ar(self, mock_dmn_class, mock_tenant):
        """Test forecast update with custom predicted collections."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'totalForecast': 150000.00,
            'confidence': 0.90
        }

        worker = UpdateForecastsWorker()

        forecast_start = date.today()
        forecast_end = date.today() + timedelta(days=14)

        job = MagicMock()
        job.variables = {
            "forecast_start": forecast_start.isoformat(),
            "forecast_end": forecast_end.isoformat(),
            "current_ar": 500000.00,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["total_forecast"] > 0
        assert result.variables["confidence"] > 0.8
