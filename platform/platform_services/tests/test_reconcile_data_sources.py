"""Tests for ReconcileDataSourcesStub."""
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
    from platform.platform_services.workers.reconcile_data_sources import ReconcileDataSourcesStub
    return ReconcileDataSourcesStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_reconciles_data_sources(worker, tenant_austa):
    """Should successfully reconcile data sources."""
    job = {
        "source_systems": ["ehr", "billing", "lab"],
        "reconcile_type": "patient_records"
    }
    result = await worker.process(job)
    assert result["status"] == "reconciled"
    assert "discrepancies" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when source_systems is missing."""
    job = {"reconcile_type": "patient_records"}
    with pytest.raises(DomainException, match="source_systems"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"source_systems": ["ehr", "billing"], "reconcile_type": "patient_records"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
