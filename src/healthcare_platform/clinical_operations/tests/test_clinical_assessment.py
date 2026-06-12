"""Tests for ClinicalAssessmentWorker."""
from __future__ import annotations

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
    """ClinicalAssessmentWorker fixture."""
    from healthcare_platform.clinical_operations.workers.clinical_assessment import ClinicalAssessmentWorker
    return ClinicalAssessmentWorker(fhir_client=fhir_client)


class TestClinicalAssessmentWorker:
    """Test cases for ClinicalAssessmentWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_initial_assessment(self, worker, fhir_client, tenant_hospital_a):
        """Test successful initial clinical assessment."""
        fhir_client.search.return_value = [
            {"resourceType": "Patient", "id": "patient-123", "name": [{"given": ["João"], "family": "Silva"}]}
        ]
        fhir_client.create.return_value = {"resourceType": "Observation", "id": "obs-456", "status": "preliminary"}

        result = await worker.execute({
            "patient_id": "patient-123",
            "encounter_id": "encounter-789",
            "chief_complaint": "Dor abdominal",
            "assessment_type": "initial",
        })

        assert result["status"] == "completed"
        assert result["patient_id"] == "patient-123"
        assert result["encounter_id"] == "encounter-789"
        assert "observation_id" in result
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_patient_id_raises(self, worker, tenant_hospital_a):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException, match="patient_id is required"):
            await worker.execute({"encounter_id": "encounter-789"})

    @pytest.mark.asyncio
    async def test_missing_encounter_id_raises(self, worker, tenant_hospital_a):
        """Test that missing encounter_id raises DomainException."""
        with pytest.raises(DomainException, match="encounter_id is required"):
            await worker.execute({"patient_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-123",
                "encounter_id": "encounter-789",
            })
