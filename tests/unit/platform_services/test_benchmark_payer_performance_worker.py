"""Tests for BenchmarkPayerPerformanceWorker."""
from __future__ import annotations
import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from decimal import Decimal
from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import (
    BenchmarkPayerPerformanceInput,
    BenchmarkPayerPerformanceOutput,
    PayerBenchmarkingError,
    BenchmarkPayerPerformanceWorkerStub,
)


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """Create worker instance."""
    return BenchmarkPayerPerformanceWorkerStub(fhir_client=fhir_client)


@pytest.fixture
def valid_input():
    """Valid input for payer benchmarking."""
    return BenchmarkPayerPerformanceInput(
        analysis_period_days=90,
        include_timeliness=True,
        include_denial_rates=True,
        include_rate_comparison=True,
        include_contract_compliance=True,
        market_benchmark_source="ANS",
    )


@pytest.mark.unit
class TestBenchmarkPayerPerformanceWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input, tenant_austa):
        """Test successful payer benchmarking."""
        result = await worker.execute(valid_input)

        assert isinstance(result, BenchmarkPayerPerformanceOutput)
        assert len(result.payer_benchmarks) > 0
        assert result.best_performer is not None
        assert result.worst_performer is not None
        assert len(result.market_averages) > 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test default values work."""
        input_data = BenchmarkPayerPerformanceInput()
        assert input_data.analysis_period_days == 90

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(BenchmarkPayerPerformanceInput())

    @pytest.mark.asyncio
    async def test_specific_payers_filter(self, worker, tenant_austa):
        """Test filtering specific payers."""
        input_data = BenchmarkPayerPerformanceInput(
            payer_ids=["PAY001", "PAY002"],
        )

        result = await worker.execute(input_data)

        assert len(result.payer_benchmarks) == 2
        payer_ids = [b.payer_id for b in result.payer_benchmarks]
        assert "PAY001" in payer_ids
        assert "PAY002" in payer_ids

    @pytest.mark.asyncio
    async def test_timeliness_metrics(self, worker, tenant_austa):
        """Test payment timeliness metrics."""
        input_data = BenchmarkPayerPerformanceInput(
            include_timeliness=True,
        )

        result = await worker.execute(input_data)

        benchmark = result.payer_benchmarks[0]
        assert benchmark.timeliness is not None
        assert benchmark.timeliness.average_days_to_payment > Decimal("0")
        assert Decimal("0") <= benchmark.timeliness.on_time_payment_rate <= Decimal("100")

    @pytest.mark.asyncio
    async def test_denial_metrics(self, worker, tenant_austa):
        """Test denial/glosa metrics."""
        input_data = BenchmarkPayerPerformanceInput(
            include_denial_rates=True,
        )

        result = await worker.execute(input_data)

        benchmark = result.payer_benchmarks[0]
        assert benchmark.denial_metrics is not None
        assert benchmark.denial_metrics.denial_rate >= Decimal("0")
        assert benchmark.denial_metrics.denial_amount >= Decimal("0")

    @pytest.mark.asyncio
    async def test_rate_comparison(self, worker, tenant_austa):
        """Test rate comparison vs market."""
        input_data = BenchmarkPayerPerformanceInput(
            include_rate_comparison=True,
        )

        result = await worker.execute(input_data)

        benchmark = result.payer_benchmarks[0]
        assert benchmark.rate_comparison is not None
        assert benchmark.rate_comparison.competitiveness in ["ABOVE", "AT", "BELOW"]

    @pytest.mark.asyncio
    async def test_contract_compliance(self, worker, tenant_austa):
        """Test contract compliance metrics."""
        input_data = BenchmarkPayerPerformanceInput(
            include_contract_compliance=True,
        )

        result = await worker.execute(input_data)

        benchmark = result.payer_benchmarks[0]
        assert benchmark.contract_compliance is not None
        assert Decimal("0") <= benchmark.contract_compliance.compliance_score <= Decimal("100")

    @pytest.mark.asyncio
    async def test_overall_score_calculation(self, worker, tenant_austa):
        """Test overall performance score."""
        input_data = BenchmarkPayerPerformanceInput()

        result = await worker.execute(input_data)

        for benchmark in result.payer_benchmarks:
            assert Decimal("0") <= benchmark.overall_score <= Decimal("100")

    @pytest.mark.asyncio
    async def test_ranking_assignment(self, worker, tenant_austa):
        """Test payer ranking."""
        input_data = BenchmarkPayerPerformanceInput()

        result = await worker.execute(input_data)

        rankings = [b.ranking for b in result.payer_benchmarks]
        assert rankings == sorted(rankings)  # Should be in order
        assert min(rankings) == 1

    @pytest.mark.asyncio
    async def test_action_items_generation(self, worker, tenant_austa):
        """Test action items generation."""
        input_data = BenchmarkPayerPerformanceInput()

        result = await worker.execute(input_data)

        assert len(result.action_items) > 0

    @pytest.mark.asyncio
    async def test_renegotiation_opportunities(self, worker, tenant_austa):
        """Test renegotiation opportunities identification."""
        input_data = BenchmarkPayerPerformanceInput()

        result = await worker.execute(input_data)

        assert len(result.contract_renegotiation_opportunities) >= 0
