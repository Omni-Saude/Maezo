"""Tests for DischargePlanningWorker."""
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
    """DischargePlanningWorker fixture."""
    from healthcare_platform.clinical_operations.workers.discharge_planning import DischargePlanningWorker
    return DischargePlanningWorker(fhir_client=fhir_client)


class TestDischargePlanningWorker:
    """Test cases for DischargePlanningWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_create_discharge_plan(self, worker, fhir_client, tenant_hospital_a):
        """Test successful discharge plan creation."""
        fhir_client.create.return_value = {
            "resourceType": "EpisodeOfCare",
            "id": "discharge-123",
            "status": "finished",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "discharge_disposition": "home",
            "follow_up_required": True,
            "medications": ["med-001", "med-002"],
            "instructions": "Rest for 3 days, follow-up in 1 week",
        })

        assert result["status"] == "completed"
        assert result["discharge_plan_id"] == "discharge-123"
        assert result["disposition"] == "home"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_discharge_disposition_raises(self, worker, tenant_hospital_a):
        """Test that missing discharge_disposition raises DomainException."""
        with pytest.raises(DomainException, match="discharge_disposition is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "encounter_id": "encounter-789",
            })

    @pytest.mark.asyncio
    async def test_discharge_readiness_assessment(self, worker, fhir_client, tenant_hospital_a):
        """Test discharge readiness assessment."""
        fhir_client.search.return_value = [
            {"resourceType": "Observation", "id": "obs-1", "status": "final"}
        ]

        result = await worker.execute({
            "patient_id": "patient-456",
            "assessment_type": "readiness",
            "criteria": ["vitals-stable", "mobility-adequate", "home-support-confirmed"],
        })

        assert "readiness_score" in result
        assert result["ready_for_discharge"] in [True, False]

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "discharge_disposition": "home",
            })
