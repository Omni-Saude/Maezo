from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2 import ValidateCodesWorkerV2
from healthcare_platform.shared.domain.exceptions import CodingException, BpmnErrorException


@pytest.fixture
def tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = "test-tenant"
    return ctx


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2.get_required_tenant')
async def test_happy_path_all_valid(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"validated_cid10": [{"code": "A01.0"}], "errors": []},
        {"errors": []},
        {"format_valid_tuss": [{"code": "10101012"}], "errors": []},
        {"validated_tuss": [{"code": "10101012"}], "errors": []},
        {"errors": []},
    ]

    worker = ValidateCodesWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute({
        "suggested_cid10_codes": [{"code": "A01.0"}],
        "suggested_tuss_codes": [{"code": "10101012"}],
        "encounter_id": "enc-001",
        "tenant_id": "test-tenant"
    })

    assert result["all_valid"] is True
    assert len(result["validated_cid10"]) == 1
    assert len(result["validated_tuss"]) == 1
    assert len(result["validation_errors"]) == 0
    assert mock_dmn.evaluate.call_count == 5


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2.get_required_tenant')
async def test_empty_codes_error(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    worker = ValidateCodesWorkerV2(dmn_service=mock_dmn)

    with pytest.raises(CodingException) as exc_info:
        await worker.execute({
            "suggested_cid10_codes": [],
            "suggested_tuss_codes": [],
            "encounter_id": "enc-001",
            "tenant_id": "test-tenant"
        })

    assert exc_info.value.bpmn_error_code == "CODING_ERROR"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2.get_required_tenant')
async def test_cid10_validation_failure(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"validated_cid10": [], "errors": [{"code": "INVALID", "message": "Invalid format"}]},
        {"errors": []},
        {"format_valid_tuss": [{"code": "10101012"}], "errors": []},
        {"validated_tuss": [{"code": "10101012"}], "errors": []},
        {"errors": []},
    ]

    worker = ValidateCodesWorkerV2(dmn_service=mock_dmn)

    with pytest.raises(BpmnErrorException) as exc_info:
        await worker.execute({
            "suggested_cid10_codes": [{"code": "INVALID"}],
            "suggested_tuss_codes": [{"code": "10101012"}],
            "encounter_id": "enc-001",
            "tenant_id": "test-tenant"
        })

    assert exc_info.value.error_code == "INVALID_CID10_CODE"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2.get_required_tenant')
async def test_tuss_validation_failure(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"validated_cid10": [{"code": "A01.0"}], "errors": []},
        {"errors": []},
        {"format_valid_tuss": [], "errors": [{"code": "INVALID", "message": "Invalid TUSS format"}]},
        {"validated_tuss": [], "errors": []},
        {"errors": []},
    ]

    worker = ValidateCodesWorkerV2(dmn_service=mock_dmn)

    with pytest.raises(BpmnErrorException) as exc_info:
        await worker.execute({
            "suggested_cid10_codes": [{"code": "A01.0"}],
            "suggested_tuss_codes": [{"code": "INVALID"}],
            "encounter_id": "enc-001",
            "tenant_id": "test-tenant"
        })

    assert exc_info.value.error_code == "INVALID_TUSS_CODE"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2.get_required_tenant')
async def test_partial_validation(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"validated_cid10": [{"code": "A01.0"}, {"code": "A01.1"}], "errors": [{"code": "A01.X", "message": "Code A01.X invalid"}]},
        {"errors": []},
        {"format_valid_tuss": [{"code": "10101012"}], "errors": [{"code": "99999999", "message": "Code 99999999 invalid"}]},
        {"validated_tuss": [{"code": "10101012"}], "errors": []},
        {"errors": [{"type": "warning", "message": "Incompatibility warning"}]},
    ]

    worker = ValidateCodesWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute({
        "suggested_cid10_codes": [{"code": "A01.0"}, {"code": "A01.1"}, {"code": "A01.X"}],
        "suggested_tuss_codes": [{"code": "10101012"}, {"code": "99999999"}],
        "encounter_id": "enc-001",
        "tenant_id": "test-tenant"
    })

    assert result["all_valid"] is False
    assert len(result["validated_cid10"]) >= 1
    assert len(result["validated_tuss"]) >= 1
    assert len(result["validation_errors"]) >= 1


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2.get_required_tenant')
async def test_process_task_compat(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"validated_cid10": [{"code": "J00"}], "errors": []},
        {"errors": []},
        {"format_valid_tuss": [{"code": "10101012"}], "errors": []},
        {"validated_tuss": [{"code": "10101012"}], "errors": []},
        {"errors": []},
    ]

    worker = ValidateCodesWorkerV2(dmn_service=mock_dmn)

    result = await worker.process_task(variables={
        "suggested_cid10_codes": [{"code": "J00"}],
        "suggested_tuss_codes": [{"code": "10101012"}],
        "encounter_id": "enc-002",
        "tenant_id": "test-tenant"
    })

    assert result.variables["all_valid"] is True
    assert result.variables["validated_cid10"] == [{"code": "J00"}]
    assert result.variables["validated_tuss"] == [{"code": "10101012"}]


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2.get_required_tenant')
async def test_dmn_sequential_calls(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"validated_cid10": [{"code": "E11.9"}], "errors": []},
        {"errors": []},
        {"format_valid_tuss": [{"code": "20101020"}], "errors": []},
        {"validated_tuss": [{"code": "20101020"}], "errors": []},
        {"errors": []},
    ]

    worker = ValidateCodesWorkerV2(dmn_service=mock_dmn)
    await worker.execute({
        "suggested_cid10_codes": [{"code": "E11.9"}],
        "suggested_tuss_codes": [{"code": "20101020"}],
        "encounter_id": "enc-003",
        "tenant_id": "test-tenant"
    })

    assert mock_dmn.evaluate.call_count == 5
    call_args = [str(call) for call in mock_dmn.evaluate.call_args_list]
    assert any("cid10_format" in arg for arg in call_args)
    assert any("cid10_incompatibility" in arg for arg in call_args)
    assert any("tuss_format" in arg for arg in call_args)
    assert any("tuss_coverage" in arg for arg in call_args)
    assert any("tuss_cid10_requirements" in arg for arg in call_args)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.validate_codes_worker_v2.get_required_tenant')
async def test_incompatibility_errors(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.side_effect = [
        {"validated_cid10": [{"code": "A01.0"}, {"code": "B01.0"}], "errors": []},
        {"errors": [{"type": "incompatibility", "message": "Codes A01.0 and B01.0 are incompatible"}]},
        {"format_valid_tuss": [{"code": "10101012"}], "errors": []},
        {"validated_tuss": [{"code": "10101012"}], "errors": []},
        {"errors": []},
    ]

    worker = ValidateCodesWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute({
        "suggested_cid10_codes": [{"code": "A01.0"}, {"code": "B01.0"}],
        "suggested_tuss_codes": [{"code": "10101012"}],
        "encounter_id": "enc-004",
        "tenant_id": "test-tenant"
    })

    assert result["all_valid"] is False
    assert len(result["validation_errors"]) >= 1
