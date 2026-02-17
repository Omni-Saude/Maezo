"""
Unit tests for Patient Satisfaction Survey Worker.

Tests post-visit NPS survey notification with 1-5 star rating buttons.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from healthcare_platform.patient_access.workers.patient_satisfaction_survey_worker import (
    PatientAccessException,
    PatientSatisfactionSurveyInput,
    PatientSatisfactionSurveyOutput,
    PatientSatisfactionSurveyWorker,
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
    return PatientSatisfactionSurveyWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_input() -> dict[str, Any]:
    """Valid input variables for satisfaction survey."""
    return {
        "patient_id": "patient-321",
        "phone_number": "+5511987654321",
        "visit_date": "2026-02-09",
        "visit_type": "consultation",
        "provider_name": "Dr. Silva",
        "department": "Cardiologia",
    }


@pytest.mark.unit
class TestPatientSatisfactionSurveyWorker:
    """Test suite for PatientSatisfactionSurveyWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker: PatientSatisfactionSurveyWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test successful satisfaction survey notification."""
        result = await worker.execute(valid_input)

        assert result["notification_sent"] is True
        assert result["message_id"] is not None
        assert result["sent_at"] is not None

        sent_at = datetime.fromisoformat(result["sent_at"])
        assert sent_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_nps_category_detractor(
        self, worker: PatientSatisfactionSurveyWorker
    ):
        """Test NPS category for detractors (score 1-2)."""
        assert worker._get_nps_category(1) == "detractor"
        assert worker._get_nps_category(2) == "detractor"

    @pytest.mark.asyncio
    async def test_nps_category_passive(
        self, worker: PatientSatisfactionSurveyWorker
    ):
        """Test NPS category for passives (score 3)."""
        assert worker._get_nps_category(3) == "passive"

    @pytest.mark.asyncio
    async def test_nps_category_promoter(
        self, worker: PatientSatisfactionSurveyWorker
    ):
        """Test NPS category for promoters (score 4-5)."""
        assert worker._get_nps_category(4) == "promoter"
        assert worker._get_nps_category(5) == "promoter"

    @pytest.mark.asyncio
    async def test_followup_action_detractor(
        self, worker: PatientSatisfactionSurveyWorker
    ):
        """Test follow-up action for detractors triggers follow-up call."""
        assert worker._get_followup_action(1) == "trigger_followup_call"
        assert worker._get_followup_action(2) == "trigger_followup_call"

    @pytest.mark.asyncio
    async def test_followup_action_passive(
        self, worker: PatientSatisfactionSurveyWorker
    ):
        """Test follow-up action for passives sends thanks."""
        assert worker._get_followup_action(3) == "send_thanks"

    @pytest.mark.asyncio
    async def test_followup_action_promoter(
        self, worker: PatientSatisfactionSurveyWorker
    ):
        """Test follow-up action for promoters sends referral info."""
        assert worker._get_followup_action(4) == "send_referral_info"
        assert worker._get_followup_action(5) == "send_referral_info"

    @pytest.mark.asyncio
    async def test_missing_patient_id(
        self, worker: PatientSatisfactionSurveyWorker, tenant_ctx, valid_input: dict[str, Any]
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
        self, worker: PatientSatisfactionSurveyWorker, tenant_ctx, valid_input: dict[str, Any]
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
        self, worker: PatientSatisfactionSurveyWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test output contains all required fields with defaults."""
        result = await worker.execute(valid_input)

        assert "notification_sent" in result
        assert "message_id" in result
        assert "sent_at" in result
        assert "nps_score" in result
        assert "feedback" in result
        assert "response_received" in result

        assert result["nps_score"] is None
        assert result["feedback"] is None
        assert result["response_received"] is False

        output = PatientSatisfactionSurveyOutput(**result)
        assert output.notification_sent is True
        assert output.nps_score is None
        assert output.feedback is None

    @pytest.mark.asyncio
    async def test_rating_buttons(
        self, worker: PatientSatisfactionSurveyWorker, tenant_ctx, valid_input: dict[str, Any]
    ):
        """Test 5 star rating buttons in the template."""
        captured_template = None

        async def capture_send(phone: str, template: WhatsAppTemplate) -> str:
            nonlocal captured_template
            captured_template = template
            return "msg-123"

        worker.whatsapp_client.send_template_message = capture_send

        await worker.execute(valid_input)

        assert captured_template is not None
        assert captured_template.name == "satisfaction_survey_v1"
        assert captured_template.language == "pt_BR"

        button_components = [
            c for c in captured_template.components if c["type"] == "button"
        ]
        assert len(button_components) == 5

    @pytest.mark.asyncio
    async def test_input_validation_model(self, valid_input: dict[str, Any]):
        """Test input validation with Pydantic model."""
        input_model = PatientSatisfactionSurveyInput(**valid_input)
        assert input_model.patient_id == "patient-321"
        assert input_model.provider_name == "Dr. Silva"
        assert input_model.department == "Cardiologia"

    @pytest.mark.asyncio
    async def test_output_validation_model(self):
        """Test output validation with Pydantic model."""
        output_data = {
            "notification_sent": True,
            "message_id": "msg-789",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "response_received": False,
            "nps_score": None,
            "feedback": None,
        }
        output_model = PatientSatisfactionSurveyOutput(**output_data)
        assert output_model.notification_sent is True

        with pytest.raises(ValidationError):
            PatientSatisfactionSurveyOutput(notification_sent=True)
