"""Tests for TrackProcessPerformanceStub."""
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
    from healthcare_platform.platform_services.workers.track_process_performance import TrackProcessPerformanceStub
    return TrackProcessPerformanceStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_tracks_process_performance(worker, tenant_austa):
    """Should successfully track process performance."""
    job = {
        "process_ids": ["PROC-001", "PROC-002"],
        "metrics": ["duration", "throughput"]
    }
    result = await worker.process(job)
    assert result["status"] == "tracked"
    assert "performance_data" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when process_ids is missing."""
    job = {"metrics": ["duration"]}
    with pytest.raises(DomainException, match="process_ids"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"process_ids": ["PROC-001"], "metrics": ["duration"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
