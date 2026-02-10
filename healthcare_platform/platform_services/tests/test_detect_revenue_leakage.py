"""Tests for DetectRevenueLeakageStub."""
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
    from healthcare_platform.platform_services.workers.detect_revenue_leakage import DetectRevenueLeakageStub
    return DetectRevenueLeakageStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_detects_revenue_leakage(worker, tenant_austa):
    """Should successfully detect revenue leakage."""
    job = {
        "analysis_period": "2024-Q1",
        "leakage_types": ["unbilled", "undercoded"]
    }
    result = await worker.process(job)
    assert result["status"] == "detected"
    assert "leakage_points" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when analysis_period is missing."""
    job = {"leakage_types": ["unbilled"]}
    with pytest.raises(DomainException, match="analysis_period"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"analysis_period": "2024-Q1", "leakage_types": ["unbilled"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
