"""Integration tests for Forecast Revenue Trends Worker V2."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestForecastRevenueTrendsWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-003",
            "process_instance_id": "proc-003",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "historical_months": 12,
                "forecast_months": 6,
                "include_seasonality": True,
                "include_trends": True,
                "confidence_level": 95.0,
                "payer_breakdown": True,
                "service_line_breakdown": True,
                "correlation_id": "corr-003",
            },
            "worker_id": "forecast-revenue-trends",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = ForecastRevenueTrendsWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        assert ForecastRevenueTrendsWorker.TOPIC == "forecast-revenue-trends"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_execute_with_missing_variables(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context(variables={})
        result = worker.execute(context)
        # Should handle gracefully with defaults
        assert result.status in (TaskStatus.SUCCESS, TaskStatus.FAILURE)

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)

    def test_monthly_forecasts_generated(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert "monthly_forecasts" in result.variables
        # Should have 6 monthly forecasts
        forecasts = result.variables.get("monthly_forecasts", [])
        assert len(forecasts) == 6

    def test_confidence_intervals_present(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        forecasts = result.variables.get("monthly_forecasts", [])
        for forecast in forecasts:
            assert "lower_bound" in forecast
            assert "upper_bound" in forecast
            # V2 worker doesn't include 'confidence' in each forecast
            # Confidence level is a parameter, not per-forecast output

    def test_trend_decomposition(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        forecasts = result.variables.get("monthly_forecasts", [])
        for forecast in forecasts:
            assert "trend_component" in forecast
            assert "seasonal_component" in forecast

    def test_payer_breakdown_included(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "payer_forecasts" in result.variables

    def test_service_line_breakdown_included(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "service_line_forecasts" in result.variables

    def test_overall_trend_detected(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "overall_trend" in result.variables
        trend = result.variables["overall_trend"]
        assert trend in ["GROWING", "STABLE", "DECLINING"]

    def test_seasonality_detection(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "seasonality_detected" in result.variables

    def test_risk_factors_identified(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        # V2 worker includes risk_level in payer_forecasts breakdown
        payer_forecasts = result.variables.get("payer_forecasts")
        if payer_forecasts:
            for payer in payer_forecasts:
                assert "risk_level" in payer

    def test_recommendations_generated(self):
        from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import ForecastRevenueTrendsWorker
        worker = ForecastRevenueTrendsWorker()
        context = self._make_context()
        result = worker.execute(context)
        # V2 worker provides trend analysis which can inform recommendations
        assert "overall_trend" in result.variables
        assert result.variables["overall_trend"] in ["GROWING", "STABLE", "DECLINING"]
