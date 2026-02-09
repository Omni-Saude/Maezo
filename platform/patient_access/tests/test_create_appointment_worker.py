"""Tests for CreateAppointmentWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from platform.patient_access.workers.create_appointment_worker import CreateAppointmentWorker
    return CreateAppointmentWorker(fhir_client=fhir_client)


class TestCreateAppointmentWorker:
    @pytest.mark.asyncio
    async def test_happy_path_creates_appointment(self, worker, fhir_client, tenant_austa, mock_appointment):
        """Test successful appointment creation."""
        fhir_client.create.return_value = mock_appointment

        result = await worker.execute({
            "patient_id": "patient-123",
            "practitioner_id": "practitioner-001",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T10:30:00Z",
            "service_type": "consultation"
        })

        assert result["appointment_id"] == "appointment-789"
        assert result["status"] == "booked"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"patient_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_overlapping_appointment_raises(self, worker, fhir_client, tenant_austa):
        """Test that overlapping appointment raises DomainException."""
        fhir_client.create.side_effect = DomainException("Appointment slot already booked")

        with pytest.raises(DomainException):
            await worker.execute({
                "patient_id": "patient-123",
                "practitioner_id": "practitioner-001",
                "start_time": "2024-01-15T10:00:00Z",
                "end_time": "2024-01-15T10:30:00Z",
                "service_type": "consultation"
            })
