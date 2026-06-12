"""Tests for CarePlanningWorker."""
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
    """CarePlanningWorker fixture."""
    from healthcare_platform.clinical_operations.workers.care_planning import CarePlanningWorker
    return CarePlanningWorker(fhir_client=fhir_client)


class TestCarePlanningWorker:
    """Test cases for CarePlanningWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_create_care_plan(self, worker, fhir_client, tenant_hospital_a):
        """Test successful care plan creation."""
        fhir_client.create.return_value = {
            "resourceType": "CarePlan",
            "id": "careplan-123",
            "status": "active",
            "subject": {"reference": "Patient/patient-456"},
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "goals": ["Pain management", "Mobility improvement"],
            "activities": [{"detail": {"description": "Physical therapy"}}],
        })

        assert result["status"] == "completed"
        assert result["care_plan_id"] == "careplan-123"
        assert result["patient_id"] == "patient-456"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_patient_id_raises(self, worker, tenant_hospital_a):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException, match="patient_id is required"):
            await worker.execute({"goals": ["Goal 1"]})

    @pytest.mark.asyncio
    async def test_missing_goals_raises(self, worker, tenant_hospital_a):
        """Test that missing goals raises DomainException."""
        with pytest.raises(DomainException, match="goals are required"):
            await worker.execute({"patient_id": "patient-456"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "goals": ["Goal 1"],
            })
