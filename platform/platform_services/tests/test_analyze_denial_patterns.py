"""Tests for AnalyzeDenialPatternsStub."""
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
    from platform.platform_services.workers.analyze_denial_patterns import AnalyzeDenialPatternsStub
    return AnalyzeDenialPatternsStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_analyzes_denial_patterns(worker, tenant_austa):
    """Should successfully analyze denial patterns."""
    job = {
        "period": "2024-Q1",
        "payer_ids": ["PAYER-001", "PAYER-002"]
    }
    result = await worker.process(job)
    assert result["status"] == "analyzed"
    assert "patterns" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when period is missing."""
    job = {"payer_ids": ["PAYER-001"]}
    with pytest.raises(DomainException, match="period"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"period": "2024-Q1", "payer_ids": ["PAYER-001"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
