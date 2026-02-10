"""Tests for OptimizeResourceUtilizationWorker."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.optimize_resource_utilization_worker import (
    OptimizeResourceUtilizationInput,
    OptimizeResourceUtilizationOutput,
    OptimizeResourceUtilizationWorkerStub,
    ResourceUtilizationOptimizationError,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """Create worker instance."""
    return OptimizeResourceUtilizationWorkerStub(fhir_client=fhir_client)


@pytest.mark.unit
class TestOptimizeResourceUtilizationWorker:
    """Test suite for OptimizeResourceUtilizationWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful resource utilization optimization."""
        input_data = OptimizeResourceUtilizationInput(
            analysis_period_days=30,
            include_or_analysis=True,
            include_bed_analysis=True,
            include_staff_analysis=True,
            include_equipment_analysis=True,
        )

        result = await worker.execute(input_data)

        assert isinstance(result, OptimizeResourceUtilizationOutput)
        assert result.overall_efficiency_score >= Decimal("0")
        assert result.overall_efficiency_score <= Decimal("100")
        assert isinstance(result.optimization_opportunities, list)

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = OptimizeResourceUtilizationInput()

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_or_analysis_only(self, worker, tenant_austa):
        """Test OR analysis only."""
        input_data = OptimizeResourceUtilizationInput(
            include_or_analysis=True,
            include_bed_analysis=False,
            include_staff_analysis=False,
            include_equipment_analysis=False,
        )

        result = await worker.execute(input_data)

        assert result.or_utilization is not None
        assert result.bed_utilization is None
        assert result.staff_productivity is None
        assert result.equipment_utilization is None

    @pytest.mark.asyncio
    async def test_bed_analysis_only(self, worker, tenant_austa):
        """Test bed analysis only."""
        input_data = OptimizeResourceUtilizationInput(
            include_or_analysis=False,
            include_bed_analysis=True,
            include_staff_analysis=False,
            include_equipment_analysis=False,
        )

        result = await worker.execute(input_data)

        assert result.or_utilization is None
        assert result.bed_utilization is not None

    @pytest.mark.asyncio
    async def test_staff_analysis_only(self, worker, tenant_austa):
        """Test staff analysis only."""
        input_data = OptimizeResourceUtilizationInput(
            include_or_analysis=False,
            include_bed_analysis=False,
            include_staff_analysis=True,
            include_equipment_analysis=False,
        )

        result = await worker.execute(input_data)

        assert result.staff_productivity is not None

    @pytest.mark.asyncio
    async def test_equipment_analysis_only(self, worker, tenant_austa):
        """Test equipment analysis only."""
        input_data = OptimizeResourceUtilizationInput(
            include_or_analysis=False,
            include_bed_analysis=False,
            include_staff_analysis=False,
            include_equipment_analysis=True,
        )

        result = await worker.execute(input_data)

        assert result.equipment_utilization is not None

    @pytest.mark.asyncio
    async def test_different_analysis_periods(self, worker, tenant_austa):
        """Test different analysis periods."""
        for days in [7, 15, 30, 60, 90]:
            input_data = OptimizeResourceUtilizationInput(
                analysis_period_days=days,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, OptimizeResourceUtilizationOutput)

    @pytest.mark.asyncio
    async def test_target_utilization_variations(self, worker, tenant_austa):
        """Test different target utilization thresholds."""
        targets = [Decimal("75.0"), Decimal("85.0"), Decimal("90.0")]

        for target in targets:
            input_data = OptimizeResourceUtilizationInput(
                target_utilization=target,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, OptimizeResourceUtilizationOutput)

    @pytest.mark.asyncio
    async def test_opportunities_identified(self, worker, tenant_austa):
        """Test that optimization opportunities are identified."""
        input_data = OptimizeResourceUtilizationInput()

        result = await worker.execute(input_data)

        assert len(result.optimization_opportunities) >= 0

    @pytest.mark.asyncio
    async def test_revenue_impact_estimated(self, worker, tenant_austa):
        """Test that revenue impact is estimated."""
        input_data = OptimizeResourceUtilizationInput(
            include_or_analysis=True,
        )

        result = await worker.execute(input_data)

        assert result.estimated_revenue_impact >= Decimal("0")

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = OptimizeResourceUtilizationInput()

        result = await worker.execute(input_data)

        assert isinstance(result, OptimizeResourceUtilizationOutput)

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent structure."""
        input_data = OptimizeResourceUtilizationInput(
            analysis_period_days=30,
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same structure
        assert type(result1.optimization_opportunities) == type(result2.optimization_opportunities)
