"""Tests for CalculateRevenuePotentialWorker."""
from __future__ import annotations
import pytest
from datetime import datetime
from decimal import Decimal
from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import (
    CalculateRevenuePotentialInput,
    CalculateRevenuePotentialOutput,
    RevenuePotentialCalculationError,
    CalculateRevenuePotentialStub,
)


@pytest.fixture
def worker(tenant_austa):
    """Create worker instance."""
    return CalculateRevenuePotentialStub()


@pytest.fixture
def valid_input():
    """Valid input for revenue potential calculation."""
    return CalculateRevenuePotentialInput(
        current_annual_revenue=Decimal("10000000"),
        volume_growth_scenarios=[Decimal("5.0"), Decimal("10.0")],
        pricing_optimization_scenarios=[Decimal("5.0"), Decimal("10.0")],
        include_bundle_impact=True,
        include_coding_improvements=True,
        time_horizon_months=12,
    )


@pytest.mark.unit
class TestCalculateRevenuePotentialWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input):
        """Test successful revenue potential calculation."""
        result = await worker.execute(valid_input)

        assert isinstance(result, CalculateRevenuePotentialOutput)
        assert result.calculation_id is not None
        assert len(result.scenarios) > 0
        assert result.best_case_scenario is not None
        assert result.conservative_scenario is not None
        assert result.recommended_scenario is not None

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            CalculateRevenuePotentialInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        worker = CalculateRevenuePotentialStub()
        valid_input = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_input)

    @pytest.mark.asyncio
    async def test_volume_growth_scenarios(self, worker, tenant_austa):
        """Test volume growth scenario generation."""
        input_data = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
            volume_growth_scenarios=[Decimal("5.0"), Decimal("10.0"), Decimal("15.0")],
        )

        result = await worker.execute(input_data)

        volume_scenarios = [s for s in result.scenarios if s.scenario_type == "volume_growth"]
        assert len(volume_scenarios) >= 3

    @pytest.mark.asyncio
    async def test_pricing_scenarios(self, worker, tenant_austa):
        """Test pricing optimization scenarios."""
        input_data = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
            pricing_optimization_scenarios=[Decimal("5.0"), Decimal("10.0")],
        )

        result = await worker.execute(input_data)

        pricing_scenarios = [s for s in result.scenarios if s.scenario_type == "pricing"]
        assert len(pricing_scenarios) >= 2

    @pytest.mark.asyncio
    async def test_combined_scenarios(self, worker, tenant_austa):
        """Test combined strategy scenarios."""
        input_data = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
        )

        result = await worker.execute(input_data)

        combined = [s for s in result.scenarios if s.scenario_type == "combined"]
        assert len(combined) > 0

    @pytest.mark.asyncio
    async def test_bundle_impact(self, worker, tenant_austa):
        """Test bundle impact scenario."""
        input_data = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
            include_bundle_impact=True,
        )

        result = await worker.execute(input_data)

        bundle_scenarios = [s for s in result.scenarios if "Bundle" in s.scenario_name]
        assert len(bundle_scenarios) > 0

    @pytest.mark.asyncio
    async def test_coding_improvements(self, worker, tenant_austa):
        """Test coding improvement scenario."""
        input_data = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
            include_coding_improvements=True,
        )

        result = await worker.execute(input_data)

        coding_scenarios = [s for s in result.scenarios if "Codifica" in s.scenario_name]
        assert len(coding_scenarios) > 0

    @pytest.mark.asyncio
    async def test_best_case_identification(self, worker, tenant_austa):
        """Test best case scenario identification."""
        input_data = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
        )

        result = await worker.execute(input_data)

        # Best case should have highest revenue
        assert result.best_case_scenario.projected_revenue == max(
            s.projected_revenue for s in result.scenarios
        )

    @pytest.mark.asyncio
    async def test_conservative_scenario(self, worker, tenant_austa):
        """Test conservative scenario identification."""
        input_data = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
        )

        result = await worker.execute(input_data)

        # Conservative should be low risk
        assert result.conservative_scenario.risk_level == "low"

    @pytest.mark.asyncio
    async def test_strategic_recommendations(self, worker, tenant_austa):
        """Test strategic recommendations generation."""
        input_data = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
        )

        result = await worker.execute(input_data)

        assert len(result.strategic_recommendations) > 0

    @pytest.mark.asyncio
    async def test_action_plan_structure(self, worker, tenant_austa):
        """Test action plan structure."""
        input_data = CalculateRevenuePotentialInput(
            current_annual_revenue=Decimal("10000000"),
        )

        result = await worker.execute(input_data)

        assert "phase_1_quick_wins" in result.action_plan
        assert "phase_2_medium_term" in result.action_plan
        assert "phase_3_long_term" in result.action_plan
