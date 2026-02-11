"""Tests for ClinicalDecisionSupportWorker."""
from __future__ import annotations

from datetime import datetime
import pytest
from unittest.mock import AsyncMock

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant


@pytest.fixture
def tenant_hospital_a():
    """Set up AUSTA tenant context."""
    ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def fhir_client():
    """Mock FHIR client fixture."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """ClinicalDecisionSupportWorker fixture."""
    from healthcare_platform.clinical_operations.workers.clinical_decision_support import ClinicalDecisionSupportWorker
    return ClinicalDecisionSupportWorker(fhir_client=fhir_client)


class TestClinicalDecisionSupportWorker:
    """Test cases for ClinicalDecisionSupportWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_generate_recommendations(self, worker, fhir_client, tenant_hospital_a):
        """Test successful CDS recommendation generation."""
        fhir_client.search.return_value = [
            {"resourceType": "Observation", "id": "obs-1", "code": {"coding": [{"code": "glucose"}]}}
        ]

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "context": "diabetes-management",
            "clinical_data": {"glucose": 180, "hba1c": 7.5},
        })

        assert result["status"] == "completed"
        assert "recommendations" in result
        assert len(result["recommendations"]) > 0
        fhir_client.search.assert_called()

    @pytest.mark.asyncio
    async def test_missing_context_raises(self, worker, tenant_hospital_a):
        """Test that missing context raises DomainException."""
        with pytest.raises(DomainException, match="context is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "clinical_data": {},
            })

    @pytest.mark.asyncio
    async def test_drug_interaction_alert(self, worker, fhir_client, tenant_hospital_a):
        """Test drug interaction detection."""
        fhir_client.search.return_value = [
            {"resourceType": "MedicationRequest", "id": "med-1", "medicationCodeableConcept": {"coding": [{"code": "warfarin"}]}}
        ]

        result = await worker.execute({
            "patient_id": "patient-456",
            "context": "drug-interaction",
            "new_medication": "aspirin",
        })

        assert result["interaction_detected"] is True
        assert "warning" in result

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "context": "diabetes-management",
            })
