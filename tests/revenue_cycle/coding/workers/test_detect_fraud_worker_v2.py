from __future__ import annotations
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.detect_fraud_worker_v2 import DetectFraudWorkerV2
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
        "encounterClass": "ambulatorio",
        "patientId": "pat-001",
        "providerId": "prov-001",
        "tenantId": "test-tenant"
    }


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.detect_fraud_worker_v2.get_required_tenant')
async def test_happy_path_clear(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {"alerts": [], "score": 0}

    worker = DetectFraudWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute(valid_input)

    assert result["fraudRiskScore"] >= 0
    assert isinstance(result["fraudAlerts"], list)
    assert result["fraudRecommendation"] in ["clear", "flag", "block"]
    assert isinstance(result["requiresManualReview"], bool)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.detect_fraud_worker_v2.get_required_tenant')
async def test_high_risk_fraud_detected(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    # Worker calls evaluate with keyword args: table_name="fraud_scoring/..."
    def dmn_side_effect(**kwargs):
        table_name = kwargs.get('table_name', '')
        if 'risk_thresholds' in table_name:
            return {"recommendation": "block"}
        return {"alerts": [{"message": "Suspicious pattern detected"}], "score": 15}

    mock_dmn.evaluate.side_effect = dmn_side_effect

    worker = DetectFraudWorkerV2(dmn_service=mock_dmn)

    # 6 checks × 15 = 90 > 80 → FRAUD_DETECTED
    with pytest.raises(BpmnErrorException) as exc_info:
        await worker.execute(valid_input)

    assert exc_info.value.error_code == "FRAUD_DETECTED"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.detect_fraud_worker_v2.get_required_tenant')
async def test_missing_fields_error(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    worker = DetectFraudWorkerV2(dmn_service=mock_dmn)

    invalid_input = {
        "encounterId": "enc-001",
        "validatedCid10": ["A01"]
        # Missing required fields
    }

    with pytest.raises(CodingException) as exc_info:
        await worker.execute(invalid_input)

    assert exc_info.value.bpmn_error_code == "CODING_ERROR"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.detect_fraud_worker_v2.get_required_tenant')
async def test_moderate_risk_flag(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    # alerts must be list[dict[str, str]], not list[str]
    def dmn_side_effect(**kwargs):
        table_name = kwargs.get('table_name', '')
        if 'risk_thresholds' in table_name:
            return {"recommendation": "flag"}
        return {"alerts": [{"message": "Moderate risk pattern"}], "score": 10}

    mock_dmn.evaluate.side_effect = dmn_side_effect

    worker = DetectFraudWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute(valid_input)

    assert result["fraudRecommendation"] == "flag"
    assert result["requiresManualReview"] is True
    assert result["fraudRiskScore"] > 0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.detect_fraud_worker_v2.get_required_tenant')
async def test_dmn_returns_alerts(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    def dmn_side_effect(**kwargs):
        table_name = kwargs.get('table_name', '')
        if 'upcoding' in table_name:
            return {"alerts": [{"message": "Upcoding detected"}], "score": 20}
        elif 'unbundling' in table_name:
            return {"alerts": [{"message": "Unbundling pattern"}], "score": 15}
        elif 'phantom' in table_name:
            return {"alerts": [{"message": "Phantom billing suspected"}], "score": 10}
        elif 'risk_thresholds' in table_name:
            return {"recommendation": "flag"}
        return {"alerts": [], "score": 0}

    mock_dmn.evaluate.side_effect = dmn_side_effect

    worker = DetectFraudWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute(valid_input)

    assert len(result["fraudAlerts"]) > 0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.detect_fraud_worker_v2.get_required_tenant')
async def test_process_task_compat(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    def dmn_side_effect(**kwargs):
        table_name = kwargs.get('table_name', '')
        if 'risk_thresholds' in table_name:
            return {"recommendation": "clear"}
        return {"alerts": [], "score": 0}

    mock_dmn.evaluate.side_effect = dmn_side_effect

    worker = DetectFraudWorkerV2(dmn_service=mock_dmn)

    result = await worker.process_task(variables=valid_input)

    assert result.variables["fraudRiskScore"] >= 0
    assert "fraudAlerts" in result.variables
    assert "fraudRecommendation" in result.variables


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.detect_fraud_worker_v2.get_required_tenant')
async def test_dmn_orphan_fallback(mock_get_tenant, tenant_ctx, valid_input):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {"alerts": [], "score": 0}

    worker = DetectFraudWorkerV2(dmn_service=mock_dmn)
    result = await worker.execute(valid_input)

    assert result["fraudRiskScore"] == 0
    assert result["fraudAlerts"] == []
    assert result["fraudRecommendation"] == "clear"
    assert result["requiresManualReview"] is False
