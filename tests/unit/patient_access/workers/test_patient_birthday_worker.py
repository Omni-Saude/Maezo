"""
Unit tests for Patient Birthday Worker.

Tests birthday greeting notification with age-appropriate wellness tips.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from healthcare_platform.patient_access.workers.patient_birthday_worker import (
    PatientAccessException,
    PatientBirthdayInput,
    PatientBirthdayOutput,
    PatientBirthdayWorker,
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
    return PatientBirthdayWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_input() -> dict[str, Any]:
    """Valid input variables for birthday greeting."""
    return {
        "patient_id": "patient-123",
        "phone_number": "+5511987654321",
        "patient_name": "Maria",
        "birth_date": "1985-03-15",
        "age": 41,
        "health_conditions": [],
    }


@pytest.mark.unit
class TestPatientBirthdayWorker:
    """Test suite for PatientBirthdayWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker: PatientBirthdayWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test successful birthday greeting notification."""
        result = await worker.execute(valid_input)

        assert result["notification_sent"] is True
        assert result["message_id"] is not None
        assert result["sent_at"] is not None

        sent_at = datetime.fromisoformat(result["sent_at"])
        assert sent_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_wellness_tip_pediatric(
        self, worker: PatientBirthdayWorker
    ):
        """Test wellness tip for pediatric patients (age < 18)."""
        tip = worker._get_wellness_tip(10, [])
        assert "brincando" in tip

    @pytest.mark.asyncio
    async def test_wellness_tip_adult(
        self, worker: PatientBirthdayWorker
    ):
        """Test wellness tip for adult patients (18-64)."""
        tip = worker._get_wellness_tip(41, [])
        assert "check-ups" in tip

    @pytest.mark.asyncio
    async def test_wellness_tip_senior(
        self, worker: PatientBirthdayWorker
    ):
        """Test wellness tip for senior patients (65+)."""
        tip = worker._get_wellness_tip(70, [])
        assert "ativo" in tip

    @pytest.mark.asyncio
    async def test_wellness_tip_diabetes(
        self, worker: PatientBirthdayWorker
    ):
        """Test wellness tip includes diabetes advice."""
        tip = worker._get_wellness_tip(50, ["diabetes"])
        assert "glicemia" in tip

    @pytest.mark.asyncio
    async def test_wellness_tip_hypertension(
        self, worker: PatientBirthdayWorker
    ):
        """Test wellness tip includes hypertension advice."""
        tip = worker._get_wellness_tip(50, ["hypertension"])
        assert "sal" in tip

    @pytest.mark.asyncio
    async def test_missing_patient_id(
        self, worker: PatientBirthdayWorker, tenant_ctx, valid_input: dict[str, Any]
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
        self, worker: PatientBirthdayWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test error handling when WhatsApp send fails."""

        async def failing_send(phone: str, template: WhatsAppTemplate) -> str:
            raise ConnectionError("WhatsApp API unavailable")

        worker.whatsapp_client.send_template_message = failing_send

        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(valid_input)

        assert exc_info.value.code == "PATIENT_ACCESS_ERROR"
        assert "patient_id" in exc_info.value.details
        assert "error_type" in exc_info.value.details

    @pytest.mark.asyncio
    async def test_output_fields(
        self, worker: PatientBirthdayWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test output contains all required fields."""
        result = await worker.execute(valid_input)

        assert "notification_sent" in result
        assert "message_id" in result
        assert "sent_at" in result

        assert isinstance(result["notification_sent"], bool)
        assert isinstance(result["message_id"], str) or result["message_id"] is None
        assert isinstance(result["sent_at"], str)

        output = PatientBirthdayOutput(**result)
        assert output.notification_sent is True
        assert output.message_id is not None

    @pytest.mark.asyncio
    async def test_template_parameters(
        self, worker: PatientBirthdayWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test WhatsApp template parameters are correctly formatted."""
        captured_template = None

        async def capture_send(phone: str, template: WhatsAppTemplate) -> str:
            nonlocal captured_template
            captured_template = template
            return "msg-123"

        worker.whatsapp_client.send_template_message = capture_send

        await worker.execute(valid_input)

        assert captured_template is not None
        assert captured_template.name == "birthday_greeting_v1"
        assert captured_template.language == "pt_BR"
        assert len(captured_template.components) == 1

        body_params = captured_template.components[0]["parameters"]
        assert len(body_params) == 2
        assert body_params[0]["text"] == "Maria"

    @pytest.mark.asyncio
    async def test_input_validation_model(self, valid_input: dict[str, Any]):
        """Test input validation with Pydantic model."""
        input_model = PatientBirthdayInput(**valid_input)
        assert input_model.patient_id == "patient-123"
        assert input_model.age == 41

        with pytest.raises(ValidationError):
            PatientBirthdayInput(**{**valid_input, "age": -1})

    @pytest.mark.asyncio
    async def test_output_validation_model(self):
        """Test output validation with Pydantic model."""
        output_data = {
            "notification_sent": True,
            "message_id": "msg-789",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        output_model = PatientBirthdayOutput(**output_data)
        assert output_model.notification_sent is True

        with pytest.raises(ValidationError):
            PatientBirthdayOutput(notification_sent=True)
