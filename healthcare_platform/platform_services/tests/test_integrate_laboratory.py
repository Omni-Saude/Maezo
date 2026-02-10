"""Tests for IntegrateLaboratoryStub."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

@pytest.fixture
def tenant_austa():
    ctx = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()

@pytest.fixture
def fhir_client():
    return AsyncMock()

@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.platform_services.workers.integrate_laboratory import IntegrateLaboratoryStub
    return IntegrateLaboratoryStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_integrates_lab_results(worker, tenant_austa):
    """Should successfully integrate laboratory results."""
    job = {
        "lab_system_id": "lab-001",
        "result_ids": ["RES-123", "RES-124"]
    }
    result = await worker.process(job)
    assert result["status"] == "integrated"
    assert "results_imported" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when lab_system_id is missing."""
    job = {"result_ids": ["RES-123"]}
    with pytest.raises(DomainException, match="lab_system_id"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"lab_system_id": "lab-001", "result_ids": ["RES-123"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
