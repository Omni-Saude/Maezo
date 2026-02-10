"""Tests for OptimizeResourceUtilizationStub."""
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
    from healthcare_platform.platform_services.workers.optimize_resource_utilization import OptimizeResourceUtilizationStub
    return OptimizeResourceUtilizationStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_optimizes_resource_utilization(worker, tenant_austa):
    """Should successfully optimize resource utilization."""
    job = {
        "resource_types": ["operating_rooms", "staff"],
        "optimization_goal": "maximize_throughput"
    }
    result = await worker.process(job)
    assert result["status"] == "optimized"
    assert "recommendations" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when resource_types is missing."""
    job = {"optimization_goal": "maximize_throughput"}
    with pytest.raises(DomainException, match="resource_types"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"resource_types": ["operating_rooms"], "optimization_goal": "maximize_throughput"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
