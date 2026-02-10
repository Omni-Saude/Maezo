from __future__ import annotations

from datetime import date, timedelta

import pytest

from healthcare_platform.revenue_cycle.collection.workers.update_forecasts_worker import UpdateForecastsWorker


@pytest.mark.asyncio
class TestUpdateForecastsWorker:
    """Tests for UpdateForecastsWorker."""

    async def test_update_forecasts_success(self):
        """Test successful forecast update."""
        worker = UpdateForecastsWorker()

        forecast_start = date.today()
        forecast_end = date.today() + timedelta(days=28)

        task_variables = {
            "forecast_start": forecast_start.isoformat(),
            "forecast_end": forecast_end.isoformat(),
            "current_ar": 720000.00,
        }

        result = await worker.execute(task_variables)

        assert result["forecast_start"] == forecast_start.isoformat()
        assert result["forecast_end"] == forecast_end.isoformat()
        assert result["current_ar"] == 720000.00
        assert result["total_forecast"] > 0
        assert len(result["forecast_by_week"]) > 0

        # Verify week structure
        for week in result["forecast_by_week"]:
            assert "week_start" in week
            assert "week_end" in week
            assert "expected_collections" in week
            assert "confidence" in week
            assert "collection_count" in week

    async def test_update_forecasts_weekly_grouping(self):
        """Test that forecasts are properly grouped by week."""
        worker = UpdateForecastsWorker()

        forecast_start = date.today()
        forecast_end = date.today() + timedelta(days=28)

        task_variables = {
            "forecast_start": forecast_start.isoformat(),
            "forecast_end": forecast_end.isoformat(),
        }

        result = await worker.execute(task_variables)

        # Should have approximately 4 weeks
        assert len(result["forecast_by_week"]) >= 4

    async def test_update_forecasts_with_predicted_collections(self):
        """Test forecast update with custom predicted collections."""
        worker = UpdateForecastsWorker()

        forecast_start = date.today()
        forecast_end = date.today() + timedelta(days=14)

        predicted_collections = [
            {
                "date": (date.today() + timedelta(days=7)).isoformat(),
                "amount": 50000.00,
                "confidence": 0.90,
            },
            {
                "date": (date.today() + timedelta(days=14)).isoformat(),
                "amount": 60000.00,
                "confidence": 0.85,
            },
        ]

        task_variables = {
            "forecast_start": forecast_start.isoformat(),
            "forecast_end": forecast_end.isoformat(),
            "predicted_collections": predicted_collections,
        }

        result = await worker.execute(task_variables)

        assert result["total_forecast"] > 0
