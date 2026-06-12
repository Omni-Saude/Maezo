"""Tests for PersistProductionWorker."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import BillingException, ExternalServiceException
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

from revenue_cycle.production.workers.persist_production_worker import PersistProductionWorker


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def fhir_client():
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    return PersistProductionWorker(fhir_client=fhir_client)


class TestPersistProductionWorker:
    @pytest.mark.asyncio
    async def test_persist_success(self, worker, fhir_client, tenant_ctx):
        fhir_client.create.return_value = {"id": "claim-123"}

        result = await worker.execute({
            "compatible_procedures": [
                {"code": "40101010", "display": "Consulta", "quantity": 1,
                 "unit_price": "150.00", "total_price": "150.00"},
            ],
            "encounter_reference": "Encounter/enc-1",
            "patient_reference": "Patient/pat-1",
            "total_amount": "150.00",
            "diagnosis_codes": ["J06.9"],
        })

        assert result["claim_reference"] == "Claim/claim-123"
        assert result["production_id"]
        assert result["persisted_at"]
        assert fhir_client.create.call_count >= 1

    @pytest.mark.asyncio
    async def test_empty_procedures_raises(self, worker, tenant_ctx):
        with pytest.raises(BillingException):
            await worker.execute({
                "compatible_procedures": [],
                "encounter_reference": "Encounter/enc-1",
                "patient_reference": "Patient/pat-1",
                "total_amount": "0.00",
                "diagnosis_codes": [],
            })

    @pytest.mark.asyncio
    async def test_fhir_unavailable_raises(self, worker, fhir_client, tenant_ctx):
        fhir_client.create.side_effect = Exception("Connection refused")

        with pytest.raises(ExternalServiceException):
            await worker.execute({
                "compatible_procedures": [
                    {"code": "40101010", "display": "Consulta", "quantity": 1,
                     "unit_price": "150.00", "total_price": "150.00"},
                ],
                "encounter_reference": "Encounter/enc-1",
                "patient_reference": "Patient/pat-1",
                "total_amount": "150.00",
                "diagnosis_codes": ["J06.9"],
            })

    @pytest.mark.asyncio
    async def test_no_pii_in_claim_resource(self, worker, fhir_client, tenant_ctx):
        fhir_client.create.return_value = {"id": "claim-456"}

        await worker.execute({
            "compatible_procedures": [
                {"code": "40101010", "display": "Consulta", "quantity": 1,
                 "unit_price": "150.00", "total_price": "150.00"},
            ],
            "encounter_reference": "Encounter/enc-1",
            "patient_reference": "Patient/pat-1",
            "total_amount": "150.00",
            "diagnosis_codes": ["J06.9"],
        })

        # Verify FHIR resource uses references, not PII
        call_args = fhir_client.create.call_args_list[0]
        claim_resource = call_args[0][1]  # Second positional arg
        assert claim_resource["patient"]["reference"] == "Patient/pat-1"
        # No name, CPF, or other PII fields
        assert "name" not in claim_resource
        assert "cpf" not in str(claim_resource).lower()
