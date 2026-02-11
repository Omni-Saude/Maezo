"""Tests for PrioritizeHighValueCasesStub."""
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
    from healthcare_platform.platform_services.workers.prioritize_high_value_cases import PrioritizeHighValueCasesStub
    return PrioritizeHighValueCasesStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_prioritizes_high_value_cases(worker, tenant_hospital_a):
    """Should successfully prioritize high value cases."""
    job = {
        "case_ids": ["CASE-001", "CASE-002", "CASE-003"],
        "priority_criteria": ["revenue", "complexity"]
    }
    result = await worker.process(job)
    assert result["status"] == "prioritized"
    assert "ranked_cases" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_hospital_a):
    """Should raise DomainException when case_ids is missing."""
    job = {"priority_criteria": ["revenue"]}
    with pytest.raises(DomainException, match="case_ids"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"case_ids": ["CASE-001"], "priority_criteria": ["revenue"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
