"""
Unit tests for Patient Medication Reminder Worker.

Tests notification flow for sending medication reminders to inpatient.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.patient_medication_reminder_worker import (
    ClinicalOperationsException,
    PatientMedicationReminderInput,
    PatientMedicationReminderOutput,
    PatientMedicationReminderWorker,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant
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
    return PatientMedicationReminderWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_task_variables() -> dict[str, Any]:
    """Valid task variables for medication reminder notification."""
    return {
        "patient_id": "Patient/12345",
        "phone_number": "+5511999887766",
        "medication_name": "Dipirona 500mg",
        "dosage": "1 comprimido",
        "scheduled_time": "14:00",
        "instructions": "Tomar com água após as refeições",
    }


@pytest.mark.unit
class TestPatientMedicationReminderWorker:
    """Test suite for PatientMedicationReminderWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker: PatientMedicationReminderWorker, tenant_ctx, valid_task_variables
    ):
        """Test successful medication reminder notification."""
        result = await worker.execute(valid_task_variables)

        # Verify output structure
        output = PatientMedicationReminderOutput.model_validate(result)
        assert output.notification_sent is True
        assert output.message_id is not None
        assert output.message_id.startswith("stub-msg-")
        assert output.sent_at is not None
        assert output.reminder_id is not None
        assert output.response_received is False
        assert output.response_action is None

        # Verify timestamp is valid ISO 8601
        datetime.fromisoformat(output.sent_at)

    @pytest.mark.asyncio
    async def test_output_fields(
        self, worker: PatientMedicationReminderWorker, tenant_ctx, valid_task_variables
    ):
        """Test that output has all expected fields."""
        result = await worker.execute(valid_task_variables)

        # Verify all fields present
        assert "notification_sent" in result
        assert "message_id" in result
        assert "sent_at" in result
        assert "reminder_id" in result
        assert "response_received" in result
        assert "response_action" in result

        # Verify types
        assert isinstance(result["notification_sent"], bool)
        assert isinstance(result["message_id"], str) or result["message_id"] is None
        assert isinstance(result["sent_at"], str)
        assert isinstance(result["reminder_id"], str)
        assert isinstance(result["response_received"], bool)

        # Verify values
        output = PatientMedicationReminderOutput.model_validate(result)
        assert output.notification_sent is True
        assert output.message_id is not None
        assert len(output.reminder_id) > 0
        assert output.response_received is False

    @pytest.mark.asyncio
    async def test_interactive_buttons(
        self, worker: PatientMedicationReminderWorker, tenant_ctx, valid_task_variables
    ):
        """Test that template has 3 interactive buttons."""
        # Mock the WhatsApp client to capture template
        captured_template = None

        def mock_send(phone_number: str, template: Any) -> str:
            nonlocal captured_template
            captured_template = template
            return "stub-msg-12345"

        worker._whatsapp_client.send_template_message = mock_send

        result = await worker.execute(valid_task_variables)

        # Verify template structure
        assert captured_template is not None
        assert captured_template.name == "medication_reminder_v1"
        assert captured_template.language == "pt_BR"

        # Should have body + 3 buttons = 4 components
        assert len(captured_template.components) == 4

        # Verify body component
        body_component = captured_template.components[0]
        assert body_component["type"] == "body"
        assert len(body_component["parameters"]) == 4

        # Verify body parameters: medication_name, dosage, scheduled_time, instructions
        params = body_component["parameters"]
        assert params[0]["text"] == "Dipirona 500mg"
        assert params[1]["text"] == "1 comprimido"
        assert params[2]["text"] == "14:00"
        assert params[3]["text"] == "Tomar com água após as refeições"

        # Verify button components
        output = PatientMedicationReminderOutput.model_validate(result)
        reminder_id = output.reminder_id

        button1 = captured_template.components[1]
        assert button1["type"] == "button"
        assert button1["sub_type"] == "quick_reply"
        assert button1["index"] == "0"
        assert button1["parameters"][0]["payload"] == f"taken:{reminder_id}"

        button2 = captured_template.components[2]
        assert button2["type"] == "button"
        assert button2["sub_type"] == "quick_reply"
        assert button2["index"] == "1"
        assert button2["parameters"][0]["payload"] == f"remind_later:{reminder_id}"

        button3 = captured_template.components[3]
        assert button3["type"] == "button"
        assert button3["sub_type"] == "quick_reply"
        assert button3["index"] == "2"
        assert button3["parameters"][0]["payload"] == f"need_help:{reminder_id}"

    @pytest.mark.asyncio
    async def test_whatsapp_failure(
        self, worker: PatientMedicationReminderWorker, tenant_ctx, valid_task_variables
    ):
        """Test that WhatsApp client failure raises ClinicalOperationsException."""
        # Mock WhatsApp client to raise exception
        worker._whatsapp_client.send_template_message = AsyncMock(
            side_effect=Exception("WhatsApp API error")
        )

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "Falha ao enviar" in str(exc_info.value)
        assert exc_info.value.code == "CLINICAL_OPERATIONS_ERROR"
        assert exc_info.value.bpmn_error_code == "CLINICAL_OPERATIONS_ERROR"

    @pytest.mark.asyncio
    async def test_missing_patient_id(
        self, worker: PatientMedicationReminderWorker, tenant_ctx, valid_task_variables
    ):
        """Test that missing patient_id raises ClinicalOperationsException."""
        del valid_task_variables["patient_id"]

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "inválidos" in str(exc_info.value).lower()
        assert exc_info.value.code == "CLINICAL_OPERATIONS_ERROR"

    @pytest.mark.asyncio
    async def test_missing_medication_name(
        self, worker: PatientMedicationReminderWorker, tenant_ctx, valid_task_variables
    ):
        """Test that missing medication_name raises ClinicalOperationsException."""
        del valid_task_variables["medication_name"]

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "inválidos" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_missing_dosage(
        self, worker: PatientMedicationReminderWorker, tenant_ctx, valid_task_variables
    ):
        """Test that missing dosage raises ClinicalOperationsException."""
        del valid_task_variables["dosage"]

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert "inválidos" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_no_tenant_context(
        self, worker: PatientMedicationReminderWorker, valid_task_variables
    ):
        """Test that missing tenant context raises InvalidTenant."""
        # Clear tenant context
        clear_tenant()

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_unique_reminder_ids(
        self, worker: PatientMedicationReminderWorker, tenant_ctx, valid_task_variables
    ):
        """Test that each reminder gets a unique ID."""
        result1 = await worker.execute(valid_task_variables)
        result2 = await worker.execute(valid_task_variables)

        output1 = PatientMedicationReminderOutput.model_validate(result1)
        output2 = PatientMedicationReminderOutput.model_validate(result2)

        # Reminder IDs should be different
        assert output1.reminder_id != output2.reminder_id

    def test_input_validation_direct(self):
        """Test input model validation directly."""
        # Valid input
        valid_input = PatientMedicationReminderInput(
            patient_id="Patient/123",
            phone_number="+5511999887766",
            medication_name="Paracetamol",
            dosage="500mg",
            scheduled_time="08:00",
            instructions="Tomar com água",
        )
        assert valid_input.medication_name == "Paracetamol"
        assert valid_input.dosage == "500mg"

        # Missing required field
        with pytest.raises(ValidationError):
            PatientMedicationReminderInput(
                patient_id="Patient/123",
                phone_number="+5511999887766",
                medication_name="Paracetamol",
                # Missing dosage
                scheduled_time="08:00",
                instructions="Tomar com água",
            )

    def test_output_model_to_variables(self):
        """Test output model to_variables method."""
        output = PatientMedicationReminderOutput(
            notification_sent=True,
            message_id="msg-123",
            sent_at="2024-01-15T14:00:00Z",
            reminder_id="reminder-456",
            response_received=False,
            response_action=None,
        )

        variables = output.to_variables()

        assert variables["notification_sent"] is True
        assert variables["message_id"] == "msg-123"
        assert variables["sent_at"] == "2024-01-15T14:00:00Z"
        assert variables["reminder_id"] == "reminder-456"
        assert variables["response_received"] is False
        assert variables["response_action"] is None

    def test_output_model_with_response(self):
        """Test output model with patient response."""
        output = PatientMedicationReminderOutput(
            notification_sent=True,
            message_id="msg-123",
            sent_at="2024-01-15T14:00:00Z",
            reminder_id="reminder-456",
            response_received=True,
            response_action="taken",
        )

        assert output.response_received is True
        assert output.response_action == "taken"

        variables = output.to_variables()
        assert variables["response_received"] is True
        assert variables["response_action"] == "taken"
