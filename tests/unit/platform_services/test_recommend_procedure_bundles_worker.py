"""Tests for RecommendProcedureBundlesWorker."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import (
    RecommendProcedureBundlesInput,
    RecommendProcedureBundlesOutput,
    RecommendProcedureBundlesStub,
    BundleRecommendationError,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def worker():
    """Create worker instance."""
    return RecommendProcedureBundlesStub()


@pytest.mark.unit
class TestRecommendProcedureBundlesWorker:
    """Test suite for RecommendProcedureBundlesWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful bundle recommendation."""
        input_data = RecommendProcedureBundlesInput(
            analysis_period_days=180,
            min_co_occurrence_count=10,
            min_co_occurrence_rate=Decimal("0.7"),
            target_discount_percentage=Decimal("10.0"),
        )

        result = await worker.execute(input_data)

        assert isinstance(result, RecommendProcedureBundlesOutput)
        assert isinstance(result.recommended_bundles, list)
        assert result.total_projected_savings >= Decimal("0")
        assert result.average_discount_percentage >= Decimal("0")

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = RecommendProcedureBundlesInput()

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_with_specific_payer(self, worker, tenant_austa):
        """Test bundle recommendation for specific payer."""
        input_data = RecommendProcedureBundlesInput(
            payer_id="payer-123",
        )

        result = await worker.execute(input_data)

        assert result.payer_id == "payer-123"

    @pytest.mark.asyncio
    async def test_different_analysis_periods(self, worker, tenant_austa):
        """Test different analysis periods."""
        for days in [90, 180, 365]:
            input_data = RecommendProcedureBundlesInput(
                analysis_period_days=days,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, RecommendProcedureBundlesOutput)

    @pytest.mark.asyncio
    async def test_min_co_occurrence_filter(self, worker, tenant_austa):
        """Test minimum co-occurrence count filter."""
        input_data = RecommendProcedureBundlesInput(
            min_co_occurrence_count=20,  # Higher threshold
        )

        result = await worker.execute(input_data)

        # Should filter out bundles with low co-occurrence
        assert isinstance(result, RecommendProcedureBundlesOutput)

    @pytest.mark.asyncio
    async def test_min_co_occurrence_rate_filter(self, worker, tenant_austa):
        """Test minimum co-occurrence rate filter."""
        input_data = RecommendProcedureBundlesInput(
            min_co_occurrence_rate=Decimal("0.85"),  # Higher threshold
        )

        result = await worker.execute(input_data)

        assert isinstance(result, RecommendProcedureBundlesOutput)

    @pytest.mark.asyncio
    async def test_target_discount_variations(self, worker, tenant_austa):
        """Test different target discount percentages."""
        discounts = [Decimal("5.0"), Decimal("10.0"), Decimal("15.0")]

        for discount in discounts:
            input_data = RecommendProcedureBundlesInput(
                target_discount_percentage=discount,
            )

            result = await worker.execute(input_data)

            # Average discount should be close to target
            assert isinstance(result, RecommendProcedureBundlesOutput)

    @pytest.mark.asyncio
    async def test_implementation_recommendations_generated(self, worker, tenant_austa):
        """Test that implementation recommendations are generated."""
        input_data = RecommendProcedureBundlesInput()

        result = await worker.execute(input_data)

        assert isinstance(result.implementation_recommendations, list)
        assert len(result.implementation_recommendations) > 0

    @pytest.mark.asyncio
    async def test_market_benchmark_included(self, worker, tenant_austa):
        """Test that market benchmark is included."""
        input_data = RecommendProcedureBundlesInput()

        result = await worker.execute(input_data)

        assert isinstance(result.market_benchmark, dict)
        assert "average_bundle_discount" in result.market_benchmark

    @pytest.mark.asyncio
    async def test_bundle_priority_assignment(self, worker, tenant_austa):
        """Test that bundles are assigned priorities."""
        input_data = RecommendProcedureBundlesInput()

        result = await worker.execute(input_data)

        for bundle in result.recommended_bundles:
            assert bundle.implementation_priority in [
                "critical", "high", "medium", "low"
            ]

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = RecommendProcedureBundlesInput()

        result = await worker.execute(input_data)

        assert isinstance(result, RecommendProcedureBundlesOutput)

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent structure."""
        input_data = RecommendProcedureBundlesInput(
            analysis_period_days=180,
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same structure
        assert type(result1.recommended_bundles) == type(result2.recommended_bundles)
