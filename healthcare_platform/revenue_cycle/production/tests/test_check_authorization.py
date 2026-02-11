"""Tests for CheckAuthorizationWorker."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import AuthorizationDenied, AuthorizationExpired
from healthcare_platform.shared.integrations.insurance_api_client import AuthorizationResponse
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

from revenue_cycle.production.workers.check_authorization_worker import CheckAuthorizationWorker


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def insurance_client():
    return AsyncMock()


@pytest.fixture
def worker(insurance_client):
    return CheckAuthorizationWorker(insurance_client=insurance_client)


class TestCheckAuthorizationWorker:
    @pytest.mark.asyncio
    async def test_pre_authorized(self, worker, insurance_client, tenant_ctx):
        insurance_client.check_authorization_status.return_value = AuthorizationResponse(
            authorization_id="auth-1",
            payer_id="payer-1",
            status="approved",
            auth_number="AUTH-123",
        )

        result = await worker.execute({
            "enriched_procedures": [{"code": "40101010", "diagnosis_codes": ["J06.9"]}],
            "patient_reference": "Patient/pat-1",
            "payer_id": "payer-1",
            "existing_auth_number": "auth-1",
        })

        assert result["all_authorized"] is True
        assert result["auth_number"] == "auth-1"

    @pytest.mark.asyncio
    async def test_denied_raises(self, worker, insurance_client, tenant_ctx):
        insurance_client.check_authorization_status.return_value = AuthorizationResponse(
            authorization_id="auth-1",
            payer_id="payer-1",
            status="denied",
            denial_reason="Not covered",
        )

        with pytest.raises(AuthorizationDenied):
            await worker.execute({
                "enriched_procedures": [{"code": "40101010"}],
                "patient_reference": "Patient/pat-1",
                "payer_id": "payer-1",
                "existing_auth_number": "auth-1",
            })

    @pytest.mark.asyncio
    async def test_realtime_auth_approved(self, worker, insurance_client, tenant_ctx):
        insurance_client.request_authorization.return_value = AuthorizationResponse(
            authorization_id="new-auth",
            payer_id="payer-1",
            status="approved",
            auth_number="NEW-123",
            response_message="Approved",
        )

        result = await worker.execute({
            "enriched_procedures": [{"code": "40101010", "diagnosis_codes": ["J06.9"], "quantity": 1}],
            "patient_reference": "Patient/pat-1",
            "payer_id": "payer-1",
        })

        assert result["all_authorized"] is True
        assert result["auth_number"] == "NEW-123"
