from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker import SuggestTussWorker
from healthcare_platform.shared.domain.exceptions import CodingException


@pytest.fixture
def tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = "test-tenant"
    return ctx


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker.get_required_tenant')
async def test_happy_path(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"raw_suggestions": [{"code": "10101012", "description": "Consulta"}]},
        {"validated_tuss": [{"code": "10101012", "description": "Consulta em consultório"}]},
    ]

    worker = SuggestTussWorker(dmn_service=mock_dmn)
    result = await worker.execute({
        "extracted_procedures": [{"description": "Consulta médica"}],
        "suggested_cid10_codes": [{"code": "A01.0"}],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert result["tuss_count"] == 1
    assert len(result["suggested_tuss_codes"]) == 1
    assert result["suggested_tuss_codes"][0]["code"] == "10101012"
    assert mock_dmn.evaluate.call_count == 2


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker.get_required_tenant')
async def test_empty_input_error(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    worker = SuggestTussWorker(dmn_service=mock_dmn)

    with pytest.raises(CodingException) as exc_info:
        await worker.execute({
            "extracted_procedures": [],
            "suggested_cid10_codes": [],
            "encounter_class": "ambulatorio",
            "tenant_id": "test-tenant"
        })

    assert exc_info.value.bpmn_error_code == "CODING_ERROR"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker.get_required_tenant')
async def test_dmn_orphan_fallback(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {},
        {"validated_tuss": []},
    ]

    worker = SuggestTussWorker(dmn_service=mock_dmn)
    result = await worker.execute({
        "extracted_procedures": [{"description": "Unknown procedure"}],
        "suggested_cid10_codes": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert result["suggested_tuss_codes"] == []
    assert result["tuss_count"] == 0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker.get_required_tenant')
async def test_multiple_tuss_codes(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"raw_suggestions": [
            {"code": "10101012", "description": "Consulta"},
            {"code": "20101020", "description": "Exame físico"},
            {"code": "30101030", "description": "Avaliação"}
        ]},
        {"validated_tuss": [
            {"code": "10101012", "description": "Consulta em consultório"},
            {"code": "20101020", "description": "Exame físico geral"},
            {"code": "30101030", "description": "Avaliação clínica"}
        ]},
    ]

    worker = SuggestTussWorker(dmn_service=mock_dmn)
    result = await worker.execute({
        "extracted_procedures": [
            {"description": "Consulta médica"},
            {"description": "Exame físico"},
            {"description": "Avaliação"}
        ],
        "suggested_cid10_codes": [{"code": "A01.0"}, {"code": "A01.1"}],
        "encounter_class": "internacao",
        "tenant_id": "test-tenant"
    })

    assert result["tuss_count"] == 3
    assert len(result["suggested_tuss_codes"]) == 3
    assert result["suggested_tuss_codes"][0]["code"] == "10101012"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker.get_required_tenant')
async def test_process_task_compat(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"raw_suggestions": [{"code": "40101039", "description": "Radiografia"}]},
        {"validated_tuss": [{"code": "40101039", "description": "Radiografia de tórax"}]},
    ]

    worker = SuggestTussWorker(dmn_service=mock_dmn)

    result = await worker.process_task(variables={
        "extracted_procedures": [{"description": "Radiografia"}],
        "suggested_cid10_codes": [{"code": "J18.9"}],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert result.variables["tuss_count"] == 1
    assert result.variables["suggested_tuss_codes"][0]["code"] == "40101039"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker.get_required_tenant')
async def test_cid10_correlation_dmn_call(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"raw_suggestions": [{"code": "50101040", "description": "Procedimento cirúrgico"}]},
        {"validated_tuss": [{"code": "50101040", "description": "Procedimento cirúrgico ambulatorial"}]},
    ]

    worker = SuggestTussWorker(dmn_service=mock_dmn)
    await worker.execute({
        "extracted_procedures": [{"description": "Cirurgia"}],
        "suggested_cid10_codes": [{"code": "K40.9"}],
        "encounter_class": "cirurgia",
        "tenant_id": "test-tenant"
    })

    assert mock_dmn.evaluate.call_count == 2
    first_call = mock_dmn.evaluate.call_args_list[0]
    assert "tuss_suggestion/cid10_correlation" in str(first_call)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker.get_required_tenant')
async def test_procedures_without_cid10(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"raw_suggestions": [{"code": "60101050", "description": "Hemograma"}]},
        {"validated_tuss": [{"code": "60101050", "description": "Hemograma completo"}]},
    ]

    worker = SuggestTussWorker(dmn_service=mock_dmn)
    result = await worker.execute({
        "extracted_procedures": [{"description": "Hemograma completo"}],
        "suggested_cid10_codes": [],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert result["tuss_count"] == 1
    assert result["suggested_tuss_codes"][0]["code"] == "60101050"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker.get_required_tenant')
async def test_format_validation_dmn_call(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"raw_suggestions": [
            {"code": "10101012", "description": "Consulta"},
            {"code": "INVALID", "description": "Invalid"}
        ]},
        {"validated_tuss": [
            {"code": "10101012", "description": "Consulta em consultório"}
        ]},
    ]

    worker = SuggestTussWorker(dmn_service=mock_dmn)
    result = await worker.execute({
        "extracted_procedures": [{"description": "Consulta"}],
        "suggested_cid10_codes": [{"code": "Z00.0"}],
        "encounter_class": "ambulatorio",
        "tenant_id": "test-tenant"
    })

    assert result["tuss_count"] == 1
    assert mock_dmn.evaluate.call_count == 2
    second_call = mock_dmn.evaluate.call_args_list[1]
    assert "tuss_suggestion/format_validation" in str(second_call)
