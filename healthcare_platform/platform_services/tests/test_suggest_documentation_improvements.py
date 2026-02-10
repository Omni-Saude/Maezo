"""Tests for SuggestDocumentationImprovementsStub."""
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
    from healthcare_platform.platform_services.workers.suggest_documentation_improvements import SuggestDocumentationImprovementsStub
    return SuggestDocumentationImprovementsStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_suggests_documentation_improvements(worker, tenant_austa):
    """Should successfully suggest documentation improvements."""
    job = {
        "encounter_ids": ["ENC-125", "ENC-126"],
        "focus_areas": ["diagnosis", "procedures"]
    }
    result = await worker.process(job)
    assert result["status"] == "suggested"
    assert "suggestions" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when encounter_ids is missing."""
    job = {"focus_areas": ["diagnosis"]}
    with pytest.raises(DomainException, match="encounter_ids"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"encounter_ids": ["ENC-125"], "focus_areas": ["diagnosis"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
