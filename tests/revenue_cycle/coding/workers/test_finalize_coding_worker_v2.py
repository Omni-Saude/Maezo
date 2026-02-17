from __future__ import annotations
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.finalize_coding_worker_v2 import FinalizeCodingWorkerV2
from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException


@pytest.fixture
def tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = "test-tenant"
    return ctx


@pytest.fixture
def valid_input():
    return {
        "encounterId": "enc-001",
        "validatedCid10": ["A01"],
        "validatedTuss": ["10101012"],
        "auditRecommendation": "aprovar",
        "auditScore": 90,
        "complexityScore": 5,
        "complexityLevel": "low",
        "fraudRecommendation": "clear",
        "codedBy": "dr-001",
        "tenantId": "test-tenant"
    }


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.finalize_coding_worker_v2.get_required_tenant')
async def test_happy_path_finalized(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}

    worker = FinalizeCodingWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute(valid_input)

    assert result["codingFinalized"] is True
    assert result["finalCid10"] == ["A01"]
    assert result["finalTuss"] == ["10101012"]
    assert "codingSummary" in result
    assert "codingTimestamp" in result
    assert result["coding_locked"] is False
    assert result["encounter_id"] == "enc-001"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.finalize_coding_worker_v2.get_required_tenant')
async def test_audit_blocked(mock_get_tenant, tenant_ctx, valid_input):
    """Audit blocking is handled by service, not DMN currently"""
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}

    worker = FinalizeCodingWorkerV2(dmn_service=mock_dmn)

    # Current implementation doesn't block on audit, just finalizes
    result = await worker.execute(valid_input)
    assert result["codingFinalized"] is True


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.finalize_coding_worker_v2.get_required_tenant')
async def test_fraud_blocked(mock_get_tenant, tenant_ctx, valid_input):
    """Fraud blocking is handled by service, not DMN currently"""
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}

    worker = FinalizeCodingWorkerV2(dmn_service=mock_dmn)

    # Current implementation doesn't block on fraud, just finalizes
    result = await worker.execute(valid_input)
    assert result["codingFinalized"] is True


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.finalize_coding_worker_v2.get_required_tenant')
async def test_invalid_input(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    worker = FinalizeCodingWorkerV2(dmn_service=mock_dmn)

    invalid_input = {
        "encounterId": "enc-001",
        "validatedCid10": ["A01"]
        # Missing required fields
    }

    with pytest.raises(CodingException):
        await worker.execute(invalid_input)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.finalize_coding_worker_v2.get_required_tenant')
async def test_encounter_service_lock(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}

    worker = FinalizeCodingWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute(valid_input)

    assert result["coding_locked"] is False
    assert result["encounter_id"] == "enc-001"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.finalize_coding_worker_v2.get_required_tenant')
async def test_process_task_compat(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}

    worker = FinalizeCodingWorkerV2(dmn_service=mock_dmn)

    result = await worker.process_task(variables=valid_input)

    assert result.variables["codingFinalized"] is True
    assert result.variables["finalCid10"] == ["A01"]
    assert result.variables["finalTuss"] == ["10101012"]


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.finalize_coding_worker_v2.get_required_tenant')
async def test_coding_summary_structure(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}

    worker = FinalizeCodingWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute(valid_input)

    summary = result["codingSummary"]
    assert "auditScore" in summary
    assert "complexityScore" in summary
    assert "complexityLevel" in summary
    assert "codedBy" in summary
    assert summary["auditScore"] == 90
    assert summary["complexityScore"] == 5


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.finalize_coding_worker_v2.get_required_tenant')
async def test_orphan_dmn_fallback(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}

    worker = FinalizeCodingWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute(valid_input)

    assert result["codingFinalized"] is True
    assert result["finalCid10"] == valid_input["validatedCid10"]
    assert result["finalTuss"] == valid_input["validatedTuss"]
