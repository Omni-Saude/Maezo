"""Tests for IdentifyCodingOpportunitiesStub."""
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
    from healthcare_platform.platform_services.workers.identify_coding_opportunities import IdentifyCodingOpportunitiesStub
    return IdentifyCodingOpportunitiesStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_identifies_coding_opportunities(worker, tenant_austa):
    """Should successfully identify coding opportunities."""
    job = {
        "encounter_ids": ["ENC-123", "ENC-124"],
        "opportunity_types": ["upcoding", "unbundling"]
    }
    result = await worker.process(job)
    assert result["status"] == "identified"
    assert "opportunities" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when encounter_ids is missing."""
    job = {"opportunity_types": ["upcoding"]}
    with pytest.raises(DomainException, match="encounter_ids"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"encounter_ids": ["ENC-123"], "opportunity_types": ["upcoding"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
