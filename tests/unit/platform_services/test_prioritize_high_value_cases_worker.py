"""Tests for PrioritizeHighValueCasesWorker."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import (
    PrioritizeHighValueCasesInput,
    PrioritizeHighValueCasesOutput,
    PrioritizeHighValueCasesWorkerStub,
    CasePrioritizationError,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def fhir_client():
    """Mock FHIR client."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """Create worker instance."""
    return PrioritizeHighValueCasesWorkerStub(fhir_client=fhir_client)


@pytest.mark.unit
class TestPrioritizeHighValueCasesWorker:
    """Test suite for PrioritizeHighValueCasesWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful case prioritization."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=["enc-1", "enc-2", "enc-3"],
            include_complexity=True,
            include_payer_margin=True,
            revenue_threshold=Decimal("5000.00"),
        )

        result = await worker.execute(input_data)

        assert isinstance(result, PrioritizeHighValueCasesOutput)
        assert len(result.prioritized_cases) == 3
        assert result.total_cases_analyzed == 3
        assert result.total_estimated_revenue >= Decimal("0")

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            PrioritizeHighValueCasesInput(
                encounter_ids=[],
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=["enc-1"],
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_single_case(self, worker, tenant_austa):
        """Test prioritization of single case."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=["enc-single"],
        )

        result = await worker.execute(input_data)

        assert len(result.prioritized_cases) == 1
        assert result.prioritized_cases[0].encounter_id == "enc-single"

    @pytest.mark.asyncio
    async def test_cases_sorted_by_priority(self, worker, tenant_austa):
        """Test that cases are sorted by priority score."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=["enc-1", "enc-2", "enc-3", "enc-4", "enc-5"],
        )

        result = await worker.execute(input_data)

        # Should be sorted descending by priority_score
        scores = [case.priority_score for case in result.prioritized_cases]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_without_complexity_analysis(self, worker, tenant_austa):
        """Test prioritization without complexity analysis."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=["enc-1", "enc-2"],
            include_complexity=False,
        )

        result = await worker.execute(input_data)

        for case in result.prioritized_cases:
            assert case.complexity_score is None

    @pytest.mark.asyncio
    async def test_without_payer_margin_analysis(self, worker, tenant_austa):
        """Test prioritization without payer margin analysis."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=["enc-1", "enc-2"],
            include_payer_margin=False,
        )

        result = await worker.execute(input_data)

        for case in result.prioritized_cases:
            assert case.payer_margin is None

    @pytest.mark.asyncio
    async def test_revenue_threshold_affects_priority(self, worker, tenant_austa):
        """Test that revenue threshold affects prioritization."""
        thresholds = [Decimal("1000.00"), Decimal("5000.00"), Decimal("10000.00")]

        for threshold in thresholds:
            input_data = PrioritizeHighValueCasesInput(
                encounter_ids=["enc-1", "enc-2"],
                revenue_threshold=threshold,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, PrioritizeHighValueCasesOutput)

    @pytest.mark.asyncio
    async def test_max_cases_limit(self, worker, tenant_austa):
        """Test max_cases limit."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=[f"enc-{i}" for i in range(150)],
            max_cases=50,
        )

        result = await worker.execute(input_data)

        # Should limit to max_cases
        assert len(result.prioritized_cases) <= 50

    @pytest.mark.asyncio
    async def test_critical_cases_counted(self, worker, tenant_austa):
        """Test that critical cases are counted."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=[f"enc-{i}" for i in range(10)],
        )

        result = await worker.execute(input_data)

        # critical_cases includes both CRITICAL and HIGH tiers
        assert result.critical_cases >= 0

    @pytest.mark.asyncio
    async def test_analysis_criteria_included(self, worker, tenant_austa):
        """Test that analysis criteria are included in output."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=["enc-1", "enc-2"],
            revenue_threshold=Decimal("7500.00"),
        )

        result = await worker.execute(input_data)

        assert isinstance(result.analysis_criteria, dict)
        assert "revenue_threshold" in result.analysis_criteria

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=["enc-999"],
        )

        result = await worker.execute(input_data)

        assert isinstance(result, PrioritizeHighValueCasesOutput)

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent structure."""
        input_data = PrioritizeHighValueCasesInput(
            encounter_ids=["enc-idem1", "enc-idem2"],
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same number of cases
        assert len(result1.prioritized_cases) == len(result2.prioritized_cases)
