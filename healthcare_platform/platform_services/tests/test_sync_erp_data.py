"""Tests for SyncErpDataStub."""
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
    from healthcare_platform.platform_services.workers.sync_erp_data import SyncErpDataStub
    return SyncErpDataStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_syncs_erp_data(worker, tenant_austa):
    """Should successfully sync ERP data."""
    job = {
        "system_id": "erp-001",
        "data_types": ["financial", "inventory"]
    }
    result = await worker.process(job)
    assert result["status"] == "synced"
    assert "records_synced" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when system_id is missing."""
    job = {"data_types": ["financial"]}
    with pytest.raises(DomainException, match="system_id"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"system_id": "erp-001", "data_types": ["financial"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
