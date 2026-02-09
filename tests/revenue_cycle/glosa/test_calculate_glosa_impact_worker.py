"""Tests for CalculateGlosaImpactWorker."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from platform.revenue_cycle.glosa.workers.calculate_glosa_impact_worker import (
    CalculateGlosaImpactWorker,
)
from platform.shared.domain.enums import GlosaType


@pytest.fixture
def worker():
    """Create worker instance for testing."""
    return CalculateGlosaImpactWorker()


@pytest.fixture
def sample_glosas():
    """Sample classified glosas for testing."""
    return [
        {
            "glosa_id": "G001",
            "denied_amount": Decimal("1000.00"),
            "original_amount": Decimal("1500.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE,
            "description": "Missing authorization"
        },
        {
            "glosa_id": "G002",
            "denied_amount": Decimal("500.00"),
            "original_amount": Decimal("500.00"),
            "glosa_type": GlosaType.TECHNICAL,
            "description": "Incompatible procedure"
        },
        {
            "glosa_id": "G003",
            "denied_amount": Decimal("300.00"),
            "original_amount": Decimal("600.00"),
            "glosa_type": GlosaType.LINEAR,
            "description": "50% linear glosa"
        }
    ]


@pytest.mark.asyncio
async def test_calculate_total_impact(worker, sample_glosas):
    """Test total impact calculation."""
    job = MagicMock()
    variables = {"classifiedGlosas": sample_glosas}

    result = await worker.process_task(job, variables)

    assert result.success is True
    assert result.variables["totalImpactBRL"] == Decimal("1800.00")


@pytest.mark.asyncio
async def test_impact_by_type(worker, sample_glosas):
    """Test impact calculation grouped by glosa type."""
    job = MagicMock()
    variables = {"classifiedGlosas": sample_glosas}

    result = await worker.process_task(job, variables)

    assert result.success is True
    impact_by_type = result.variables["impactByType"]

    assert impact_by_type[GlosaType.ADMINISTRATIVE] == Decimal("1000.00")
    assert impact_by_type[GlosaType.TECHNICAL] == Decimal("500.00")
    assert impact_by_type[GlosaType.LINEAR] == Decimal("300.00")


@pytest.mark.asyncio
async def test_recovery_potential_calculation(worker, sample_glosas):
    """Test recovery potential calculation with different glosa types."""
    job = MagicMock()
    variables = {"classifiedGlosas": sample_glosas}

    result = await worker.process_task(job, variables)

    assert result.success is True

    # Expected: 1000*0.80 + 500*0.60 + 300*0.40 = 800 + 300 + 120 = 1220
    expected_recovery = Decimal("1220.00")
    assert result.variables["recoveryPotentialBRL"] == expected_recovery


@pytest.mark.asyncio
async def test_zero_amount_glosas(worker):
    """Test handling of glosas with zero amounts."""
    glosas = [
        {
            "glosa_id": "G001",
            "denied_amount": Decimal("0.00"),
            "original_amount": Decimal("1000.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE
        }
    ]

    job = MagicMock()
    variables = {"classifiedGlosas": glosas}

    result = await worker.process_task(job, variables)

    assert result.success is True
    assert result.variables["totalImpactBRL"] == Decimal("0.00")
    assert result.variables["recoveryPotentialBRL"] == Decimal("0.00")
    assert result.variables["denialPercentage"] == 0.0


@pytest.mark.asyncio
async def test_denial_percentage(worker):
    """Test denial percentage calculation."""
    glosas = [
        {
            "glosa_id": "G001",
            "denied_amount": Decimal("750.00"),
            "original_amount": Decimal("1000.00"),
            "glosa_type": GlosaType.LINEAR
        },
        {
            "glosa_id": "G002",
            "denied_amount": Decimal("250.00"),
            "original_amount": Decimal("1000.00"),
            "glosa_type": GlosaType.PARTIAL
        }
    ]

    job = MagicMock()
    variables = {"classifiedGlosas": glosas}

    result = await worker.process_task(job, variables)

    assert result.success is True
    # Total denied: 1000, Total original: 2000 = 50%
    assert result.variables["denialPercentage"] == 50.0


@pytest.mark.asyncio
async def test_empty_glosas_list(worker):
    """Test handling of empty glosas list."""
    job = MagicMock()
    variables = {"classifiedGlosas": []}

    result = await worker.process_task(job, variables)

    assert result.success is False
    assert result.error_code == "NO_GLOSAS"


@pytest.mark.asyncio
async def test_impact_summary_generation(worker, sample_glosas):
    """Test Portuguese impact summary generation."""
    job = MagicMock()
    variables = {"classifiedGlosas": sample_glosas}

    result = await worker.process_task(job, variables)

    assert result.success is True
    summary = result.variables["impactSummary"]

    assert "Impacto total" in summary
    assert "Total de glosas: 3" in summary
    assert "Percentual negado" in summary
    assert "Potencial de recuperação" in summary
    assert "Impacto por tipo:" in summary


@pytest.mark.asyncio
async def test_parse_money_various_formats(worker):
    """Test money parsing from various formats."""
    assert worker._parse_money(Decimal("100.50")) == Decimal("100.50")
    assert worker._parse_money(100.5) == Decimal("100.50")
    assert worker._parse_money("100.50") == Decimal("100.50")
    assert worker._parse_money("R$ 1.234,56") == Decimal("1234.56")
    assert worker._parse_money(0) == Decimal("0.00")


@pytest.mark.asyncio
async def test_multiple_glosas_same_type(worker):
    """Test impact calculation with multiple glosas of the same type."""
    glosas = [
        {
            "glosa_id": "G001",
            "denied_amount": Decimal("100.00"),
            "original_amount": Decimal("100.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE
        },
        {
            "glosa_id": "G002",
            "denied_amount": Decimal("200.00"),
            "original_amount": Decimal("200.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE
        },
        {
            "glosa_id": "G003",
            "denied_amount": Decimal("150.00"),
            "original_amount": Decimal("150.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE
        }
    ]

    job = MagicMock()
    variables = {"classifiedGlosas": glosas}

    result = await worker.process_task(job, variables)

    assert result.success is True
    assert result.variables["totalImpactBRL"] == Decimal("450.00")
    impact_by_type = result.variables["impactByType"]
    assert impact_by_type[GlosaType.ADMINISTRATIVE] == Decimal("450.00")
    assert len(impact_by_type) == 1


@pytest.mark.asyncio
async def test_recovery_rate_by_type(worker):
    """Test recovery rate calculation for each glosa type."""
    assert worker._get_recovery_rate(GlosaType.ADMINISTRATIVE) == Decimal("0.80")
    assert worker._get_recovery_rate(GlosaType.TECHNICAL) == Decimal("0.60")
    assert worker._get_recovery_rate(GlosaType.LINEAR) == Decimal("0.40")
    assert worker._get_recovery_rate(GlosaType.PARTIAL) == Decimal("0.50")
    assert worker._get_recovery_rate(GlosaType.TOTAL) == Decimal("0.30")
