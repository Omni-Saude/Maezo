"""Tests for AdverseEventDetectionWorker."""
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
    """AdverseEventDetectionWorker fixture."""
    from healthcare_platform.clinical_operations.workers.adverse_event_detection import AdverseEventDetectionWorker
    return AdverseEventDetectionWorker(fhir_client=fhir_client)


class TestAdverseEventDetectionWorker:
    """Test cases for AdverseEventDetectionWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_report_adverse_event(self, worker, fhir_client, tenant_hospital_a):
        """Test successful adverse event reporting."""
        fhir_client.create.return_value = {
            "resourceType": "AdverseEvent",
            "id": "ae-123",
            "actuality": "actual",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "event_type": "medication-error",
            "severity": "moderate",
            "description": "Wrong dosage administered",
            "detected_by": "practitioner-001",
        })

        assert result["status"] == "completed"
        assert result["adverse_event_id"] == "ae-123"
        assert result["severity"] == "moderate"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_event_type_raises(self, worker, tenant_hospital_a):
        """Test that missing event_type raises DomainException."""
        with pytest.raises(DomainException, match="event_type is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "description": "Some event",
            })

    @pytest.mark.asyncio
    async def test_automatic_detection_from_vitals(self, worker, fhir_client, tenant_hospital_a):
        """Test automatic adverse event detection from vital signs."""
        fhir_client.search.return_value = [
            {"resourceType": "Observation", "id": "obs-1", "valueQuantity": {"value": 40, "unit": "bpm"}}
        ]
        fhir_client.create.return_value = {"resourceType": "AdverseEvent", "id": "ae-123"}

        result = await worker.execute({
            "patient_id": "patient-456",
            "detection_mode": "automatic",
            "monitor_vital_signs": True,
        })

        assert result["auto_detected"] is True
        assert "bradycardia" in result["detected_events"]

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "event_type": "medication-error",
            })
