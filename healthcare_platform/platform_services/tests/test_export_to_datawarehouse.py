"""Tests for ExportToDatawarehouseStub."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

@pytest.fixture
def tenant_hospital_a():
    ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()

@pytest.fixture
def fhir_client():
    return AsyncMock()

@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.platform_services.workers.export_to_datawarehouse import ExportToDatawarehouseStub
    return ExportToDatawarehouseStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_exports_to_datawarehouse(worker, tenant_hospital_a):
    """Should successfully export to datawarehouse."""
    job = {
        "export_type": "clinical_data",
        "target_warehouse": "redshift-001"
    }
    result = await worker.process(job)
    assert result["status"] == "exported"
    assert "records_exported" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_hospital_a):
    """Should raise DomainException when export_type is missing."""
    job = {"target_warehouse": "redshift-001"}
    with pytest.raises(DomainException, match="export_type"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"export_type": "clinical_data", "target_warehouse": "redshift-001"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
