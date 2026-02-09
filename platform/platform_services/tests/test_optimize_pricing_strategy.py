"""Tests for OptimizePricingStrategyStub."""
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
    from platform.platform_services.workers.optimize_pricing_strategy import OptimizePricingStrategyStub
    return OptimizePricingStrategyStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_optimizes_pricing_strategy(worker, tenant_austa):
    """Should successfully optimize pricing strategy."""
    job = {
        "service_types": ["surgery", "imaging"],
        "market_segment": "private"
    }
    result = await worker.process(job)
    assert result["status"] == "optimized"
    assert "pricing_recommendations" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when service_types is missing."""
    job = {"market_segment": "private"}
    with pytest.raises(DomainException, match="service_types"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"service_types": ["surgery"], "market_segment": "private"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
