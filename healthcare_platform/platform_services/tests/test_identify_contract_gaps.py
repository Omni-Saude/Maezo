"""Tests for IdentifyContractGapsStub."""
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
    from healthcare_platform.platform_services.workers.identify_contract_gaps import IdentifyContractGapsStub
    return IdentifyContractGapsStub(fhir_client=fhir_client)

@pytest.mark.asyncio
async def test_happy_path_identifies_contract_gaps(worker, tenant_austa):
    """Should successfully identify contract gaps."""
    job = {
        "payer_ids": ["PAYER-001", "PAYER-002"],
        "gap_types": ["coverage", "reimbursement"]
    }
    result = await worker.process(job)
    assert result["status"] == "identified"
    assert "gaps" in result

@pytest.mark.asyncio
async def test_missing_required_field_raises(worker, tenant_austa):
    """Should raise DomainException when payer_ids is missing."""
    job = {"gap_types": ["coverage"]}
    with pytest.raises(DomainException, match="payer_ids"):
        await worker.process(job)

@pytest.mark.asyncio
async def test_no_tenant_raises(worker):
    """Should raise DomainException when tenant context is missing."""
    job = {"payer_ids": ["PAYER-001"], "gap_types": ["coverage"]}
    with pytest.raises(DomainException, match="tenant"):
        await worker.process(job)
