"""Tests for EnrichProcedureWorker."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import CodingException, MissingDiagnosisCode
from platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

from revenue_cycle.production.workers.enrich_procedure_worker import EnrichProcedureWorker


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def fhir_client():
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    return EnrichProcedureWorker(fhir_client=fhir_client)


class TestEnrichProcedureWorker:
    @pytest.mark.asyncio
    async def test_enrich_with_diagnosis(self, worker, fhir_client, tenant_ctx):
        fhir_client.get_encounter.return_value = {
            "reasonCode": [{"coding": [{"system": "icd-10", "code": "J06.9"}]}],
            "participant": [{"individual": {"reference": "Practitioner/dr-1"}}],
        }
        fhir_client.read.return_value = {
            "bodySite": [{"coding": [{"system": "snomed", "code": "123", "display": "Chest"}]}]
        }

        result = await worker.execute({
            "captured_procedures": [{"code": "40101010", "procedure_id": "p-1"}],
            "encounter_reference": "Encounter/enc-1",
        })

        assert result["diagnosis_codes"] == ["J06.9"]
        assert len(result["enriched_procedures"]) == 1
        assert result["enriched_procedures"][0]["performer_references"] == ["Practitioner/dr-1"]

    @pytest.mark.asyncio
    async def test_missing_diagnosis_raises(self, worker, fhir_client, tenant_ctx):
        fhir_client.get_encounter.return_value = {
            "reasonCode": [],
            "participant": [],
        }

        with pytest.raises(MissingDiagnosisCode):
            await worker.execute({
                "captured_procedures": [{"code": "40101010"}],
                "encounter_reference": "Encounter/enc-1",
            })

    @pytest.mark.asyncio
    async def test_empty_procedures_raises(self, worker, tenant_ctx):
        with pytest.raises(CodingException):
            await worker.execute({
                "captured_procedures": [],
                "encounter_reference": "Encounter/enc-1",
            })
