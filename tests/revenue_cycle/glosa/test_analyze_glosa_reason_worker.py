"""Tests for AnalyzeGlosaReasonWorker."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from platform.revenue_cycle.glosa.workers.analyze_glosa_reason_worker import (
    AnalyzeGlosaReasonWorker,
)
from platform.shared.domain.enums import GlosaReasonCode, GlosaType


@pytest.fixture
def worker():
    """Create worker instance for testing."""
    return AnalyzeGlosaReasonWorker()


@pytest.fixture
def sample_glosas():
    """Sample classified glosas for testing."""
    return [
        {
            "glosa_id": "G001",
            "denied_amount": Decimal("1000.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE,
            "description": "Autorização ausente para procedimento"
        },
        {
            "glosa_id": "G002",
            "denied_amount": Decimal("500.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE,
            "description": "Autorização vencida"
        },
        {
            "glosa_id": "G003",
            "denied_amount": Decimal("300.00"),
            "glosa_type": GlosaType.TECHNICAL,
            "description": "Código incompatível com diagnóstico"
        }
    ]


@pytest.mark.asyncio
async def test_map_to_reason_codes(worker, sample_glosas):
    """Test mapping glosas to GlosaReasonCode."""
    job = MagicMock()
    variables = {"classifiedGlosas": sample_glosas, "claimId": "CLM-001"}

    result = await worker.process_task(job, variables)

    assert result.success is True
    analyzed = result.variables["analyzedGlosas"]

    assert len(analyzed) == 3
    assert analyzed[0]["reason_code"] == GlosaReasonCode.MISSING_AUTH
    assert analyzed[1]["reason_code"] == GlosaReasonCode.EXPIRED_AUTH
    assert analyzed[2]["reason_code"] == GlosaReasonCode.INCOMPATIBLE_PROCEDURE

    # Check Portuguese descriptions are added
    assert "reason_description" in analyzed[0]
    assert analyzed[0]["reason_description"] == "Autorização ausente"


@pytest.mark.asyncio
async def test_identify_systemic_patterns(worker):
    """Test identification of systemic issues with multiple auth problems."""
    # Create 5 authorization issues (should trigger pattern)
    glosas = [
        {
            "glosa_id": f"G00{i}",
            "denied_amount": Decimal("100.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE,
            "description": "Autorização ausente"
        }
        for i in range(5)
    ]

    job = MagicMock()
    variables = {"classifiedGlosas": glosas, "claimId": "CLM-001"}

    result = await worker.process_task(job, variables)

    assert result.success is True
    patterns = result.variables["rootCausePatterns"]

    # Should identify authorization pattern
    auth_pattern = next((p for p in patterns if p["pattern_type"] == "authorization_process"), None)
    assert auth_pattern is not None
    assert auth_pattern["occurrences"] == 5
    assert auth_pattern["severity"] == "high"


@pytest.mark.asyncio
async def test_single_glosa_no_pattern(worker):
    """Test that single glosa doesn't trigger pattern detection."""
    glosas = [
        {
            "glosa_id": "G001",
            "denied_amount": Decimal("100.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE,
            "description": "Autorização ausente"
        }
    ]

    job = MagicMock()
    variables = {"classifiedGlosas": glosas, "claimId": "CLM-001"}

    result = await worker.process_task(job, variables)

    assert result.success is True
    patterns = result.variables["rootCausePatterns"]
    systemic_issues = result.variables["systemicIssues"]

    # Should not identify patterns with single occurrence
    assert len(patterns) == 0
    # May identify systemic issue if it's 100% of glosas
    assert len(systemic_issues) >= 0


@pytest.mark.asyncio
async def test_reason_distribution(worker, sample_glosas):
    """Test reason code distribution calculation."""
    job = MagicMock()
    variables = {"classifiedGlosas": sample_glosas, "claimId": "CLM-001"}

    result = await worker.process_task(job, variables)

    assert result.success is True
    distribution = result.variables["reasonDistribution"]

    assert distribution[GlosaReasonCode.MISSING_AUTH] == 1
    assert distribution[GlosaReasonCode.EXPIRED_AUTH] == 1
    assert distribution[GlosaReasonCode.INCOMPATIBLE_PROCEDURE] == 1
    assert len(distribution) == 3


@pytest.mark.asyncio
async def test_detect_systemic_issues(worker):
    """Test systemic issue detection when >50% have same reason."""
    # 6 out of 10 glosas have same reason (60%)
    glosas = [
        {
            "glosa_id": f"G00{i}",
            "denied_amount": Decimal("100.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE,
            "description": "Documentação ausente"
        }
        for i in range(6)
    ]
    glosas.extend([
        {
            "glosa_id": f"G10{i}",
            "denied_amount": Decimal("100.00"),
            "glosa_type": GlosaType.TECHNICAL,
            "description": "Código incorreto"
        }
        for i in range(4)
    ])

    job = MagicMock()
    variables = {"classifiedGlosas": glosas, "claimId": "CLM-001"}

    result = await worker.process_task(job, variables)

    assert result.success is True
    systemic_issues = result.variables["systemicIssues"]

    # Should identify systemic issue for missing documentation (60%)
    assert len(systemic_issues) > 0
    assert any("Documentação ausente" in issue for issue in systemic_issues)


@pytest.mark.asyncio
async def test_empty_glosas_list(worker):
    """Test handling of empty glosas list."""
    job = MagicMock()
    variables = {"classifiedGlosas": [], "claimId": "CLM-001"}

    result = await worker.process_task(job, variables)

    assert result.success is False
    assert result.error_code == "NO_GLOSAS"


@pytest.mark.asyncio
async def test_infer_reason_from_description(worker):
    """Test reason code inference from various description patterns."""
    test_cases = [
        ("Cobrança duplicada", GlosaReasonCode.DUPLICATE_CHARGE),
        ("Quantidade excedida", GlosaReasonCode.EXCEEDS_QUANTITY),
        ("Procedimento não coberto", GlosaReasonCode.NOT_COVERED),
        ("Divergência de preço", GlosaReasonCode.PRICE_DIVERGENCE),
        ("Falha validação TISS", GlosaReasonCode.TISS_VALIDATION),
    ]

    for description, expected_code in test_cases:
        glosa = {
            "description": description,
            "glosa_type": GlosaType.ADMINISTRATIVE
        }
        inferred_code = worker._infer_reason_code(glosa)
        assert inferred_code == expected_code


@pytest.mark.asyncio
async def test_documentation_gap_pattern(worker):
    """Test detection of documentation gap pattern."""
    glosas = [
        {
            "glosa_id": f"G00{i}",
            "denied_amount": Decimal("100.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE,
            "description": "Documentação incompleta"
        }
        for i in range(4)
    ]

    job = MagicMock()
    variables = {"classifiedGlosas": glosas, "claimId": "CLM-001"}

    result = await worker.process_task(job, variables)

    assert result.success is True
    patterns = result.variables["rootCausePatterns"]

    doc_pattern = next((p for p in patterns if p["pattern_type"] == "documentation_gap"), None)
    assert doc_pattern is not None
    assert doc_pattern["occurrences"] == 4


@pytest.mark.asyncio
async def test_duplicate_charge_critical_pattern(worker):
    """Test that duplicate charges are marked as critical severity."""
    glosas = [
        {
            "glosa_id": f"G00{i}",
            "denied_amount": Decimal("100.00"),
            "glosa_type": GlosaType.ADMINISTRATIVE,
            "description": "Cobrança duplicada"
        }
        for i in range(3)
    ]

    job = MagicMock()
    variables = {"classifiedGlosas": glosas, "claimId": "CLM-001"}

    result = await worker.process_task(job, variables)

    assert result.success is True
    patterns = result.variables["rootCausePatterns"]

    dup_pattern = next((p for p in patterns if p["pattern_type"] == "billing_control"), None)
    assert dup_pattern is not None
    assert dup_pattern["severity"] == "critical"
