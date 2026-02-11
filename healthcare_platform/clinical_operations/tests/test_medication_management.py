"""Tests for MedicationManagementWorker."""
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
    """MedicationManagementWorker fixture."""
    from healthcare_platform.clinical_operations.workers.medication_management import MedicationManagementWorker
    return MedicationManagementWorker(fhir_client=fhir_client)


class TestMedicationManagementWorker:
    """Test cases for MedicationManagementWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_prescribe_medication(self, worker, fhir_client, tenant_hospital_a):
        """Test successful medication prescription."""
        fhir_client.create.return_value = {
            "resourceType": "MedicationRequest",
            "id": "medrq-123",
            "status": "active",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "medication_code": "387517004",
            "dosage": "500mg",
            "frequency": "BID",
            "route": "oral",
        })

        assert result["status"] == "completed"
        assert result["medication_request_id"] == "medrq-123"
        assert result["patient_id"] == "patient-456"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_medication_code_raises(self, worker, tenant_hospital_a):
        """Test that missing medication_code raises DomainException."""
        with pytest.raises(DomainException, match="medication_code is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "dosage": "500mg",
            })

    @pytest.mark.asyncio
    async def test_drug_interaction_warning(self, worker, fhir_client, tenant_hospital_a):
        """Test that drug interactions trigger warnings."""
        fhir_client.search.return_value = [
            {"resourceType": "MedicationRequest", "id": "existing-med", "medicationCodeableConcept": {"coding": [{"code": "123456"}]}}
        ]
        fhir_client.create.return_value = {"resourceType": "MedicationRequest", "id": "medrq-123", "status": "active"}

        result = await worker.execute({
            "patient_id": "patient-456",
            "medication_code": "warfarin",
            "dosage": "5mg",
        })

        assert "warnings" in result
        assert result["interaction_check_performed"] is True

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "medication_code": "387517004",
            })
