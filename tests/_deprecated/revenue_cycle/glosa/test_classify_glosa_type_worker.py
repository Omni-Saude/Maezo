"""
from __future__ import annotations

Tests for ClassifyGlosaTypeWorker

Tests glosa type classification including administrative, technical, linear,
total, and partial categorization.
"""

from unittest.mock import Mock

import pytest

from healthcare_platform.revenue_cycle.glosa.workers import ClassifyGlosaTypeWorker
from healthcare_platform.shared.domain.enums import GlosaReasonCode, GlosaType


@pytest.fixture
def worker(mock_dmn_service):
    """Create worker instance for testing with mocked DMN service."""
    return ClassifyGlosaTypeWorker(dmn_service=mock_dmn_service)


@pytest.fixture
def mock_job():
    """Create mock Zeebe job."""
    job = Mock()
    job.key = "test-job-456"
    return job


@pytest.fixture
def sample_glosa_items():
    """Create sample glosa items for classification."""
    return [
        {
            "item_sequence": 1,
            "procedure_code": "40101010",
            "reason_code": GlosaReasonCode.MISSING_AUTH.value,
            "reason_display": "Autorização ausente ou inválida",
            "denied_amount": 1000.00,
            "original_amount": 1000.00,
            "notes": "Guia não apresentada",
        },
        {
            "item_sequence": 2,
            "procedure_code": "40101020",
            "reason_code": GlosaReasonCode.EXCEEDS_QUANTITY.value,
            "reason_display": "Quantidade excede limite autorizado",
            "denied_amount": 500.00,
            "original_amount": 2000.00,
            "notes": "Autorizado 1, cobrado 2",
        },
        {
            "item_sequence": 3,
            "procedure_code": "40101030",
            "reason_code": GlosaReasonCode.PRICE_DIVERGENCE.value,
            "reason_display": "Divergência no valor cobrado",
            "denied_amount": 200.00,
            "original_amount": 1200.00,
            "notes": "Tabela: R$ 1000",
        },
    ]


@pytest.mark.asyncio
async def test_classify_administrative_glosa(worker, mock_job):
    """Test classification of administrative glosas."""
    glosa_items = [
        {
            "item_sequence": 1,
            "procedure_code": "40101010",
            "reason_code": GlosaReasonCode.MISSING_AUTH.value,
            "denied_amount": 1000.00,
            "original_amount": 1000.00,
        },
        {
            "item_sequence": 2,
            "procedure_code": "40101020",
            "reason_code": GlosaReasonCode.EXPIRED_AUTH.value,
            "denied_amount": 500.00,
            "original_amount": 500.00,
        },
        {
            "item_sequence": 3,
            "procedure_code": "40101030",
            "reason_code": GlosaReasonCode.DUPLICATE_CHARGE.value,
            "denied_amount": 300.00,
            "original_amount": 300.00,
        },
    ]

    variables = {"glosaItems": glosa_items}

    result = await worker.process_task(mock_job, variables)

    assert result.success is True
    assert result.variables["hasAdministrative"] is True

    classified = result.variables["classifiedGlosas"]
    assert len(classified) == 3

    # All should be administrative
    for glosa in classified:
        assert glosa["glosa_type"] == GlosaType.ADMINISTRATIVE.value

    distribution = result.variables["glosaTypeDistribution"]
    assert distribution[GlosaType.ADMINISTRATIVE.value] == 3


@pytest.mark.asyncio
async def test_classify_technical_glosa(worker, mock_job):
    """Test classification of technical glosas."""
    glosa_items = [
        {
            "item_sequence": 1,
            "procedure_code": "40101010",
            "reason_code": GlosaReasonCode.NOT_COVERED.value,
            "denied_amount": 1000.00,
            "original_amount": 1000.00,
        },
        {
            "item_sequence": 2,
            "procedure_code": "40101020",
            "reason_code": GlosaReasonCode.WRONG_CODE.value,
            "denied_amount": 500.00,
            "original_amount": 500.00,
        },
        {
            "item_sequence": 3,
            "procedure_code": "40101030",
            "reason_code": GlosaReasonCode.INCOMPATIBLE_PROCEDURE.value,
            "denied_amount": 300.00,
            "original_amount": 300.00,
        },
    ]

    variables = {"glosaItems": glosa_items}

    result = await worker.process_task(mock_job, variables)

    assert result.success is True
    assert result.variables["hasTechnical"] is True

    classified = result.variables["classifiedGlosas"]
    assert len(classified) == 3

    # All should be technical
    for glosa in classified:
        assert glosa["glosa_type"] == GlosaType.TECHNICAL.value

    distribution = result.variables["glosaTypeDistribution"]
    assert distribution[GlosaType.TECHNICAL.value] == 3


@pytest.mark.asyncio
async def test_classify_total_vs_partial(worker, mock_job):
    """Test classification of total vs partial denials."""
    glosa_items = [
        {
            "item_sequence": 1,
            "procedure_code": "40101010",
            "reason_code": GlosaReasonCode.MISSING_AUTH.value,
            "denied_amount": 1000.00,
            "original_amount": 1000.00,  # 100% denied = TOTAL
        },
        {
            "item_sequence": 2,
            "procedure_code": "40101020",
            "reason_code": GlosaReasonCode.EXCEEDS_QUANTITY.value,
            "denied_amount": 500.00,
            "original_amount": 2000.00,  # 25% denied = PARTIAL
        },
        {
            "item_sequence": 3,
            "procedure_code": "40101030",
            "reason_code": GlosaReasonCode.NOT_COVERED.value,
            "denied_amount": 1500.00,
            "original_amount": 1500.00,  # 100% denied = TOTAL
        },
    ]

    variables = {"glosaItems": glosa_items}

    result = await worker.process_task(mock_job, variables)

    assert result.success is True

    classified = result.variables["classifiedGlosas"]
    assert len(classified) == 3

    # Check extents
    assert classified[0]["glosa_extent"] == GlosaType.TOTAL.value
    assert classified[0]["denial_ratio"] == 1.0

    assert classified[1]["glosa_extent"] == GlosaType.PARTIAL.value
    assert classified[1]["denial_ratio"] == 0.25

    assert classified[2]["glosa_extent"] == GlosaType.TOTAL.value
    assert classified[2]["denial_ratio"] == 1.0


@pytest.mark.asyncio
async def test_classify_linear_glosa(worker, mock_job):
    """Test classification of linear (price divergence) glosas."""
    glosa_items = [
        {
            "item_sequence": 1,
            "procedure_code": "40101010",
            "reason_code": GlosaReasonCode.PRICE_DIVERGENCE.value,
            "denied_amount": 200.00,
            "original_amount": 1200.00,
        }
    ]

    variables = {"glosaItems": glosa_items}

    result = await worker.process_task(mock_job, variables)

    assert result.success is True

    classified = result.variables["classifiedGlosas"]
    assert len(classified) == 1
    assert classified[0]["glosa_type"] == GlosaType.LINEAR.value
    assert classified[0]["glosa_extent"] == GlosaType.PARTIAL.value


@pytest.mark.asyncio
async def test_empty_glosa_list(worker, mock_job):
    """Test handling of empty glosa list."""
    variables = {"glosaItems": []}

    result = await worker.process_task(mock_job, variables)

    assert result.success is True
    assert result.variables["hasAdministrative"] is False
    assert result.variables["hasTechnical"] is False
    assert len(result.variables["classifiedGlosas"]) == 0

    distribution = result.variables["glosaTypeDistribution"]
    assert all(count == 0 for count in distribution.values())


@pytest.mark.asyncio
async def test_mixed_glosa_types(worker, mock_job, sample_glosa_items):
    """Test classification of mixed glosa types."""
    variables = {"glosaItems": sample_glosa_items}

    result = await worker.process_task(mock_job, variables)

    assert result.success is True
    assert result.variables["hasAdministrative"] is True
    assert result.variables["hasTechnical"] is True

    classified = result.variables["classifiedGlosas"]
    assert len(classified) == 3

    # Check type distribution
    distribution = result.variables["glosaTypeDistribution"]
    assert distribution[GlosaType.ADMINISTRATIVE.value] == 1  # MISSING_AUTH
    assert distribution[GlosaType.TECHNICAL.value] == 1  # EXCEEDS_QUANTITY
    assert distribution[GlosaType.LINEAR.value] == 1  # PRICE_DIVERGENCE


@pytest.mark.asyncio
async def test_filter_by_reason_code(worker, mock_job, sample_glosa_items):
    """Test filtering glosas by specific reason code."""
    variables = {
        "glosaItems": sample_glosa_items,
        "reasonCode": GlosaReasonCode.MISSING_AUTH.value,
    }

    result = await worker.process_task(mock_job, variables)

    assert result.success is True

    classified = result.variables["classifiedGlosas"]
    assert len(classified) == 1
    assert classified[0]["reason_code"] == GlosaReasonCode.MISSING_AUTH.value


@pytest.mark.asyncio
async def test_invalid_reason_code_handling(worker, mock_job):
    """Test handling of invalid reason codes."""
    glosa_items = [
        {
            "item_sequence": 1,
            "procedure_code": "40101010",
            "reason_code": "INVALID_CODE_999",
            "denied_amount": 1000.00,
            "original_amount": 1000.00,
        }
    ]

    variables = {"glosaItems": glosa_items}

    result = await worker.process_task(mock_job, variables)

    # Should still succeed with default technical classification
    assert result.success is True

    classified = result.variables["classifiedGlosas"]
    assert len(classified) == 1
    assert classified[0]["glosa_type"] == GlosaType.TECHNICAL.value


@pytest.mark.asyncio
async def test_denial_ratio_calculation(worker, mock_job):
    """Test accurate denial ratio calculation."""
    glosa_items = [
        {
            "item_sequence": 1,
            "procedure_code": "40101010",
            "reason_code": GlosaReasonCode.NOT_COVERED.value,
            "denied_amount": 750.00,
            "original_amount": 1000.00,  # 75% denial
        }
    ]

    variables = {"glosaItems": glosa_items}

    result = await worker.process_task(mock_job, variables)

    assert result.success is True

    classified = result.variables["classifiedGlosas"]
    assert len(classified) == 1
    assert classified[0]["denial_ratio"] == 0.75
    assert classified[0]["glosa_extent"] == GlosaType.PARTIAL.value
