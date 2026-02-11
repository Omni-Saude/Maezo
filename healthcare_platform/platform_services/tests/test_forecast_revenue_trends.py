"""Tests for ForecastRevenueTrendsStub."""
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
    from healthcare_platform.platform_services.workers.forecast_revenue_trends import ForecastRevenueTrendsStub
    return ForecastRevenueTrendsStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_forecasts_revenue_trends(worker, tenant_hospital_a):
    """Should successfully forecast revenue trends."""
    job = {
        "forecast_horizon": "12_months",
        "forecast_methods": ["time_series", "regression"]
    }
    result = await worker.process(job)
    assert result["status"] == "forecasted"
    assert "forecast_data" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_hospital_a):
    """Should raise DomainException when forecast_horizon is missing."""
    job = {"forecast_methods": ["time_series"]}
    with pytest.raises(DomainException, match="forecast_horizon"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"forecast_horizon": "12_months", "forecast_methods": ["time_series"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
