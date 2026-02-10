"""Tests for AnalyzeFinancialPerformanceWorker."""
from __future__ import annotations
import pytest
from datetime import datetime, timedelta
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.platform_services.workers.analyze_financial_performance_worker import (
    execute,
    AnalyzeFinancialPerformanceInput,
    AnalyzeFinancialPerformanceOutput,
    FinancialAnalysisException,
    AnalyzeFinancialPerformanceStub,
)


@pytest.fixture
def valid_input():
    """Valid input for financial performance analysis."""
    return {
        "analysis_types": ["revenue_analysis", "ebitda"],
        "period_start": datetime.utcnow() - timedelta(days=30),
        "period_end": datetime.utcnow(),
        "specialty": None,
        "payer": None,
        "include_projections": False,
    }


@pytest.mark.unit
class TestAnalyzeFinancialPerformanceWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, valid_input, tenant_austa):
        """Test successful financial performance analysis."""
        result = await execute(valid_input)

        assert isinstance(result, dict)
        assert "analysis_id" in result
        assert "metrics" in result
        assert len(result["metrics"]) == 2
        assert result["total_revenue"] > 0
        assert result["total_cost"] > 0
        assert result["net_margin"] >= 0

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
            await execute({"analysis_types": ["revenue_analysis"]})

    @pytest.mark.asyncio
    async def test_all_analysis_types(self, tenant_austa):
        """Test all supported analysis types."""
        input_data = {
            "analysis_types": [
                "revenue_analysis",
                "cost_per_case",
                "margin_by_payer",
                "margin_by_specialty",
                "ebitda",
            ],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert len(result["metrics"]) == 5
        types_found = [m["analysis_type"] for m in result["metrics"]]
        assert "revenue_analysis" in types_found
        assert "ebitda" in types_found

    @pytest.mark.asyncio
    async def test_revenue_breakdown(self, tenant_austa):
        """Test revenue analysis with breakdown."""
        input_data = {
            "analysis_types": ["revenue_analysis"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        metric = result["metrics"][0]
        assert metric["analysis_type"] == "revenue_analysis"
        assert "breakdown" in metric
        assert metric["breakdown"] is not None

    @pytest.mark.asyncio
    async def test_specialty_filter(self, tenant_austa):
        """Test specialty filter."""
        input_data = {
            "analysis_types": ["revenue_analysis"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
            "specialty": "cardiology",
        }

        result = await execute(input_data)

        assert result["specialty"] == "cardiology"

    @pytest.mark.asyncio
    async def test_payer_filter(self, tenant_austa):
        """Test payer filter."""
        input_data = {
            "analysis_types": ["revenue_analysis"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
            "payer": "Unimed",
        }

        result = await execute(input_data)

        assert result["payer"] == "Unimed"

    @pytest.mark.asyncio
    async def test_margin_calculation(self, tenant_austa):
        """Test net margin calculation."""
        input_data = {
            "analysis_types": ["revenue_analysis", "cost_per_case"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert "net_margin" in result
        # Margin should be (revenue - cost) / revenue * 100
        expected_margin = (
            (result["total_revenue"] - result["total_cost"])
            / result["total_revenue"]
            * 100
        )
        assert abs(result["net_margin"] - expected_margin) < 1.0

    @pytest.mark.asyncio
    async def test_variance_tracking(self, tenant_austa):
        """Test variance from previous period."""
        input_data = {
            "analysis_types": ["revenue_analysis"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        metric = result["metrics"][0]
        if metric.get("previous_period_value") is not None:
            assert "variance_percent" in metric

    @pytest.mark.asyncio
    async def test_duration_recorded(self, tenant_austa):
        """Test duration is recorded."""
        input_data = {
            "analysis_types": ["revenue_analysis"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert "duration_ms" in result
        assert result["duration_ms"] > 0

    @pytest.mark.asyncio
    async def test_idempotency(self, tenant_austa):
        """Test idempotency of analysis."""
        input_data = {
            "analysis_types": ["revenue_analysis"],
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result1 = await execute(input_data)
        result2 = await execute(input_data)

        assert len(result1["metrics"]) == len(result2["metrics"])
