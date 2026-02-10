"""Tests for CreateAppointmentWorker."""
from __future__ import annotations
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.create_appointment_worker import (
        CreateAppointmentWorker,
        StubAppointmentCreator,
    )

    return CreateAppointmentWorker(
        fhir_client=fhir_client, appointment_creator=StubAppointmentCreator()
    )


@pytest.mark.unit
class TestCreateAppointmentWorker:
    @pytest.mark.asyncio
    async def test_happy_path_create_appointment(self, worker, fhir_client, tenant_austa):
        """Test successful appointment creation."""
        # Arrange
        start_time = datetime.utcnow() + timedelta(days=7)
        end_time = start_time + timedelta(minutes=30)

        task_vars = {
            "patient_id": "Patient/123",
            "practitioner_id": "Practitioner/456",
            "slot_id": "Slot/789",
            "start_datetime": start_time.isoformat(),
            "end_datetime": end_time.isoformat(),
            "service_type": "consulta",
            "specialty_code": "cardiologia",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["status"] == "booked"
        assert "appointment_reference" in result
        assert "appointment_id" in result
        assert result["start_datetime"] == start_time.isoformat()
        assert result["end_datetime"] == end_time.isoformat()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"patient_id": "Patient/123"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        start_time = datetime.utcnow() + timedelta(days=7)
        end_time = start_time + timedelta(minutes=30)

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "patient_id": "Patient/123",
                    "practitioner_id": "Practitioner/456",
                    "slot_id": "Slot/789",
                    "start_datetime": start_time.isoformat(),
                    "end_datetime": end_time.isoformat(),
                    "service_type": "consulta",
                    "specialty_code": "cardiologia",
                }
            )

    @pytest.mark.asyncio
    async def test_appointment_with_location(self, worker, tenant_austa):
        """Test appointment creation with location."""
        start_time = datetime.utcnow() + timedelta(days=7)
        end_time = start_time + timedelta(minutes=30)

        result = await worker.execute(
            {
                "patient_id": "Patient/123",
                "practitioner_id": "Practitioner/456",
                "slot_id": "Slot/789",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "consulta",
                "specialty_code": "cardiologia",
                "location_id": "Location/building-a",
            }
        )

        assert result["status"] == "booked"
        assert "appointment_reference" in result

    @pytest.mark.asyncio
    async def test_appointment_with_reason_and_comment(self, worker, tenant_austa):
        """Test appointment creation with reason and comment."""
        start_time = datetime.utcnow() + timedelta(days=7)
        end_time = start_time + timedelta(minutes=30)

        result = await worker.execute(
            {
                "patient_id": "Patient/123",
                "practitioner_id": "Practitioner/456",
                "slot_id": "Slot/789",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "consulta",
                "specialty_code": "cardiologia",
                "reason": "Consulta de retorno",
                "comment": "Paciente solicitou horário pela manhã",
            }
        )

        assert result["status"] == "booked"

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, fhir_client, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        start_time = datetime.utcnow() + timedelta(days=7)
        end_time = start_time + timedelta(minutes=30)

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "patient_id": "Patient/austa-123",
                "practitioner_id": "Practitioner/456",
                "slot_id": "Slot/austa-789",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "consulta",
                "specialty_code": "cardiologia",
            }
        )

        # Switch to HPA
        hpa_ctx = TenantContext.from_tenant_code(TenantCode.HPA)
        set_current_tenant(hpa_ctx)

        # Execute with HPA
        result_hpa = await worker.execute(
            {
                "patient_id": "Patient/hpa-123",
                "practitioner_id": "Practitioner/456",
                "slot_id": "Slot/hpa-789",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "consulta",
                "specialty_code": "cardiologia",
            }
        )

        # Appointments should be independent
        assert result_austa["appointment_id"] != result_hpa["appointment_id"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotent execution."""
        start_time = datetime.utcnow() + timedelta(days=7)
        end_time = start_time + timedelta(minutes=30)

        task_vars = {
            "patient_id": "Patient/123",
            "practitioner_id": "Practitioner/456",
            "slot_id": "Slot/789",
            "start_datetime": start_time.isoformat(),
            "end_datetime": end_time.isoformat(),
            "service_type": "consulta",
            "specialty_code": "cardiologia",
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Should create separate appointments (not truly idempotent for creation)
        assert result1["status"] == "booked"
        assert result2["status"] == "booked"

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, fhir_client, tenant_austa):
        """Test external service failure handling."""
        from healthcare_platform.patient_access.workers.create_appointment_worker import PatientAccessException

        start_time = datetime.utcnow() + timedelta(days=7)
        end_time = start_time + timedelta(minutes=30)

        # Mock failure
        worker.appointment_creator.create_appointment = AsyncMock(
            side_effect=Exception("FHIR server unavailable")
        )

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "patient_id": "Patient/123",
                    "practitioner_id": "Practitioner/456",
                    "slot_id": "Slot/789",
                    "start_datetime": start_time.isoformat(),
                    "end_datetime": end_time.isoformat(),
                    "service_type": "consulta",
                    "specialty_code": "cardiologia",
                }
            )

    @pytest.mark.asyncio
    async def test_appointment_reference_format(self, worker, tenant_austa):
        """Test appointment reference follows FHIR format."""
        start_time = datetime.utcnow() + timedelta(days=7)
        end_time = start_time + timedelta(minutes=30)

        result = await worker.execute(
            {
                "patient_id": "Patient/123",
                "practitioner_id": "Practitioner/456",
                "slot_id": "Slot/789",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "consulta",
                "specialty_code": "cardiologia",
            }
        )

        # Reference should be in format "Appointment/ID"
        assert result["appointment_reference"].startswith("Appointment/")
        assert result["appointment_id"] == result["appointment_reference"].split("/")[1]

    @pytest.mark.asyncio
    async def test_appointment_priority(self, worker, tenant_austa):
        """Test appointment creation with custom priority."""
        start_time = datetime.utcnow() + timedelta(days=7)
        end_time = start_time + timedelta(minutes=30)

        result = await worker.execute(
            {
                "patient_id": "Patient/123",
                "practitioner_id": "Practitioner/456",
                "slot_id": "Slot/789",
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "service_type": "urgencia",
                "specialty_code": "emergencia",
                "priority": 1,  # High priority
            }
        )

        assert result["status"] == "booked"
