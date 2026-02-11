"""Tests for VitalSignsMonitoringWorker."""
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
    """VitalSignsMonitoringWorker fixture."""
    from healthcare_platform.clinical_operations.workers.vital_signs_monitoring import VitalSignsMonitoringWorker
    return VitalSignsMonitoringWorker(fhir_client=fhir_client)


class TestVitalSignsMonitoringWorker:
    """Test cases for VitalSignsMonitoringWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_record_vital_signs(self, worker, fhir_client, tenant_hospital_a):
        """Test successful vital signs recording."""
        fhir_client.create.return_value = {
            "resourceType": "Observation",
            "id": "obs-vitals-123",
            "status": "final",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "vital_signs": {
                "blood_pressure": {"systolic": 120, "diastolic": 80},
                "heart_rate": 72,
                "temperature": 36.5,
                "respiratory_rate": 16,
                "oxygen_saturation": 98,
            },
        })

        assert result["status"] == "completed"
        assert result["patient_id"] == "patient-456"
        assert len(result["observations_created"]) == 5
        assert fhir_client.create.call_count == 5

    @pytest.mark.asyncio
    async def test_missing_vital_signs_raises(self, worker, tenant_hospital_a):
        """Test that missing vital_signs raises DomainException."""
        with pytest.raises(DomainException, match="vital_signs are required"):
            await worker.execute({
                "patient_id": "patient-456",
                "encounter_id": "encounter-789",
            })

    @pytest.mark.asyncio
    async def test_abnormal_vital_signs_triggers_alert(self, worker, fhir_client, tenant_hospital_a):
        """Test that abnormal vital signs trigger alerts."""
        fhir_client.create.return_value = {"resourceType": "Observation", "id": "obs-123", "status": "final"}

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "vital_signs": {
                "blood_pressure": {"systolic": 180, "diastolic": 110},
                "heart_rate": 120,
            },
        })

        assert result["alerts_triggered"] is True
        assert "blood_pressure" in result["abnormal_values"]

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "vital_signs": {"heart_rate": 72},
            })
