"""Tests for TrackOptimizationROIWorker."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.track_optimization_roi_worker import (
    TrackOptimizationROIInput,
    TrackOptimizationROIOutput,
    TrackOptimizationROIWorkerStub,
    OptimizationROITrackingError,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """Create worker instance."""
    return TrackOptimizationROIWorkerStub(fhir_client=fhir_client)


@pytest.mark.unit
class TestTrackOptimizationROIWorker:
    """Test suite for TrackOptimizationROIWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful ROI tracking."""
        input_data = TrackOptimizationROIInput(
            tracking_period_months=6,
            include_revenue_impact=True,
            include_cost_savings=True,
            include_efficiency_gains=True,
            calculate_payback_period=True,
            trend_analysis=True,
        )

        result = await worker.execute(input_data)

        assert isinstance(result, TrackOptimizationROIOutput)
        assert len(result.optimization_impacts) > 0
        assert result.overall_roi is not None
        assert result.total_investment >= Decimal("0")
        assert result.total_return >= Decimal("0")

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = TrackOptimizationROIInput()

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_specific_optimizations(self, worker, tenant_austa):
        """Test tracking specific optimizations."""
        input_data = TrackOptimizationROIInput(
            optimization_ids=["OPT001", "OPT002"],
        )

        result = await worker.execute(input_data)

        assert len(result.optimization_impacts) == 2
        assert result.optimization_impacts[0].optimization_id in ["OPT001", "OPT002"]

    @pytest.mark.asyncio
    async def test_all_optimizations(self, worker, tenant_austa):
        """Test tracking all optimizations."""
        input_data = TrackOptimizationROIInput(
            optimization_ids=None,  # Track all
        )

        result = await worker.execute(input_data)

        # Should return all optimizations (stub returns 5)
        assert len(result.optimization_impacts) >= 5

    @pytest.mark.asyncio
    async def test_different_tracking_periods(self, worker, tenant_austa):
        """Test different tracking periods."""
        for months in [3, 6, 12]:
            input_data = TrackOptimizationROIInput(
                tracking_period_months=months,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, TrackOptimizationROIOutput)

    @pytest.mark.asyncio
    async def test_payback_period_calculated(self, worker, tenant_austa):
        """Test that payback period is calculated."""
        input_data = TrackOptimizationROIInput(
            calculate_payback_period=True,
        )

        result = await worker.execute(input_data)

        # Should have average payback calculated
        assert result.average_payback_months >= Decimal("0")

    @pytest.mark.asyncio
    async def test_trend_analysis_included(self, worker, tenant_austa):
        """Test that trend analysis is included when requested."""
        input_data = TrackOptimizationROIInput(
            trend_analysis=True,
        )

        result = await worker.execute(input_data)

        assert result.monthly_trends is not None
        assert len(result.monthly_trends) > 0

    @pytest.mark.asyncio
    async def test_trend_analysis_excluded(self, worker, tenant_austa):
        """Test that trend analysis can be excluded."""
        input_data = TrackOptimizationROIInput(
            trend_analysis=False,
        )

        result = await worker.execute(input_data)

        assert result.monthly_trends is None

    @pytest.mark.asyncio
    async def test_category_roi_calculated(self, worker, tenant_austa):
        """Test that ROI by category is calculated."""
        input_data = TrackOptimizationROIInput()

        result = await worker.execute(input_data)

        assert len(result.category_roi) > 0
        for category in result.category_roi:
            assert category.roi_percentage is not None

    @pytest.mark.asyncio
    async def test_best_performing_identified(self, worker, tenant_austa):
        """Test that best performing optimization is identified."""
        input_data = TrackOptimizationROIInput()

        result = await worker.execute(input_data)

        assert result.best_performing_optimization is not None
        assert result.best_performing_optimization != "N/A"

    @pytest.mark.asyncio
    async def test_recommendations_generated(self, worker, tenant_austa):
        """Test that recommendations are generated."""
        input_data = TrackOptimizationROIInput()

        result = await worker.execute(input_data)

        assert isinstance(result.recommendations, list)
        assert len(result.recommendations) > 0

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = TrackOptimizationROIInput()

        result = await worker.execute(input_data)

        assert isinstance(result, TrackOptimizationROIOutput)

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent structure."""
        input_data = TrackOptimizationROIInput(
            tracking_period_months=6,
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same number of optimizations
        assert len(result1.optimization_impacts) == len(result2.optimization_impacts)
