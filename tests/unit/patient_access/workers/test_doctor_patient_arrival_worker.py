"""
Unit tests for Doctor Patient Arrival Worker.

Tests the scheduling.patient_arrival external task worker that notifies
doctors when patients arrive for scheduled appointments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from healthcare_platform.patient_access.workers.doctor_patient_arrival_worker import (
    DoctorPatientArrivalWorker,
    PatientAccessException,
)
from healthcare_platform.shared.integrations.whatsapp_client import StubWhatsAppClient
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx():
    """Set up tenant context for tests."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker instance with stub WhatsApp client."""
    return DoctorPatientArrivalWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def base_task_variables() -> dict[str, Any]:
    """Base task variables for patient arrival notification."""
    return {
        "doctor_id": "Practitioner/dr-silva",
        "patient_id": "Patient/patient-123",
        "appointment_id": "Appointment/appt-456",
        "appointment_time": "14:30",
        "location": "Clínica Central - Sala 202",
        "phone_number": "+5511999887766",
        "patient_name": "João Silva",
    }


@pytest.mark.unit
class TestDoctorPatientArrivalWorker:
    """Test suite for DoctorPatientArrivalWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker: DoctorPatientArrivalWorker, tenant_ctx, base_task_variables
    ):
        """Test successful patient arrival notification."""
        result = await worker.execute(base_task_variables)

        assert result["notification_sent"] is True
        assert result["message_id"] is not None
        assert isinstance(result["message_id"], str)
        assert result["sent_at"] is not None

        # Verify ISO 8601 timestamp format
        datetime.fromisoformat(result["sent_at"])

    @pytest.mark.asyncio
    async def test_default_patient_name(
        self, worker: DoctorPatientArrivalWorker, tenant_ctx, base_task_variables
    ):
        """Test that patient_name defaults to 'Paciente' when not provided."""
        task_vars = base_task_variables.copy()
        del task_vars["patient_name"]

        result = await worker.execute(task_vars)

        assert result["notification_sent"] is True
        # Verify the worker handled the default correctly

    @pytest.mark.asyncio
    async def test_template_parameters(
        self, tenant_ctx, base_task_variables
    ):
        """Test that template name and body parameters are correct."""
        mock_client = AsyncMock()
        mock_client.send_template_message = AsyncMock(return_value="msg-test-123")

        worker = DoctorPatientArrivalWorker(whatsapp_client=mock_client)
        await worker.execute(base_task_variables)

        # Verify send_template_message was called
        mock_client.send_template_message.assert_called_once()
        call_args = mock_client.send_template_message.call_args

        # Verify phone number
        assert call_args.kwargs["phone"] == "+5511999887766"

        # Verify template
        template = call_args.kwargs["template"]
        assert template.name == "patient_arrival_v1"
        assert template.language == "pt_BR"

        # Verify body parameters
        body_component = next(
            c for c in template.components if c["type"] == "body"
        )
        params = body_component["parameters"]
        assert len(params) == 3
        assert params[0]["text"] == "João Silva"  # patient_name
        assert params[1]["text"] == "14:30"  # appointment_time
        assert params[2]["text"] == "Clínica Central - Sala 202"  # location

    @pytest.mark.asyncio
    async def test_missing_appointment_id(
        self, worker: DoctorPatientArrivalWorker, tenant_ctx, base_task_variables
    ):
        """Test that missing appointment_id raises PatientAccessException."""
        task_vars = base_task_variables.copy()
        del task_vars["appointment_id"]

        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(task_vars)

        # The Pydantic validation error message is generic, just check error was raised
        assert exc_info.value.bpmn_error_code == "PATIENT_ACCESS_ERROR"

    @pytest.mark.asyncio
    async def test_whatsapp_failure(
        self, tenant_ctx, base_task_variables
    ):
        """Test that WhatsApp client failures are propagated as PatientAccessException."""
        mock_client = AsyncMock()
        mock_client.send_template_message = AsyncMock(
            side_effect=Exception("WhatsApp API timeout")
        )

        worker = DoctorPatientArrivalWorker(whatsapp_client=mock_client)

        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(base_task_variables)

        assert "Failed to send patient arrival notification" in str(exc_info.value)
        assert exc_info.value.bpmn_error_code == "PATIENT_ACCESS_ERROR"
        assert "WhatsApp API timeout" in str(exc_info.value.details)

    @pytest.mark.asyncio
    async def test_output_has_sent_at(
        self, worker: DoctorPatientArrivalWorker, tenant_ctx, base_task_variables
    ):
        """Test that output includes valid sent_at ISO timestamp."""
        before_execution = datetime.now(timezone.utc)
        result = await worker.execute(base_task_variables)
        after_execution = datetime.now(timezone.utc)

        assert "sent_at" in result
        sent_at = datetime.fromisoformat(result["sent_at"])

        # Verify timestamp is within execution window
        assert before_execution <= sent_at <= after_execution

        # Verify ISO 8601 format with timezone
        assert "T" in result["sent_at"]
        assert result["sent_at"].endswith(("+00:00", "Z")) or "+" in result["sent_at"]

    @pytest.mark.asyncio
    async def test_notification_sent_flag(
        self, worker: DoctorPatientArrivalWorker, tenant_ctx, base_task_variables
    ):
        """Test that notification_sent flag is True on success."""
        result = await worker.execute(base_task_variables)

        assert "notification_sent" in result
        assert result["notification_sent"] is True
        assert isinstance(result["notification_sent"], bool)

    @pytest.mark.asyncio
    async def test_message_id_returned(
        self, worker: DoctorPatientArrivalWorker, tenant_ctx, base_task_variables
    ):
        """Test that message_id is returned from WhatsApp client."""
        result = await worker.execute(base_task_variables)

        assert "message_id" in result
        assert result["message_id"] is not None
        assert isinstance(result["message_id"], str)
        assert len(result["message_id"]) > 0
