from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker import AuditCodingWorker
from healthcare_platform.shared.domain.exceptions import CodingException, BpmnErrorException


@pytest.fixture
def tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = "test-tenant"
    return ctx


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.FederatedDMNService')
async def test_happy_path_approve(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = AuditCodingWorker()
    result = await worker.execute({
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0', 'B02.1'],
        'validatedTuss': ['10101012', '20101015'],
        'rulesApplied': [],
        'codedBy': 'coder-1'
    })

    assert result['auditScore'] == 100
    assert result['auditFindings'] == []
    assert result['auditRecommendation'] == 'approve'
    assert result['requiresRevision'] is False
    assert mock_dmn.evaluate.call_count == 4


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.FederatedDMNService')
async def test_low_score_reject_raises(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # 4 checks: code_specificity(deduct=T), documentation(deduct=T), drg(deduct=F), unbundling(deduct=T)
    # Need 3 deducting BLOQUEAR to reach score<60: 100-15-15-15=55
    mock_dmn.evaluate.side_effect = [
        {'resultado': 'BLOQUEAR', 'acao': 'Code not specific enough'},      # deduct=True, -15
        {'resultado': 'BLOQUEAR', 'acao': 'Missing documentation'},          # deduct=True, -15
        {'resultado': 'BLOQUEAR', 'acao': 'DRG not optimized'},              # deduct=False
        {'resultado': 'BLOQUEAR', 'acao': 'Unbundling detected'},            # deduct=True, -15
    ]

    worker = AuditCodingWorker()

    with pytest.raises(BpmnErrorException) as exc_info:
        await worker.execute({
            'encounterId': 'enc-123',
            'validatedCid10': ['A01'],
            'validatedTuss': ['10101012'],
            'rulesApplied': [],
            'codedBy': 'coder-1'
        })

    assert exc_info.value.error_code == 'AUDIT_FAILED'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.FederatedDMNService')
async def test_revise_recommendation(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # 2 REVISAR on deducting checks: 100-10-10=80. Score 80 >= 80 → approve
    mock_dmn.evaluate.side_effect = [
        {'resultado': 'REVISAR', 'acao': 'Code could be more specific'},
        {'resultado': 'REVISAR', 'acao': 'Documentation incomplete'},
        {},
        {}
    ]

    worker = AuditCodingWorker()
    result = await worker.execute({
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0'],
        'validatedTuss': ['10101012'],
        'rulesApplied': [],
        'codedBy': 'coder-1'
    })

    assert result['auditScore'] == 80
    assert len(result['auditFindings']) == 2
    assert result['auditRecommendation'] == 'approve'
    assert result['requiresRevision'] is False


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.FederatedDMNService')
async def test_empty_cid10_error(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value

    worker = AuditCodingWorker()

    with pytest.raises(CodingException):
        await worker.execute({
            'encounterId': 'enc-123',
            'validatedCid10': [],
            'validatedTuss': ['10101012'],
            'rulesApplied': [],
            'codedBy': 'coder-1'
        })


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.FederatedDMNService')
async def test_empty_tuss_error(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value

    worker = AuditCodingWorker()

    with pytest.raises(CodingException):
        await worker.execute({
            'encounterId': 'enc-123',
            'validatedCid10': ['A01.0'],
            'validatedTuss': [],
            'rulesApplied': [],
            'codedBy': 'coder-1'
        })


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.FederatedDMNService')
async def test_rule_violations_deduct(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # 2 REVISAR on deducting checks: 100-10-10=80
    mock_dmn.evaluate.side_effect = [
        {'resultado': 'REVISAR', 'acao': 'Issue 1'},
        {'resultado': 'REVISAR', 'acao': 'Issue 2'},
        {},
        {}
    ]

    worker = AuditCodingWorker()
    result = await worker.execute({
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0'],
        'validatedTuss': ['10101012'],
        'rulesApplied': [],
        'codedBy': 'coder-1'
    })

    assert result['auditScore'] == 80
    assert len(result['auditFindings']) == 2
    assert result['auditRecommendation'] == 'approve'
    assert result['requiresRevision'] is False


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.FederatedDMNService')
async def test_process_task_compat(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = AuditCodingWorker()

    result = await worker.process_task(variables={
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0'],
        'validatedTuss': ['10101012'],
        'rulesApplied': [],
        'codedBy': 'coder-1'
    })

    assert result.variables['auditScore'] == 100
    assert result.variables['auditRecommendation'] == 'approve'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.audit_coding_worker.FederatedDMNService')
async def test_score_floor_zero(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # All 4 checks BLOQUEAR: 3 deducting × -15 = score 55 < 60
    mock_dmn.evaluate.side_effect = [
        {'resultado': 'BLOQUEAR', 'acao': 'Major issue 1'},      # deduct=True, -15
        {'resultado': 'BLOQUEAR', 'acao': 'Major issue 2'},      # deduct=True, -15
        {'resultado': 'BLOQUEAR', 'acao': 'Major issue 3'},      # deduct=False
        {'resultado': 'BLOQUEAR', 'acao': 'Major issue 4'},      # deduct=True, -15
    ]

    worker = AuditCodingWorker()

    with pytest.raises(BpmnErrorException) as exc_info:
        await worker.execute({
            'encounterId': 'enc-123',
            'validatedCid10': ['A01'],
            'validatedTuss': ['10101012'],
            'rulesApplied': [],
            'codedBy': 'coder-1'
        })

    assert exc_info.value.error_code == 'AUDIT_FAILED'
