"""Tests for DetectDataQualityIssuesStub."""
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
    from healthcare_platform.platform_services.workers.detect_data_quality_issues import DetectDataQualityIssuesStub
    return DetectDataQualityIssuesStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_detects_data_quality_issues(worker, tenant_austa):
    """Should successfully detect data quality issues."""
    job = {
        "data_sources": ["ehr", "billing"],
        "quality_checks": ["completeness", "accuracy"]
    }
    result = await worker.process(job)
    assert result["status"] == "detected"
    assert "issues" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when data_sources is missing."""
    job = {"quality_checks": ["completeness"]}
    with pytest.raises(DomainException, match="data_sources"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"data_sources": ["ehr"], "quality_checks": ["completeness"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
