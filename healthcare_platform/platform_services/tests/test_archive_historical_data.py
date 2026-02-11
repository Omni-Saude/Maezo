"""Tests for ArchiveHistoricalDataStub."""
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
    from healthcare_platform.platform_services.workers.archive_historical_data import ArchiveHistoricalDataStub
    return ArchiveHistoricalDataStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_archives_historical_data(worker, tenant_hospital_a):
    """Should successfully archive historical data."""
    job = {
        "data_types": ["claims", "encounters"],
        "retention_date": "2020-01-01"
    }
    result = await worker.process(job)
    assert result["status"] == "archived"
    assert "records_archived" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_hospital_a):
    """Should raise DomainException when data_types is missing."""
    job = {"retention_date": "2020-01-01"}
    with pytest.raises(DomainException, match="data_types"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"data_types": ["claims"], "retention_date": "2020-01-01"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
