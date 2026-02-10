"""Tests for CalculateOperationalMetricsWorker."""
from __future__ import annotations
import pytest
from datetime import datetime, timedelta
from healthcare_platform.platform_services.workers.calculate_operational_metrics_worker import (
    execute,
    CalculateOperationalMetricsInput,
    OperationalMetricsException,
    CalculateOperationalMetricsStub,
)


@pytest.fixture
def valid_input():
    """Valid input for operational metrics."""
    return {
        "metric_types": ["los", "bed_occupancy"],
        "period_start": datetime.utcnow() - timedelta(days=30),
        "period_end": datetime.utcnow(),
        "department": "ICU",
        "include_benchmarks": True,
    }


@pytest.mark.unit
class TestCalculateOperationalMetricsWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, valid_input, tenant_austa):
        """Test successful operational metrics calculation."""
        result = await execute(valid_input)

        assert "calculation_id" in result
        assert "metrics" in result
        assert len(result["metrics"]) == 2
        assert result["department"] == "ICU"

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises(self, tenant_austa):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            await execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await execute({"metric_types": ["los"]})

    @pytest.mark.asyncio
    async def test_all_metric_types(self, tenant_austa):
        """Test all supported metric types."""
        input_data = {
            "metric_types": ["los", "bed_occupancy", "or_utilization", "ed_throughput"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert len(result["metrics"]) == 4
        metric_types = [m["metric_type"] for m in result["metrics"]]
        assert "los" in metric_types
        assert "bed_occupancy" in metric_types

    @pytest.mark.asyncio
    async def test_los_calculation(self, tenant_austa):
        """Test length of stay calculation."""
        service = CalculateOperationalMetricsStub()

        period_start = datetime.utcnow() - timedelta(days=30)
        period_end = datetime.utcnow()

        metric = await service.calculate_los(period_start, period_end, "ICU")

        assert metric.metric_type == "los"
        assert metric.unit == "days"
        assert metric.value > 0
        assert "total_admissions" in metric.details

    @pytest.mark.asyncio
    async def test_bed_occupancy_calculation(self, tenant_austa):
        """Test bed occupancy calculation."""
        service = CalculateOperationalMetricsStub()

        period_start = datetime.utcnow() - timedelta(days=30)
        period_end = datetime.utcnow()

        metric = await service.calculate_bed_occupancy(period_start, period_end, "General")

        assert metric.metric_type == "bed_occupancy"
        assert metric.unit == "%"
        assert 0 <= metric.value <= 100
        assert "total_beds" in metric.details

    @pytest.mark.asyncio
    async def test_benchmark_comparison(self, tenant_austa):
        """Test benchmark comparison."""
        input_data = {
            "metric_types": ["los"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
            "include_benchmarks": True,
        }

        result = await execute(input_data)

        metric = result["metrics"][0]
        assert metric.get("benchmark_value") is not None
        assert metric.get("variance_from_benchmark") is not None

    @pytest.mark.asyncio
    async def test_status_classification(self, tenant_austa):
        """Test metric status classification."""
        input_data = {
            "metric_types": ["bed_occupancy"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        metric = result["metrics"][0]
        assert metric["status"] in ["good", "warning", "critical"]

    @pytest.mark.asyncio
    async def test_department_filter(self, tenant_austa):
        """Test department filter."""
        input_data = {
            "metric_types": ["bed_occupancy"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
            "department": "Surgery",
        }

        result = await execute(input_data)

        assert result["department"] == "Surgery"

    @pytest.mark.asyncio
    async def test_duration_recorded(self, tenant_austa):
        """Test duration is recorded."""
        input_data = {
            "metric_types": ["los"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert "duration_ms" in result
        assert result["duration_ms"] > 0

    @pytest.mark.asyncio
    async def test_idempotency(self, tenant_austa):
        """Test idempotency of calculation."""
        input_data = {
            "metric_types": ["los"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result1 = await execute(input_data)
        result2 = await execute(input_data)

        assert len(result1["metrics"]) == len(result2["metrics"])
