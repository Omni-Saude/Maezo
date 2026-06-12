"""Tests for ClinicalAlertsWorker."""
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
    """ClinicalAlertsWorker fixture."""
    from healthcare_platform.clinical_operations.workers.clinical_alerts import ClinicalAlertsWorker
    return ClinicalAlertsWorker(fhir_client=fhir_client)


class TestClinicalAlertsWorker:
    """Test cases for ClinicalAlertsWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_create_critical_alert(self, worker, fhir_client, tenant_hospital_a):
        """Test successful critical alert creation."""
        fhir_client.create.return_value = {
            "resourceType": "Flag",
            "id": "alert-123",
            "status": "active",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "alert_type": "critical",
            "alert_code": "sepsis-suspected",
            "message": "Sepsis criteria met - immediate attention required",
        })

        assert result["status"] == "completed"
        assert result["alert_id"] == "alert-123"
        assert result["severity"] == "critical"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_alert_type_raises(self, worker, tenant_hospital_a):
        """Test that missing alert_type raises DomainException."""
        with pytest.raises(DomainException, match="alert_type is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "message": "Alert message",
            })

    @pytest.mark.asyncio
    async def test_notification_sent_for_critical_alerts(self, worker, fhir_client, tenant_hospital_a):
        """Test that critical alerts trigger notifications."""
        fhir_client.create.return_value = {"resourceType": "Flag", "id": "alert-123", "status": "active"}

        result = await worker.execute({
            "patient_id": "patient-456",
            "alert_type": "critical",
            "alert_code": "cardiac-arrest",
            "message": "Cardiac arrest alert",
        })

        assert result["notification_sent"] is True
        assert "recipients" in result

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "alert_type": "critical",
            })
