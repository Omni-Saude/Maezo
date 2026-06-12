"""Tests for TrackOptimizationRoiStub."""
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
    from healthcare_platform.platform_services.workers.track_optimization_roi import TrackOptimizationRoiStub
    return TrackOptimizationRoiStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_tracks_optimization_roi(worker, tenant_hospital_a):
    """Should successfully track optimization ROI."""
    job = {
        "optimization_ids": ["OPT-001", "OPT-002"],
        "tracking_period": "2024-Q1"
    }
    result = await worker.process(job)
    assert result["status"] == "tracked"
    assert "roi_metrics" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_hospital_a):
    """Should raise DomainException when optimization_ids is missing."""
    job = {"tracking_period": "2024-Q1"}
    with pytest.raises(DomainException, match="optimization_ids"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"optimization_ids": ["OPT-001"], "tracking_period": "2024-Q1"}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
