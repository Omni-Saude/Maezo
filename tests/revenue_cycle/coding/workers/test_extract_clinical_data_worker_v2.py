from __future__ import annotations
from typing import Any
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker import ExtractClinicalDataWorker
from healthcare_platform.shared.domain.exceptions import CodingException


@pytest.fixture
def tenant_ctx():
    ctx = MagicMock()
    ctx.tenant_id = "test-tenant"
    return ctx


@pytest.fixture
def mock_fhir_client():
    client = MagicMock()
    return client


@pytest.fixture
def expected_extraction_result():
    return {
        "encounter_id": "enc-001",
        "diagnoses": [
            {
                "code": "A01",
                "system": "ICD-10",
                "display": "Typhoid fever"
            }
        ],
        "procedures": [
            {
                "code": "10101012",
                "system": "TUSS",
                "display": "Consultation"
            }
        ],
        "patient_demographics": {
            "age": 45,
            "gender": "M"
        },
        "encounter_class": "ambulatorio"
    }


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.ClinicalDataExtractionService')
async def test_happy_path(MockService, mock_get_tenant, tenant_ctx, mock_fhir_client, expected_extraction_result):
    mock_get_tenant.return_value = tenant_ctx
    mock_svc = MockService.return_value
    mock_svc.extract_with_dmn = AsyncMock(return_value=expected_extraction_result)

    worker = ExtractClinicalDataWorker(fhir_client=mock_fhir_client)
    worker.service = mock_svc

    result = await worker.execute({"encounter_id": "enc-001"})

    assert result["encounter_id"] == "enc-001"
    assert "diagnoses" in result
    assert "procedures" in result
    mock_svc.extract_with_dmn.assert_called_once()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.ClinicalDataExtractionService')
async def test_missing_encounter_id_error(MockService, mock_get_tenant, tenant_ctx, mock_fhir_client):
    mock_get_tenant.return_value = tenant_ctx
    mock_svc = MockService.return_value

    worker = ExtractClinicalDataWorker(fhir_client=mock_fhir_client)
    worker.service = mock_svc

    with pytest.raises(CodingException) as exc_info:
        await worker.execute({})

    assert "encounter_id" in str(exc_info.value).lower()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.ClinicalDataExtractionService')
async def test_empty_encounter_id_error(MockService, mock_get_tenant, tenant_ctx, mock_fhir_client):
    mock_get_tenant.return_value = tenant_ctx
    mock_svc = MockService.return_value

    worker = ExtractClinicalDataWorker(fhir_client=mock_fhir_client)
    worker.service = mock_svc

    with pytest.raises(CodingException):
        await worker.execute({"encounter_id": ""})


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.ClinicalDataExtractionService')
async def test_no_fhir_client_error(MockService):
    with pytest.raises(ValueError) as exc_info:
        ExtractClinicalDataWorker(fhir_client=None)

    assert "fhir_client" in str(exc_info.value).lower()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.ClinicalDataExtractionService')
async def test_service_extraction(MockService, mock_get_tenant, tenant_ctx, mock_fhir_client, expected_extraction_result):
    mock_get_tenant.return_value = tenant_ctx
    mock_svc = MockService.return_value
    mock_svc.extract_with_dmn = AsyncMock(return_value=expected_extraction_result)

    worker = ExtractClinicalDataWorker(fhir_client=mock_fhir_client)
    worker.service = mock_svc

    result = await worker.execute({"encounter_id": "enc-001"})

    mock_svc.extract_with_dmn.assert_called_once()
    assert result == expected_extraction_result


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.ClinicalDataExtractionService')
async def test_process_task_compat(MockService, mock_get_tenant, tenant_ctx, mock_fhir_client, expected_extraction_result):
    mock_get_tenant.return_value = tenant_ctx
    mock_svc = MockService.return_value

    # process_task delegates to service.process_task_compat(execute_fn, variables)
    # We mock it to call execute_fn and wrap result
    async def process_task_compat_impl(execute_fn, variables):
        from dataclasses import dataclass, field
        from typing import Dict, Optional

        @dataclass
        class _Result:
            success: bool
            variables: Dict[str, Any] = field(default_factory=dict)
            error_code: Optional[str] = None
            error_message: Optional[str] = None

        result = await execute_fn(variables)
        return _Result(success=True, variables=result)

    mock_svc.process_task_compat = AsyncMock(side_effect=process_task_compat_impl)
    mock_svc.extract_with_dmn = AsyncMock(return_value=expected_extraction_result)

    worker = ExtractClinicalDataWorker(fhir_client=mock_fhir_client)
    worker.service = mock_svc

    result = await worker.process_task(variables={"encounter_id": "enc-001"})

    assert result.variables["encounter_id"] == "enc-001"
    assert "diagnoses" in result.variables


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.ClinicalDataExtractionService')
async def test_extraction_with_empty_results(MockService, mock_get_tenant, tenant_ctx, mock_fhir_client):
    mock_get_tenant.return_value = tenant_ctx
    mock_svc = MockService.return_value

    empty_result = {
        "encounter_id": "enc-001",
        "diagnoses": [],
        "procedures": [],
        "patient_demographics": {},
        "encounter_class": None
    }
    mock_svc.extract_with_dmn = AsyncMock(return_value=empty_result)

    worker = ExtractClinicalDataWorker(fhir_client=mock_fhir_client)
    worker.service = mock_svc

    result = await worker.execute({"encounter_id": "enc-001"})

    assert result["encounter_id"] == "enc-001"
    assert result["diagnoses"] == []
    assert result["procedures"] == []


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.coding.workers.extract_clinical_data_worker.ClinicalDataExtractionService')
async def test_extraction_with_multiple_items(MockService, mock_get_tenant, tenant_ctx, mock_fhir_client):
    mock_get_tenant.return_value = tenant_ctx
    mock_svc = MockService.return_value

    multi_item_result = {
        "encounter_id": "enc-001",
        "diagnoses": [
            {"code": "A01", "system": "ICD-10", "display": "Typhoid fever"},
            {"code": "B05", "system": "ICD-10", "display": "Measles"}
        ],
        "procedures": [
            {"code": "10101012", "system": "TUSS", "display": "Consultation"},
            {"code": "20101020", "system": "TUSS", "display": "Lab test"}
        ],
        "patient_demographics": {"age": 45, "gender": "M"},
        "encounter_class": "ambulatorio"
    }
    mock_svc.extract_with_dmn = AsyncMock(return_value=multi_item_result)

    worker = ExtractClinicalDataWorker(fhir_client=mock_fhir_client)
    worker.service = mock_svc

    result = await worker.execute({"encounter_id": "enc-001"})

    assert len(result["diagnoses"]) == 2
    assert len(result["procedures"]) == 2
