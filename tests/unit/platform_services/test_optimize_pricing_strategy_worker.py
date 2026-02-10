"""Tests for OptimizePricingStrategyWorker."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.optimize_pricing_strategy_worker import (
    OptimizePricingStrategyInput,
    OptimizePricingStrategyOutput,
    OptimizePricingStrategyStub,
    PricingOptimizationError,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def ans_client():
    """Mock ANS client."""
    return AsyncMock()


@pytest.fixture
def worker(ans_client):
    """Create worker instance."""
    return OptimizePricingStrategyStub(ans_client=ans_client)


@pytest.mark.unit
class TestOptimizePricingStrategyWorker:
    """Test suite for OptimizePricingStrategyWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful pricing optimization."""
        input_data = OptimizePricingStrategyInput(
            payer_id="payer-123",
            contract_id="contract-456",
            include_market_benchmark=True,
            target_margin_percentage=Decimal("15.0"),
        )

        result = await worker.execute(input_data)

        assert isinstance(result, OptimizePricingStrategyOutput)
        assert result.contract_id == "contract-456"
        assert isinstance(result.opportunities, list)
        assert result.total_projected_increase >= Decimal("0")
        assert result.current_annual_revenue >= Decimal("0")

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            OptimizePricingStrategyInput(
                payer_id="payer-123",
                contract_id="",
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = OptimizePricingStrategyInput(
            payer_id="payer-123",
            contract_id="contract-456",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_with_specific_procedures(self, worker, tenant_austa):
        """Test optimization with specific procedure codes."""
        input_data = OptimizePricingStrategyInput(
            payer_id="payer-123",
            contract_id="contract-456",
            procedure_codes=["10101012", "20101020"],
        )

        result = await worker.execute(input_data)

        assert isinstance(result, OptimizePricingStrategyOutput)

    @pytest.mark.asyncio
    async def test_without_market_benchmark(self, worker, tenant_austa):
        """Test optimization without market benchmark."""
        input_data = OptimizePricingStrategyInput(
            payer_id="payer-123",
            contract_id="contract-456",
            include_market_benchmark=False,
        )

        result = await worker.execute(input_data)

        assert isinstance(result, OptimizePricingStrategyOutput)

    @pytest.mark.asyncio
    async def test_different_target_margins(self, worker, tenant_austa):
        """Test optimization with different target margins."""
        margins = [Decimal("10.0"), Decimal("15.0"), Decimal("20.0")]

        for margin in margins:
            input_data = OptimizePricingStrategyInput(
                payer_id="payer-123",
                contract_id="contract-456",
                target_margin_percentage=margin,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, OptimizePricingStrategyOutput)

    @pytest.mark.asyncio
    async def test_analysis_scope_variations(self, worker, tenant_austa):
        """Test different analysis scopes."""
        for scope in ["full", "quick", "procedures_only"]:
            input_data = OptimizePricingStrategyInput(
                payer_id="payer-123",
                contract_id="contract-456",
                analysis_scope=scope,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, OptimizePricingStrategyOutput)

    @pytest.mark.asyncio
    async def test_negotiation_recommendations_generated(self, worker, tenant_austa):
        """Test that negotiation recommendations are generated."""
        input_data = OptimizePricingStrategyInput(
            payer_id="payer-123",
            contract_id="contract-456",
        )

        result = await worker.execute(input_data)

        assert isinstance(result.negotiation_recommendations, list)

    @pytest.mark.asyncio
    async def test_market_benchmark_summary(self, worker, tenant_austa):
        """Test that market benchmark summary is included."""
        input_data = OptimizePricingStrategyInput(
            payer_id="payer-123",
            contract_id="contract-456",
            include_market_benchmark=True,
        )

        result = await worker.execute(input_data)

        assert isinstance(result.market_benchmark_summary, dict)
        assert "procedures_analyzed" in result.market_benchmark_summary

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = OptimizePricingStrategyInput(
            payer_id="payer-999",
            contract_id="contract-999",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, OptimizePricingStrategyOutput)
        assert result.contract_id == "contract-999"

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent results."""
        input_data = OptimizePricingStrategyInput(
            payer_id="payer-idem",
            contract_id="contract-idem",
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same contract_id and structure
        assert result1.contract_id == result2.contract_id
        assert type(result1.opportunities) == type(result2.opportunities)
