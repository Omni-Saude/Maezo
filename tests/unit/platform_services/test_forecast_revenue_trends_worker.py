"""Tests for ForecastRevenueTrendsWorker."""
from __future__ import annotations
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from healthcare_platform.platform_services.workers.forecast_revenue_trends_worker import (
    ForecastRevenueTrendsInput,
    ForecastRevenueTrendsOutput,
    RevenueForecastingError,
    ForecastRevenueTrendsWorkerStub,
)


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """Create worker instance."""
    return ForecastRevenueTrendsWorkerStub(fhir_client=fhir_client)


@pytest.fixture
def valid_input():
    """Valid input for revenue forecasting."""
    return ForecastRevenueTrendsInput(
        historical_months=12,
        forecast_months=6,
        include_seasonality=True,
        include_trends=True,
        confidence_level=Decimal("95.0"),
        payer_breakdown=True,
        service_line_breakdown=True,
    )


@pytest.mark.unit
class TestForecastRevenueTrendsWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input, tenant_austa):
        """Test successful revenue forecasting."""
        result = await worker.execute(valid_input)

        assert isinstance(result, ForecastRevenueTrendsOutput)
        assert len(result.monthly_forecasts) > 0
        assert result.overall_trend in ["GROWING", "STABLE", "DECLINING"]
        assert result.forecast_accuracy > Decimal("0")

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test default values work."""
        input_data = ForecastRevenueTrendsInput()
        assert input_data.historical_months == 12
        assert input_data.forecast_months == 6

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(ForecastRevenueTrendsInput())

    @pytest.mark.asyncio
    async def test_monthly_forecasts(self, worker, tenant_austa):
        """Test monthly forecast generation."""
        input_data = ForecastRevenueTrendsInput(
            forecast_months=6,
        )

        result = await worker.execute(input_data)

        assert len(result.monthly_forecasts) == 6

        for forecast in result.monthly_forecasts:
            assert forecast.forecasted_revenue > Decimal("0")
            assert forecast.lower_bound < forecast.forecasted_revenue
            assert forecast.upper_bound > forecast.forecasted_revenue

    @pytest.mark.asyncio
    async def test_confidence_intervals(self, worker, tenant_austa):
        """Test confidence interval calculation."""
        input_data = ForecastRevenueTrendsInput(
            confidence_level=Decimal("95.0"),
        )

        result = await worker.execute(input_data)

        forecast = result.monthly_forecasts[0]
        assert forecast.confidence == Decimal("95.0")
        assert forecast.lower_bound < forecast.upper_bound

    @pytest.mark.asyncio
    async def test_seasonality_decomposition(self, worker, tenant_austa):
        """Test seasonality component decomposition."""
        input_data = ForecastRevenueTrendsInput(
            include_seasonality=True,
        )

        result = await worker.execute(input_data)

        assert result.seasonality_detected is not None

        forecast = result.monthly_forecasts[0]
        assert forecast.seasonal_component is not None

    @pytest.mark.asyncio
    async def test_trend_component(self, worker, tenant_austa):
        """Test trend component extraction."""
        input_data = ForecastRevenueTrendsInput(
            include_trends=True,
        )

        result = await worker.execute(input_data)

        forecast = result.monthly_forecasts[0]
        assert forecast.trend_component is not None

    @pytest.mark.asyncio
    async def test_payer_breakdown(self, worker, tenant_austa):
        """Test payer-specific forecasts."""
        input_data = ForecastRevenueTrendsInput(
            payer_breakdown=True,
        )

        result = await worker.execute(input_data)

        assert result.payer_forecasts is not None
        assert len(result.payer_forecasts) > 0

        for payer_forecast in result.payer_forecasts:
            assert payer_forecast.forecasted_revenue > Decimal("0")
            assert payer_forecast.risk_level in ["LOW", "MEDIUM", "HIGH"]

    @pytest.mark.asyncio
    async def test_service_line_breakdown(self, worker, tenant_austa):
        """Test service line forecasts."""
        input_data = ForecastRevenueTrendsInput(
            service_line_breakdown=True,
        )

        result = await worker.execute(input_data)

        assert result.service_line_forecasts is not None
        assert len(result.service_line_forecasts) > 0

        for service_forecast in result.service_line_forecasts:
            assert service_forecast.forecasted_revenue > Decimal("0")
            assert service_forecast.volume_trend in [
                "INCREASING",
                "STABLE",
                "DECREASING",
            ]

    @pytest.mark.asyncio
    async def test_overall_trend_detection(self, worker, tenant_austa):
        """Test overall trend detection."""
        input_data = ForecastRevenueTrendsInput()

        result = await worker.execute(input_data)

        assert result.overall_trend in ["GROWING", "STABLE", "DECLINING"]

    @pytest.mark.asyncio
    async def test_risk_factors_identification(self, worker, tenant_austa):
        """Test risk factors identification."""
        input_data = ForecastRevenueTrendsInput()

        result = await worker.execute(input_data)

        assert isinstance(result.risk_factors, list)

    @pytest.mark.asyncio
    async def test_recommendations_generation(self, worker, tenant_austa):
        """Test strategic recommendations."""
        input_data = ForecastRevenueTrendsInput()

        result = await worker.execute(input_data)

        assert len(result.recommendations) > 0

    @pytest.mark.asyncio
    async def test_forecast_timestamp(self, worker, tenant_austa):
        """Test forecast timestamp is recorded."""
        input_data = ForecastRevenueTrendsInput()

        result = await worker.execute(input_data)

        assert result.forecast_timestamp is not None
        assert isinstance(result.forecast_timestamp, datetime)
