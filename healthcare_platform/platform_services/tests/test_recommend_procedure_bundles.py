"""Tests for RecommendProcedureBundlesStub."""
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
    from healthcare_platform.platform_services.workers.recommend_procedure_bundles import RecommendProcedureBundlesStub
    return RecommendProcedureBundlesStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_recommends_procedure_bundles(worker, tenant_austa):
    """Should successfully recommend procedure bundles."""
    job = {
        "specialty": "cardiology",
        "target_patient_segment": "elective"
    }
    result = await worker.process(job)
    assert result["status"] == "recommended"
    assert "bundles" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when specialty is missing."""
    job = {"target_patient_segment": "elective"}
    with pytest.raises(DomainException, match="specialty"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"specialty": "cardiology", "target_patient_segment": "elective"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
