"""Tests for AlertOnAnomaliesStub."""
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
    from platform.platform_services.workers.alert_on_anomalies import AlertOnAnomaliesStub
    return AlertOnAnomaliesStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_alerts_on_anomalies(worker, tenant_austa):
    """Should successfully detect and alert on anomalies."""
    job = {
        "monitoring_targets": ["claims", "appointments"],
        "anomaly_types": ["spike", "drop"]
    }
    result = await worker.process(job)
    assert result["status"] == "alerted"
    assert "anomalies_detected" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when monitoring_targets is missing."""
    job = {"anomaly_types": ["spike"]}
    with pytest.raises(DomainException, match="monitoring_targets"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"monitoring_targets": ["claims"], "anomaly_types": ["spike"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
