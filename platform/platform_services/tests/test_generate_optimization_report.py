"""Tests for GenerateOptimizationReportStub."""
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
    from platform.platform_services.workers.generate_optimization_report import GenerateOptimizationReportStub
    return GenerateOptimizationReportStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_generates_optimization_report(worker, tenant_austa):
    """Should successfully generate optimization report."""
    job = {
        "report_period": "2024-Q1",
        "include_sections": ["opportunities", "leakage", "forecast"]
    }
    result = await worker.process(job)
    assert result["status"] == "generated"
    assert "report_url" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when report_period is missing."""
    job = {"include_sections": ["opportunities"]}
    with pytest.raises(DomainException, match="report_period"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"report_period": "2024-Q1", "include_sections": ["opportunities"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
