"""
Unit tests for Patient Health Anniversary Worker.

Tests health milestone celebration notifications with interactive sharing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from healthcare_platform.patient_access.workers.patient_health_anniversary_worker import (
    PatientAccessException,
    PatientHealthAnniversaryInput,
    PatientHealthAnniversaryOutput,
    PatientHealthAnniversaryWorker,
)
from healthcare_platform.shared.integrations.whatsapp_client import (
    StubWhatsAppClient,
    WhatsAppTemplate,
)
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
    return PatientHealthAnniversaryWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_input() -> dict[str, Any]:
    """Valid input variables for health anniversary notification."""
    return {
        "patient_id": "patient-456",
        "phone_number": "+5511987654321",
        "patient_name": "Jo\u00e3o",
        "milestone_type": "cancer_free",
        "milestone_date": "2023-06-15",
        "years_since": 3,
    }


@pytest.mark.unit
class TestPatientHealthAnniversaryWorker:
    """Test suite for PatientHealthAnniversaryWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker: PatientHealthAnniversaryWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test successful health anniversary notification."""
        result = await worker.execute(valid_input)

        assert result["notification_sent"] is True
        assert result["message_id"] is not None
        assert result["sent_at"] is not None

        sent_at = datetime.fromisoformat(result["sent_at"])
        assert sent_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_milestone_labels(
        self, worker: PatientHealthAnniversaryWorker
    ):
        """Test milestone type to label mapping."""
        expected = {
            "cancer_free": "livre de c\u00e2ncer",
            "transplant": "de transplante",
            "surgery_recovery": "de recupera\u00e7\u00e3o cir\u00fargica",
            "diabetes_managed": "controlando diabetes",
        }

        for milestone_type, expected_label in expected.items():
            label = worker._get_milestone_label(milestone_type)
            assert label == expected_label, f"{milestone_type} should map to {expected_label}"

    @pytest.mark.asyncio
    async def test_unknown_milestone_returns_raw(
        self, worker: PatientHealthAnniversaryWorker
    ):
        """Test unknown milestone type returns raw value."""
        label = worker._get_milestone_label("custom_milestone")
        assert label == "custom_milestone"

    @pytest.mark.asyncio
    async def test_interactive_buttons_present(
        self, worker: PatientHealthAnniversaryWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test that interactive buttons are included in the template."""
        captured_template = None

        async def capture_send(phone: str, template: WhatsAppTemplate) -> str:
            nonlocal captured_template
            captured_template = template
            return "msg-123"

        worker.whatsapp_client.send_template_message = capture_send

        await worker.execute(valid_input)

        assert captured_template is not None
        button_components = [
            c for c in captured_template.components if c["type"] == "button"
        ]
        assert len(button_components) == 2
        assert button_components[0]["parameters"][0]["text"] == "Compartilhar Hist\u00f3ria"
        assert button_components[1]["parameters"][0]["text"] == "Agradecer Equipe"

    @pytest.mark.asyncio
    async def test_missing_patient_id(
        self, worker: PatientHealthAnniversaryWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test error when patient_id is missing."""
        invalid_input = {**valid_input}
        del invalid_input["patient_id"]

        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(invalid_input)

        assert exc_info.value.code == "PATIENT_ACCESS_ERROR"
        assert "validation_errors" in exc_info.value.details

    @pytest.mark.asyncio
    async def test_whatsapp_failure(
        self, worker: PatientHealthAnniversaryWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test error handling when WhatsApp send fails."""

        async def failing_send(phone: str, template: WhatsAppTemplate) -> str:
            raise ConnectionError("WhatsApp API unavailable")

        worker.whatsapp_client.send_template_message = failing_send

        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(valid_input)

        assert exc_info.value.code == "PATIENT_ACCESS_ERROR"
        assert "patient_id" in exc_info.value.details

    @pytest.mark.asyncio
    async def test_output_fields(
        self, worker: PatientHealthAnniversaryWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test output contains all required fields including feedback_received."""
        result = await worker.execute(valid_input)

        assert "notification_sent" in result
        assert "message_id" in result
        assert "sent_at" in result
        assert "feedback_received" in result

        assert result["feedback_received"] is False

        output = PatientHealthAnniversaryOutput(**result)
        assert output.notification_sent is True
        assert output.feedback_received is False

    @pytest.mark.asyncio
    async def test_template_name(
        self, worker: PatientHealthAnniversaryWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test template name is health_anniversary_v1."""
        captured_template = None

        async def capture_send(phone: str, template: WhatsAppTemplate) -> str:
            nonlocal captured_template
            captured_template = template
            return "msg-456"

        worker.whatsapp_client.send_template_message = capture_send

        await worker.execute(valid_input)

        assert captured_template.name == "health_anniversary_v1"
        assert captured_template.language == "pt_BR"

    @pytest.mark.asyncio
    async def test_input_validation_model(self, valid_input: dict[str, Any]):
        """Test input validation with Pydantic model."""
        input_model = PatientHealthAnniversaryInput(**valid_input)
        assert input_model.patient_id == "patient-456"
        assert input_model.years_since == 3

        with pytest.raises(ValidationError):
            PatientHealthAnniversaryInput(**{**valid_input, "years_since": 0})

    @pytest.mark.asyncio
    async def test_output_validation_model(self):
        """Test output validation with Pydantic model."""
        output_data = {
            "notification_sent": True,
            "message_id": "msg-789",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "feedback_received": False,
        }
        output_model = PatientHealthAnniversaryOutput(**output_data)
        assert output_model.notification_sent is True
        assert output_model.feedback_received is False

        with pytest.raises(ValidationError):
            PatientHealthAnniversaryOutput(notification_sent=True)
