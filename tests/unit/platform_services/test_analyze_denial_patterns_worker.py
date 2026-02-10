"""Tests for AnalyzeDenialPatternsWorker."""
from __future__ import annotations
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.platform_services.workers.analyze_denial_patterns_worker import (
    AnalyzeDenialPatternsInput,
    AnalyzeDenialPatternsOutput,
    DenialPatternAnalysisError,
    AnalyzeDenialPatternsStub,
)


@pytest.fixture
def ans_client():
    """Mock ANS client."""
    return AsyncMock()


@pytest.fixture
def worker(ans_client):
    """Create worker instance."""
    return AnalyzeDenialPatternsStub(ans_client=ans_client)


@pytest.fixture
def valid_input():
    """Valid input for denial pattern analysis."""
    return AnalyzeDenialPatternsInput(
        payer_id="PAY001",
        analysis_period_days=90,
        include_ml_predictions=True,
        min_pattern_frequency=3,
    )


@pytest.mark.unit
class TestAnalyzeDenialPatternsWorker:
    @pytest.mark.asyncio
    async def test_happy_path(self, worker, valid_input, tenant_austa):
        """Test successful denial pattern analysis."""
        result = await worker.execute(valid_input)

        assert isinstance(result, AnalyzeDenialPatternsOutput)
        assert result.payer_id == "PAY001"
        assert result.analysis_id is not None
        assert len(result.patterns) >= 0
        assert result.total_denials_analyzed >= 0
        assert result.overall_denial_rate >= Decimal("0")

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(Exception):
            AnalyzeDenialPatternsInput()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        valid_input = AnalyzeDenialPatternsInput(
            payer_id="PAY001",
        )

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_input)

    @pytest.mark.asyncio
    async def test_ml_predictions_enabled(self, worker, tenant_austa):
        """Test ML predictions when enabled."""
        input_data = AnalyzeDenialPatternsInput(
            payer_id="PAY001",
            include_ml_predictions=True,
        )

        result = await worker.execute(input_data)

        assert len(result.ml_predictions) > 0
        for prediction in result.ml_predictions:
            assert Decimal("0") <= prediction.predicted_denial_probability <= Decimal("1")

    @pytest.mark.asyncio
    async def test_ml_predictions_disabled(self, worker, tenant_austa):
        """Test ML predictions when disabled."""
        input_data = AnalyzeDenialPatternsInput(
            payer_id="PAY001",
            include_ml_predictions=False,
        )

        result = await worker.execute(input_data)

        assert result.ml_predictions == []

    @pytest.mark.asyncio
    async def test_pattern_frequency_filter(self, worker, tenant_austa):
        """Test minimum pattern frequency filtering."""
        input_data = AnalyzeDenialPatternsInput(
            payer_id="PAY001",
            min_pattern_frequency=5,
        )

        result = await worker.execute(input_data)

        # All patterns should meet minimum frequency
        for pattern in result.patterns:
            assert pattern.frequency >= 5

    @pytest.mark.asyncio
    async def test_procedure_filter(self, worker, tenant_austa):
        """Test procedure filter."""
        input_data = AnalyzeDenialPatternsInput(
            payer_id="PAY001",
            procedure_filter=["10101012", "20202020"],
        )

        result = await worker.execute(input_data)

        assert result.payer_id == "PAY001"

    @pytest.mark.asyncio
    async def test_high_risk_patterns(self, worker, tenant_austa):
        """Test high risk pattern identification."""
        input_data = AnalyzeDenialPatternsInput(
            payer_id="PAY001",
        )

        result = await worker.execute(input_data)

        # High risk patterns should have risk_score > 0.7
        high_risk = [p for p in result.patterns if p.risk_score > Decimal("0.7")]
        assert result.high_risk_patterns_count >= len(high_risk)

    @pytest.mark.asyncio
    async def test_actionable_insights(self, worker, tenant_austa):
        """Test actionable insights generation."""
        input_data = AnalyzeDenialPatternsInput(
            payer_id="PAY001",
        )

        result = await worker.execute(input_data)

        assert len(result.actionable_insights) > 0

    @pytest.mark.asyncio
    async def test_pattern_structure(self, worker, tenant_austa):
        """Test denial pattern structure."""
        input_data = AnalyzeDenialPatternsInput(
            payer_id="PAY001",
        )

        result = await worker.execute(input_data)

        if result.patterns:
            pattern = result.patterns[0]
            assert pattern.pattern_id is not None
            assert pattern.denial_reason_code is not None
            assert pattern.frequency > 0
            assert pattern.total_denied_amount >= Decimal("0")
            assert len(pattern.root_causes) > 0
            assert len(pattern.prevention_recommendations) > 0

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotency of analysis."""
        input_data = AnalyzeDenialPatternsInput(
            payer_id="PAY001",
        )

        result1 = await worker.execute(input_data)
        result2 = await worker.execute(input_data)

        assert result1.payer_id == result2.payer_id
        assert len(result1.patterns) == len(result2.patterns)
