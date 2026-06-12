from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker import CheckCodeCompatibilityWorker
from healthcare_platform.shared.domain.exceptions import CodingException, IncompatibleCodes


@pytest.fixture
def tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = "test-tenant"
    return ctx


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.FederatedDMNService')
async def test_happy_path_compatible(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CheckCodeCompatibilityWorker()
    result = await worker.execute({
        'validatedCid10': ['A01.0', 'B02.1'],
        'validatedTuss': ['10101012', '20101015'],
        'encounterId': 'enc-123'
    })

    assert result['compatible'] is True
    assert result['incompatibilities'] == []
    assert result['warnings'] == []
    assert mock_dmn.evaluate.call_count == 2


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.FederatedDMNService')
async def test_empty_cid10_error(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value

    worker = CheckCodeCompatibilityWorker()

    with pytest.raises(CodingException):
        await worker.execute({
            'validatedCid10': [],
            'validatedTuss': ['10101012'],
            'encounterId': 'enc-123'
        })


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.FederatedDMNService')
async def test_empty_tuss_error(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value

    worker = CheckCodeCompatibilityWorker()

    with pytest.raises(CodingException):
        await worker.execute({
            'validatedCid10': ['A01.0'],
            'validatedTuss': [],
            'encounterId': 'enc-123'
        })


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.FederatedDMNService')
async def test_dmn_block_incompatible(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.side_effect = [
        {
            'resultado': 'BLOQUEAR',
            'acao': 'Codes A01.0 and B02.1 are incompatible',
            'cid10': 'A01.0',
            'tuss': 'B02.1'
        },
        {}
    ]

    worker = CheckCodeCompatibilityWorker()

    with pytest.raises(IncompatibleCodes):
        await worker.execute({
            'validatedCid10': ['A01.0', 'B02.1'],
            'validatedTuss': ['10101012'],
            'encounterId': 'enc-123'
        })


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.FederatedDMNService')
async def test_dmn_review_warning(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.side_effect = [
        {},
        {
            'resultado': 'REVISAR',
            'acao': 'Consider reviewing codes 10101012 and 20101015',
            'pair': '10101012+20101015'
        }
    ]

    worker = CheckCodeCompatibilityWorker()
    result = await worker.execute({
        'validatedCid10': ['A01.0'],
        'validatedTuss': ['10101012', '20101015'],
        'encounterId': 'enc-123'
    })

    assert result['compatible'] is True
    assert len(result['warnings']) == 1
    assert result['warnings'][0] == 'Consider reviewing codes 10101012 and 20101015'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.FederatedDMNService')
async def test_process_task_compat(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {}

    worker = CheckCodeCompatibilityWorker()

    result = await worker.process_task(variables={
        'validatedCid10': ['A01.0'],
        'validatedTuss': ['10101012'],
        'encounterId': 'enc-123'
    })

    assert result.variables['compatible'] is True
    assert result.variables['incompatibilities'] == []


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.FederatedDMNService')
async def test_multiple_incompatibilities(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.side_effect = [
        {
            'resultado': 'BLOQUEAR',
            'acao': 'First incompatibility',
            'cid10': 'A01.0',
            'tuss': '10101012'
        },
        {}
    ]

    worker = CheckCodeCompatibilityWorker()

    with pytest.raises(IncompatibleCodes):
        await worker.execute({
            'validatedCid10': ['A01.0', 'B02.1', 'C03.2'],
            'validatedTuss': ['10101012'],
            'encounterId': 'enc-123'
        })


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.check_code_compatibility_worker.FederatedDMNService')
async def test_mixed_results_warnings_only(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.side_effect = [
        {},
        {'resultado': 'REVISAR', 'acao': 'Warning message'},
    ]

    worker = CheckCodeCompatibilityWorker()
    result = await worker.execute({
        'validatedCid10': ['A01.0', 'B02.1'],
        'validatedTuss': ['10101012', '20101015'],
        'encounterId': 'enc-123'
    })

    assert result['compatible'] is True
    assert len(result['warnings']) == 1
    assert result['warnings'][0] == 'Warning message'
    assert result['incompatibilities'] == []
