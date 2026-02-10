"""Tests for GenerateRegulatoryReportsStub."""
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
    from healthcare_platform.platform_services.workers.generate_regulatory_reports import GenerateRegulatoryReportsStub
    return GenerateRegulatoryReportsStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_generates_regulatory_reports(worker, tenant_austa):
    """Should successfully generate regulatory reports."""
    job = {
        "report_types": ["ans", "cnes"],
        "period": "2024-Q1"
    }
    result = await worker.process(job)
    assert result["status"] == "generated"
    assert "reports" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when report_types is missing."""
    job = {"period": "2024-Q1"}
    with pytest.raises(DomainException, match="report_types"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"report_types": ["ans"], "period": "2024-Q1"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
