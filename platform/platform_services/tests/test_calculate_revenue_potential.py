"""Tests for CalculateRevenuePotentialStub."""
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
    from platform.platform_services.workers.calculate_revenue_potential import CalculateRevenuePotentialStub
    return CalculateRevenuePotentialStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_calculates_revenue_potential(worker, tenant_austa):
    """Should successfully calculate revenue potential."""
    job = {
        "opportunity_ids": ["OPP-001", "OPP-002"],
        "calculation_method": "conservative"
    }
    result = await worker.process(job)
    assert result["status"] == "calculated"
    assert "revenue_potential" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when opportunity_ids is missing."""
    job = {"calculation_method": "conservative"}
    with pytest.raises(DomainException, match="opportunity_ids"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"opportunity_ids": ["OPP-001"], "calculation_method": "conservative"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
