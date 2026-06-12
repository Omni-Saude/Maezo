"""Tests for CareTransitionsWorker."""
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
    """CareTransitionsWorker fixture."""
    from healthcare_platform.clinical_operations.workers.care_transitions import CareTransitionsWorker
    return CareTransitionsWorker(fhir_client=fhir_client)


class TestCareTransitionsWorker:
    """Test cases for CareTransitionsWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_manage_transition(self, worker, fhir_client, tenant_hospital_a):
        """Test successful care transition management."""
        fhir_client.create.return_value = {
            "resourceType": "Task",
            "id": "transition-123",
            "status": "requested",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "transition_type": "hospital-to-home",
            "from_location": "ward-3",
            "to_location": "home",
            "transition_date": "2025-01-20",
        })

        assert result["status"] == "completed"
        assert result["transition_id"] == "transition-123"
        assert result["transition_type"] == "hospital-to-home"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_transition_type_raises(self, worker, tenant_hospital_a):
        """Test that missing transition_type raises DomainException."""
        with pytest.raises(DomainException, match="transition_type is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "from_location": "ward-3",
            })

    @pytest.mark.asyncio
    async def test_transition_checklist_validation(self, worker, fhir_client, tenant_hospital_a):
        """Test transition checklist validation."""
        fhir_client.create.return_value = {"resourceType": "Task", "id": "transition-123"}

        result = await worker.execute({
            "patient_id": "patient-456",
            "transition_type": "hospital-to-home",
            "checklist": {
                "medications_reconciled": True,
                "follow_up_scheduled": True,
                "patient_education_completed": True,
                "equipment_arranged": False,
            },
        })

        assert result["checklist_complete"] is False
        assert "missing_items" in result

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "transition_type": "hospital-to-home",
            })
