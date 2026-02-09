"""Tests for IntegrateImagingStub."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock
from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import DomainException
from platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

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
    from platform.platform_services.workers.integrate_imaging import IntegrateImagingStub
    return IntegrateImagingStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_integrates_imaging_studies(worker, tenant_austa):
    """Should successfully integrate imaging studies."""
    job = {
        "pacs_system_id": "pacs-001",
        "study_ids": ["STU-456", "STU-457"]
    }
    result = await worker.process(job)
    assert result["status"] == "integrated"
    assert "studies_imported" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when pacs_system_id is missing."""
    job = {"study_ids": ["STU-456"]}
    with pytest.raises(DomainException, match="pacs_system_id"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"pacs_system_id": "pacs-001", "study_ids": ["STU-456"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
