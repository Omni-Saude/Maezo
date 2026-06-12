from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker import SuggestCid10Worker
from healthcare_platform.shared.domain.exceptions import CodingException


@pytest.fixture
def tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = "test-tenant"
    return ctx


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker.get_required_tenant')
async def test_happy_path_with_suggestions(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"suggestions": [{"code": "A01.0", "confidence": 0.9}]},
        {"valid_suggestions": [{"code": "A01.0", "confidence": 0.9, "description": "Typhoid fever"}]},
    ]

    worker = SuggestCid10Worker(dmn_service=mock_dmn)
    result = await worker.execute({
        "clinical_notes": "Febre tifoide com complicações",
        "extracted_diagnoses": [{"description": "Febre tifoide"}],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert result["cid10_count"] == 1
    assert result["primary_cid10"] == "A01.0"
    assert len(result["suggested_cid10_codes"]) == 1
    assert result["suggested_cid10_codes"][0]["code"] == "A01.0"
    assert mock_dmn.evaluate.call_count == 2


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker.get_required_tenant')
async def test_empty_clinical_data_error(mock_get_tenant, tenant_ctx):
    """Empty string fails Pydantic min_length=1 on clinical_notes, wrapped as CodingException-like."""
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    worker = SuggestCid10Worker(dmn_service=mock_dmn)

    # clinical_notes="" fails Pydantic min_length=1 → ValidationError
    # The worker doesn't catch this, so it raises as-is
    with pytest.raises(Exception):
        await worker.execute({
            "clinical_notes": "",
            "extracted_diagnoses": [],
            "encounter_class": "ambulatorio",
            "tenant_id": "test-tenant"
        })


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker.get_required_tenant')
async def test_dmn_orphan_fallback_empty(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {},
        {"valid_suggestions": []},
    ]

    worker = SuggestCid10Worker(dmn_service=mock_dmn)
    result = await worker.execute({
        "clinical_notes": "Unknown symptoms",
        "extracted_diagnoses": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert result["suggested_cid10_codes"] == []
    assert result["primary_cid10"] == ""
    assert result["cid10_count"] == 0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker.get_required_tenant')
async def test_multiple_suggestions(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"suggestions": [
            {"code": "A01.0", "confidence": 0.9},
            {"code": "A01.1", "confidence": 0.85},
            {"code": "A01.2", "confidence": 0.8}
        ]},
        {"valid_suggestions": [
            {"code": "A01.0", "confidence": 0.9, "description": "Typhoid fever"},
            {"code": "A01.1", "confidence": 0.85, "description": "Paratyphoid fever A"},
            {"code": "A01.2", "confidence": 0.8, "description": "Paratyphoid fever B"}
        ]},
    ]

    worker = SuggestCid10Worker(dmn_service=mock_dmn)
    result = await worker.execute({
        "clinical_notes": "Febre tifoide e paratifoide",
        "extracted_diagnoses": [{"description": "Febre"}],
        "encounter_class": "internacao",
        "tenant_id": "test-tenant"
    })

    assert result["cid10_count"] == 3
    assert result["primary_cid10"] == "A01.0"
    assert len(result["suggested_cid10_codes"]) == 3


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker.get_required_tenant')
async def test_process_task_compat(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"suggestions": [{"code": "J00", "confidence": 0.95}]},
        {"valid_suggestions": [{"code": "J00", "confidence": 0.95, "description": "Acute nasopharyngitis"}]},
    ]

    worker = SuggestCid10Worker(dmn_service=mock_dmn)

    # process_task(variables=...) passes variables dict to execute()
    result = await worker.process_task(variables={
        "clinical_notes": "Common cold symptoms",
        "extracted_diagnoses": [{"description": "Resfriado"}],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert result.variables["primary_cid10"] == "J00"
    assert result.variables["cid10_count"] == 1


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker.get_required_tenant')
async def test_single_diagnosis(mock_get_tenant, tenant_ctx):
    """Test with only extracted_diagnoses (clinical_notes must still be non-empty for Pydantic)."""
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"suggestions": [{"code": "E11.9", "confidence": 0.88}]},
        {"valid_suggestions": [{"code": "E11.9", "confidence": 0.88, "description": "Type 2 diabetes mellitus without complications"}]},
    ]

    worker = SuggestCid10Worker(dmn_service=mock_dmn)
    result = await worker.execute({
        "clinical_notes": "Diabetes tipo 2",
        "extracted_diagnoses": [{"description": "Diabetes tipo 2"}],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert result["cid10_count"] == 1
    assert result["primary_cid10"] == "E11.9"
    assert result["suggested_cid10_codes"][0]["description"] == "Type 2 diabetes mellitus without complications"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker.get_required_tenant')
async def test_confidence_boosting_dmn_call(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"suggestions": [{"code": "I10", "confidence": 0.75}]},
        {"valid_suggestions": [{"code": "I10", "confidence": 0.75, "description": "Essential hypertension"}]},
    ]

    worker = SuggestCid10Worker(dmn_service=mock_dmn)
    await worker.execute({
        "clinical_notes": "Hipertensão arterial sistêmica",
        "extracted_diagnoses": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert mock_dmn.evaluate.call_count == 2
    first_call = mock_dmn.evaluate.call_args_list[0]
    assert "cid10_suggestion/confidence_boosting" in str(first_call)
