"""Tests for GenerateExecutiveDashboardStub."""
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
    from healthcare_platform.platform_services.workers.generate_executive_dashboard import GenerateExecutiveDashboardStub
    return GenerateExecutiveDashboardStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_generates_executive_dashboard(worker, tenant_hospital_a):
    """Should successfully generate executive dashboard."""
    job = {
        "dashboard_type": "executive",
        "period": "2024-Q1"
    }
    result = await worker.process(job)
    assert result["status"] == "generated"
    assert "dashboard_url" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_hospital_a):
    """Should raise DomainException when dashboard_type is missing."""
    job = {"period": "2024-Q1"}
    with pytest.raises(DomainException, match="dashboard_type"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"dashboard_type": "executive", "period": "2024-Q1"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
