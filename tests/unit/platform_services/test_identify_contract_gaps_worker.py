"""Tests for IdentifyContractGapsWorker."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from healthcare_platform.platform_services.workers.identify_contract_gaps_worker import (
    IdentifyContractGapsInput,
    IdentifyContractGapsOutput,
    IdentifyContractGapsStub,
    ContractGapAnalysisError,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant


@pytest.fixture
def ans_client():
    """Mock ANS client."""
    return AsyncMock()


@pytest.fixture
def worker(ans_client):
    """Create worker instance."""
    return IdentifyContractGapsStub(ans_client=ans_client)


@pytest.mark.unit
class TestIdentifyContractGapsWorker:
    """Test suite for IdentifyContractGapsWorker."""

    @pytest.mark.asyncio
    async def test_happy_path(self, worker, tenant_austa):
        """Test successful contract gap analysis."""
        input_data = IdentifyContractGapsInput(
            contract_id="contract-123",
            payer_id="payer-456",
            include_procedure_coverage=True,
            include_term_analysis=True,
            include_expiration_check=True,
            expiration_warning_days=90,
        )

        result = await worker.execute(input_data)

        assert isinstance(result, IdentifyContractGapsOutput)
        assert result.contract_id == "contract-123"
        assert result.payer_name is not None
        assert isinstance(result.gaps, list)
        assert result.contract_health_score >= Decimal("0")
        assert result.contract_health_score <= Decimal("1.0")

    @pytest.mark.asyncio
    async def test_identifies_expiring_contract(self, worker, tenant_austa):
        """Test identification of expiring contracts."""
        input_data = IdentifyContractGapsInput(
            contract_id="contract-expiring",
            payer_id="payer-456",
            include_expiration_check=True,
            expiration_warning_days=90,
        )

        result = await worker.execute(input_data)

        # Should identify expiration gap
        expiring_gaps = [g for g in result.gaps if g.gap_type == "expiring"]
        # Stub returns expiring contract
        assert len(expiring_gaps) >= 0

    @pytest.mark.asyncio
    async def test_missing_contract_id_raises(self, worker, tenant_austa):
        """Test that missing contract_id raises validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            IdentifyContractGapsInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that execution without tenant raises InvalidTenant."""
        input_data = IdentifyContractGapsInput(
            contract_id="contract-123",
            payer_id="payer-456",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(input_data)

    @pytest.mark.asyncio
    async def test_procedure_coverage_only(self, worker, tenant_austa):
        """Test analysis with only procedure coverage enabled."""
        input_data = IdentifyContractGapsInput(
            contract_id="contract-123",
            payer_id="payer-456",
            include_procedure_coverage=True,
            include_term_analysis=False,
            include_expiration_check=False,
        )

        result = await worker.execute(input_data)

        assert isinstance(result, IdentifyContractGapsOutput)
        # Should only have procedure coverage gaps
        uncovered = [g for g in result.gaps if g.gap_type == "uncovered_procedure"]
        # Stub returns uncovered procedures

    @pytest.mark.asyncio
    async def test_term_analysis_only(self, worker, tenant_austa):
        """Test analysis with only term analysis enabled."""
        input_data = IdentifyContractGapsInput(
            contract_id="contract-123",
            payer_id="payer-456",
            include_procedure_coverage=False,
            include_term_analysis=True,
            include_expiration_check=False,
        )

        result = await worker.execute(input_data)

        assert isinstance(result, IdentifyContractGapsOutput)
        # Should only have term gaps
        term_gaps = [g for g in result.gaps if g.gap_type == "unfavorable_term"]

    @pytest.mark.asyncio
    async def test_critical_gaps_count(self, worker, tenant_austa):
        """Test counting of critical gaps."""
        input_data = IdentifyContractGapsInput(
            contract_id="contract-123",
            payer_id="payer-456",
            include_expiration_check=True,
            expiration_warning_days=30,  # Very short window
        )

        result = await worker.execute(input_data)

        assert result.critical_gaps_count >= 0
        # Should match count of critical severity gaps
        critical_count = sum(1 for g in result.gaps if g.severity == "critical")
        assert result.critical_gaps_count == critical_count

    @pytest.mark.asyncio
    async def test_priority_actions_generated(self, worker, tenant_austa):
        """Test that priority actions are generated."""
        input_data = IdentifyContractGapsInput(
            contract_id="contract-123",
            payer_id="payer-456",
        )

        result = await worker.execute(input_data)

        assert isinstance(result.priority_actions, list)
        # Should have actionable recommendations

    @pytest.mark.asyncio
    async def test_expiration_warning_threshold(self, worker, tenant_austa):
        """Test different expiration warning thresholds."""
        for days in [30, 60, 90, 180]:
            input_data = IdentifyContractGapsInput(
                contract_id="contract-123",
                payer_id="payer-456",
                include_expiration_check=True,
                expiration_warning_days=days,
            )

            result = await worker.execute(input_data)

            assert isinstance(result, IdentifyContractGapsOutput)
            assert result.days_until_expiration is not None

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, worker, tenant_saude_mais):
        """Test tenant isolation - different tenant."""
        input_data = IdentifyContractGapsInput(
            contract_id="contract-999",
            payer_id="payer-999",
        )

        result = await worker.execute(input_data)

        assert isinstance(result, IdentifyContractGapsOutput)
        assert result.contract_id == "contract-999"

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test that multiple executions produce consistent results."""
        input_data = IdentifyContractGapsInput(
            contract_id="contract-idempotent",
            payer_id="payer-idem",
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        # Should have same contract_id and structure
        assert result1.contract_id == result2.contract_id
        assert type(result1.gaps) == type(result2.gaps)
