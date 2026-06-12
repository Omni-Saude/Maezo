from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker import ApplyCodingRulesWorker
from healthcare_platform.shared.domain.exceptions import CodingException, BpmnErrorException


@pytest.fixture
def tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = "test-tenant"
    return ctx


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.FederatedDMNService')
async def test_happy_path_no_violations(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = ApplyCodingRulesWorker(dmn_service=mock_dmn)
    result = await worker.execute({
        'validatedCid10': ['A01.0', 'B02.1'],
        'validatedTuss': ['10101012', '20101015'],
        'encounterClass': 'inpatient',
        'encounterId': 'enc-123'
    })

    assert result['rulesPassed'] is True
    assert result['ruleViolations'] == []
    assert result['modifiersRequired'] == []
    assert mock_dmn.evaluate.call_count == 4


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.FederatedDMNService')
async def test_missing_cid10_error(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value

    worker = ApplyCodingRulesWorker(dmn_service=mock_dmn)

    with pytest.raises(CodingException) as exc_info:
        await worker.execute({
            'validatedCid10': [],
            'validatedTuss': ['10101012'],
            'encounterClass': 'inpatient',
            'encounterId': 'enc-123'
        })

    assert exc_info.value.bpmn_error_code == 'CODING_ERROR'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.FederatedDMNService')
async def test_missing_tuss_error(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value

    worker = ApplyCodingRulesWorker(dmn_service=mock_dmn)

    with pytest.raises(CodingException) as exc_info:
        await worker.execute({
            'validatedCid10': ['A01.0'],
            'validatedTuss': [],
            'encounterClass': 'inpatient',
            'encounterId': 'enc-123'
        })

    assert exc_info.value.bpmn_error_code == 'CODING_ERROR'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.FederatedDMNService')
async def test_dmn_returns_block(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.side_effect = [
        {'resultado': 'BLOQUEAR', 'motivo': 'Quantity exceeded', 'severidade': 'ERROR'},
        {},
        {},
        {}
    ]

    worker = ApplyCodingRulesWorker(dmn_service=mock_dmn)

    with pytest.raises(BpmnErrorException) as exc_info:
        await worker.execute({
            'validatedCid10': ['A01.0'],
            'validatedTuss': ['10101012'],
            'encounterClass': 'inpatient',
            'encounterId': 'enc-123'
        })

    assert exc_info.value.error_code == 'CODING_RULE_VIOLATION'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.FederatedDMNService')
async def test_dmn_returns_review_warning(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.side_effect = [
        {'resultado': 'REVISAR', 'acao': 'Check bundling', 'severidade': 'WARNING'},
        {},
        {},
        {}
    ]

    worker = ApplyCodingRulesWorker(dmn_service=mock_dmn)
    result = await worker.execute({
        'validatedCid10': ['A01.0'],
        'validatedTuss': ['10101012'],
        'encounterClass': 'inpatient',
        'encounterId': 'enc-123'
    })

    assert result['rulesPassed'] is True
    assert len(result['ruleViolations']) == 1
    assert result['ruleViolations'][0]['severity'] == 'WARNING'
    assert result['ruleViolations'][0]['message'] == 'Check bundling'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.FederatedDMNService')
async def test_modifier_extraction(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.side_effect = [
        {},
        {},
        {},
        {'acao': 'Aplicar modificador 22'}
    ]

    worker = ApplyCodingRulesWorker(dmn_service=mock_dmn)
    result = await worker.execute({
        'validatedCid10': ['A01.0'],
        'validatedTuss': ['10101012', '20101015'],
        'encounterClass': 'inpatient',
        'encounterId': 'enc-123'
    })

    assert result['rulesPassed'] is True
    assert len(result['modifiersRequired']) == 1
    assert 'Aplicar modificador 22' in result['modifiersRequired']


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.apply_coding_rules_worker.FederatedDMNService')
async def test_multiple_violations_mixed_severity(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.side_effect = [
        {'resultado': 'REVISAR', 'motivo': 'Warning 1', 'severidade': 'WARNING'},
        {'resultado': 'BLOQUEAR', 'motivo': 'Error 1', 'severidade': 'ERROR'},
        {},
        {}
    ]

    worker = ApplyCodingRulesWorker(dmn_service=mock_dmn)

    with pytest.raises(BpmnErrorException) as exc_info:
        await worker.execute({
            'validatedCid10': ['A01.0'],
            'validatedTuss': ['10101012'],
            'encounterClass': 'inpatient',
            'encounterId': 'enc-123'
        })

    assert exc_info.value.error_code == 'CODING_RULE_VIOLATION'
