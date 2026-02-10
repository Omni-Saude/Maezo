"""Tests for GenerateExecutiveDashboardWorker."""
from __future__ import annotations
import pytest
from datetime import datetime, timedelta
from healthcare_platform.platform_services.workers.generate_executive_dashboard_worker import (
    execute,
    GenerateExecutiveDashboardInput,
    DashboardGenerationException,
    GenerateExecutiveDashboardStub,
)


@pytest.fixture
def valid_input():
    """Valid input for executive dashboard generation."""
    return {
        "dashboard_type": "monthly",
        "period_start": datetime.utcnow() - timedelta(days=30),
        "period_end": datetime.utcnow(),
        "include_trends": True,
        "include_forecasts": True,
        "compare_to_budget": True,
    }


@pytest.mark.unit
class TestGenerateExecutiveDashboardWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, valid_input, tenant_austa):
        """Test successful executive dashboard generation."""
        result = await execute(valid_input)

        assert "dashboard_id" in result
        assert "kpis" in result
        assert len(result["kpis"]) > 0
        assert "summary" in result
        assert result["dashboard_type"] == "monthly"

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
            await execute({"dashboard_type": "monthly"})

    @pytest.mark.asyncio
    async def test_all_dashboard_types(self, tenant_austa):
        """Test all dashboard types."""
        for dashboard_type in ["monthly", "quarterly", "yearly", "realtime"]:
            input_data = {
                "dashboard_type": dashboard_type,
                "period_start": datetime.utcnow() - timedelta(days=30),
                "period_end": datetime.utcnow(),
            }

            result = await execute(input_data)

            assert result["dashboard_type"] == dashboard_type

    @pytest.mark.asyncio
    async def test_financial_kpis(self, tenant_austa):
        """Test financial KPI collection."""
        service = GenerateExecutiveDashboardStub()

        period_start = datetime.utcnow() - timedelta(days=30)
        period_end = datetime.utcnow()

        kpis = await service.collect_financial_kpis(period_start, period_end)

        assert len(kpis) > 0
        for kpi in kpis:
            assert kpi.kpi_category == "financial"
            assert kpi.value is not None

    @pytest.mark.asyncio
    async def test_operational_kpis(self, tenant_austa):
        """Test operational KPI collection."""
        service = GenerateExecutiveDashboardStub()

        period_start = datetime.utcnow() - timedelta(days=30)
        period_end = datetime.utcnow()

        kpis = await service.collect_operational_kpis(period_start, period_end)

        assert len(kpis) > 0
        for kpi in kpis:
            assert kpi.kpi_category == "operational"

    @pytest.mark.asyncio
    async def test_clinical_kpis(self, tenant_austa):
        """Test clinical KPI collection."""
        service = GenerateExecutiveDashboardStub()

        period_start = datetime.utcnow() - timedelta(days=30)
        period_end = datetime.utcnow()

        kpis = await service.collect_clinical_kpis(period_start, period_end)

        assert len(kpis) > 0
        for kpi in kpis:
            assert kpi.kpi_category == "clinical"

    @pytest.mark.asyncio
    async def test_kpi_status_classification(self, tenant_austa):
        """Test KPI status classification."""
        input_data = {
            "dashboard_type": "monthly",
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        for kpi in result["kpis"]:
            assert kpi["status"] in ["good", "warning", "critical"]

    @pytest.mark.asyncio
    async def test_trend_analysis(self, tenant_austa):
        """Test trend analysis."""
        input_data = {
            "dashboard_type": "monthly",
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
            "include_trends": True,
        }

        result = await execute(input_data)

        for kpi in result["kpis"]:
            if kpi.get("previous_period") is not None:
                assert kpi.get("trend") in ["up", "down", "stable"]

    @pytest.mark.asyncio
    async def test_executive_summary(self, tenant_austa):
        """Test executive summary generation."""
        input_data = {
            "dashboard_type": "monthly",
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert "highlights" in result["summary"]
        assert "concerns" in result["summary"]
        assert "recommendations" in result["summary"]

    @pytest.mark.asyncio
    async def test_critical_alerts(self, tenant_austa):
        """Test critical alerts identification."""
        input_data = {
            "dashboard_type": "monthly",
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert "alerts" in result
        # Alerts should only contain critical KPIs
        for alert in result["alerts"]:
            matching_kpi = [kpi for kpi in result["kpis"] if kpi["kpi_name"] == alert]
            if matching_kpi:
                assert matching_kpi[0]["status"] == "critical"

    @pytest.mark.asyncio
    async def test_duration_recorded(self, tenant_austa):
        """Test duration is recorded."""
        input_data = {
            "dashboard_type": "monthly",
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result = await execute(input_data)

        assert "duration_ms" in result
        assert result["duration_ms"] > 0

    @pytest.mark.asyncio
    async def test_idempotency(self, tenant_austa):
        """Test idempotency of dashboard generation."""
        input_data = {
            "dashboard_type": "monthly",
            "period_start": datetime.utcnow() - timedelta(days=30),
            "period_end": datetime.utcnow(),
        }

        result1 = await execute(input_data)
        result2 = await execute(input_data)

        assert len(result1["kpis"]) == len(result2["kpis"])
