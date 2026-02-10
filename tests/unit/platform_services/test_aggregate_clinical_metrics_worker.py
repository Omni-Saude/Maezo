"""Tests for AggregateClinicalMetricsWorker."""
from __future__ import annotations
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import (
    execute,
    AggregateClinicalMetricsInput,
    AggregateClinicalMetricsOutput,
    ClinicalMetricsException,
    AggregateClinicalMetricsStub,
)


@pytest.fixture
def valid_input():
    """Valid input for clinical metrics aggregation."""
    return {
        "metric_types": ["readmission_rate", "mortality_index"],
        "period_start": datetime.utcnow() - timedelta(days=30),
        "period_end": datetime.utcnow(),
        "specialty": "cardiology",
        "department": "ICU",
        "include_comparison": True,
    }


@pytest.mark.unit
class TestAggregateClinicalMetricsWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, valid_input, tenant_austa):
        """Test successful clinical metrics aggregation."""
        result = await execute(valid_input)

        assert isinstance(result, dict)
        assert "aggregation_id" in result
        assert "metrics" in result
        assert len(result["metrics"]) == 2
        assert result["specialty"] == "cardiology"
        assert result["department"] == "ICU"
        assert result["total_encounters"] == 850

        # Verify metric structure
        metric = result["metrics"][0]
        assert "metric_type" in metric
        assert "value" in metric
        assert "unit" in metric
        assert "numerator" in metric
        assert "denominator" in metric

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises(self, tenant_austa):
        """Test missing required fields raises validation error."""
        with pytest.raises((DomainException, Exception)):
            await execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await execute({"metric_types": ["readmission_rate"]})

    @pytest.mark.asyncio
    async def test_all_metric_types(self, tenant_austa):
        """Test all supported metric types."""
        input_data = {
            "metric_types": [
                "readmission_rate",
                "mortality_index",
                "infection_rate",
                "los_average",
            ],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
            "include_comparison": True,
        }

        result = await execute(input_data)

        assert len(result["metrics"]) == 4
        metric_types = [m["metric_type"] for m in result["metrics"]]
        assert "readmission_rate" in metric_types
        assert "mortality_index" in metric_types
        assert "infection_rate" in metric_types
        assert "los_average" in metric_types

    @pytest.mark.asyncio
    async def test_empty_metric_types(self, tenant_austa):
        """Test empty metric_types list."""
        input_data = {
            "metric_types": [],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)
        assert result["metrics"] == []

    @pytest.mark.asyncio
    async def test_period_filters(self, tenant_austa):
        """Test period date filters."""
        period_start = datetime(2024, 1, 1)
        period_end = datetime(2024, 1, 31)

        input_data = {
            "metric_types": ["readmission_rate"],
            "period_start": period_start,
            "period_end": period_end,
        }

        result = await execute(input_data)

        assert result["period_start"] == period_start
        assert result["period_end"] == period_end

    @pytest.mark.asyncio
    async def test_optional_filters(self, tenant_austa):
        """Test optional specialty and department filters."""
        input_data = {
            "metric_types": ["readmission_rate"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
            "specialty": "oncology",
            "department": "Surgery",
            "icd10_filter": ["C50", "C80"],
        }

        result = await execute(input_data)

        assert result["specialty"] == "oncology"
        assert result["department"] == "Surgery"

    @pytest.mark.asyncio
    async def test_stub_implementation(self, tenant_austa):
        """Test stub implementation methods."""
        service = AggregateClinicalMetricsStub()

        period_start = datetime.utcnow() - timedelta(days=30)
        period_end = datetime.utcnow()
        filters = {"specialty": "cardiology"}

        # Test readmission rate
        metric = await service.calculate_readmission_rate(
            period_start, period_end, filters
        )
        assert metric.metric_type == "readmission_rate"
        assert metric.unit == "%"
        assert metric.value > 0

        # Test mortality index
        metric = await service.calculate_mortality_index(
            period_start, period_end, filters
        )
        assert metric.metric_type == "mortality_index"
        assert metric.denominator > 0

    @pytest.mark.asyncio
    async def test_idempotency(self, tenant_austa):
        """Test idempotency of metrics calculation."""
        input_data = {
            "metric_types": ["readmission_rate"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result1 = await execute(input_data)
        result2 = await execute(input_data)

        # Both calls should produce metrics with same structure
        assert len(result1["metrics"]) == len(result2["metrics"])
        assert result1["metrics"][0]["metric_type"] == result2["metrics"][0]["metric_type"]

    @pytest.mark.asyncio
    async def test_duration_recorded(self, tenant_austa):
        """Test duration is recorded."""
        input_data = {
            "metric_types": ["readmission_rate"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert "duration_ms" in result
        assert result["duration_ms"] > 0
