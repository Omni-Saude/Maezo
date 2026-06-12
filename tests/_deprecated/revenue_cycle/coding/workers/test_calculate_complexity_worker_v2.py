from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2 import CalculateComplexityWorkerV2
from healthcare_platform.shared.domain.exceptions import CodingException


@pytest.fixture
def tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = "test-tenant"
    return ctx


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.FederatedDMNService')
async def test_happy_path_low(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # total = 0.5 + 1.0 + 1.0 = 2.5 → round(2.5)=2 (banker's rounding) → score=2
    mock_dmn.evaluate.side_effect = [
        {'contribution': 0.5},
        {'age_factor': 1.0},
        {'weight': 1.0}
    ]

    worker = CalculateComplexityWorkerV2()

    result = await worker.execute({
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0'],
        'validatedTuss': ['10101012'],
        'encounterClass': 'outpatient',
        'patientAge': 35,
        'comorbidities': []
    })

    assert result['complexityScore'] == 2
    assert result['complexityLevel'] == 'LOW'
    assert 'complexityFactors' in result
    assert 'suggestedDRG' in result
    assert mock_dmn.evaluate.call_count == 3


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.FederatedDMNService')
async def test_moderate_complexity(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # total = 1.0 + 1.5 + 1.5 = 4.0 → score=4, 4<=6 → MODERATE
    mock_dmn.evaluate.side_effect = [
        {'contribution': 1.0},
        {'age_factor': 1.5},
        {'weight': 1.5}
    ]

    worker = CalculateComplexityWorkerV2()
    result = await worker.execute({
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0', 'B02.1'],
        'validatedTuss': ['10101012'],
        'encounterClass': 'inpatient',
        'patientAge': 65,
        'comorbidities': ['diabetes']
    })

    assert result['complexityScore'] == 4
    assert result['complexityLevel'] == 'MODERATE'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.FederatedDMNService')
async def test_high_complexity(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # total = 2.5 + 2.0 + 2.5 = 7.0 → score=7, 7>6 and 7<=9 → HIGH
    mock_dmn.evaluate.side_effect = [
        {'contribution': 2.5},
        {'age_factor': 2.0},
        {'weight': 2.5}
    ]

    worker = CalculateComplexityWorkerV2()

    result = await worker.execute({
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0', 'B02.1', 'C03.2'],
        'validatedTuss': ['10101012', '20101015'],
        'encounterClass': 'emergency',
        'patientAge': 78,
        'comorbidities': ['diabetes', 'hypertension', 'copd']
    })

    assert result['complexityScore'] == 7
    assert result['complexityLevel'] == 'HIGH'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.FederatedDMNService')
async def test_very_high_complexity(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # total = 3.5 + 3.0 + 3.5 = 10.0 → score=10, 10>9 → VERY_HIGH
    mock_dmn.evaluate.side_effect = [
        {'contribution': 3.5},
        {'age_factor': 3.0},
        {'weight': 3.5}
    ]

    worker = CalculateComplexityWorkerV2()

    result = await worker.execute({
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0', 'B02.1', 'C03.2', 'D04.3'],
        'validatedTuss': ['10101012', '20101015', '30101018'],
        'encounterClass': 'icu',
        'patientAge': 85,
        'comorbidities': ['diabetes', 'hypertension', 'copd', 'ckd', 'chf']
    })

    assert result['complexityScore'] == 10
    assert result['complexityLevel'] == 'VERY_HIGH'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.get_required_tenant')
async def test_missing_encounter_id_error(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    worker = CalculateComplexityWorkerV2()
    worker.dmn_service = mock_dmn

    with pytest.raises(CodingException):
        await worker.execute({
            'encounterId': '',
            'validatedCid10': ['A01.0'],
            'validatedTuss': ['10101012'],
            'encounterClass': 'outpatient',
            'patientAge': 35,
            'comorbidities': []
        })


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.get_required_tenant')
async def test_missing_encounter_class_error(mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MagicMock()

    worker = CalculateComplexityWorkerV2()
    worker.dmn_service = mock_dmn

    with pytest.raises(CodingException):
        await worker.execute({
            'encounterId': 'enc-123',
            'validatedCid10': ['A01.0'],
            'validatedTuss': ['10101012'],
            'encounterClass': '',
            'patientAge': 35,
            'comorbidities': []
        })


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.FederatedDMNService')
async def test_process_task_compat(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # total = 0.5 + 1.0 + 1.0 = 2.5 → round(2.5)=2
    mock_dmn.evaluate.side_effect = [
        {'contribution': 0.5},
        {'age_factor': 1.0},
        {'weight': 1.0}
    ]

    worker = CalculateComplexityWorkerV2()

    result = await worker.process_task(variables={
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0'],
        'validatedTuss': ['10101012'],
        'encounterClass': 'outpatient',
        'patientAge': 35,
        'comorbidities': []
    })

    assert result.variables['complexityScore'] == 2
    assert result.variables['complexityLevel'] == 'LOW'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker_v2.FederatedDMNService')
async def test_score_capped_at_15(MockDMNService, mock_get_tenant, tenant_ctx):
    mock_get_tenant.return_value = tenant_ctx
    mock_dmn = MockDMNService.return_value
    # total = 10+10+10 = 30 → min(30,15) = 15
    mock_dmn.evaluate.side_effect = [
        {'contribution': 10.0},
        {'age_factor': 10.0},
        {'weight': 10.0}
    ]

    worker = CalculateComplexityWorkerV2()

    result = await worker.execute({
        'encounterId': 'enc-123',
        'validatedCid10': ['A01.0'] * 10,
        'validatedTuss': ['10101012'] * 10,
        'encounterClass': 'icu',
        'patientAge': 90,
        'comorbidities': ['cond1', 'cond2', 'cond3', 'cond4', 'cond5']
    })

    assert result['complexityScore'] == 15
    assert result['complexityLevel'] == 'VERY_HIGH'
