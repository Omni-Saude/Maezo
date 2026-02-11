from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from healthcare_platform.clinical_operations.workers.doctor_cme_reminder_worker import (
    ClinicalOperationsException,
    DoctorCmeReminderInput,
    DoctorCmeReminderOutput,
    DoctorCmeReminderWorker,
)
from healthcare_platform.shared.integrations.whatsapp_client import StubWhatsAppClient
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    return DoctorCmeReminderWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_input() -> dict[str, Any]:
    return {
        "doctor_id": "doc-003",
        "phone_number": "+5511987654321",
        "credits_required": 50,
        "credits_completed": 30,
        "expiration_date": "2026-05-15",
        "days_until_expiration": 94,
        "recommended_courses": ["Curso A", "Curso B"],
    }


@pytest.mark.unit
class TestDoctorCmeReminderWorker:

    @pytest.mark.asyncio
    async def test_execute_success(self, tenant_ctx, worker, valid_input):
        result = await worker.execute(valid_input)

        assert result["notification_sent"] is True
        assert result["message_id"] is not None
        assert result["sent_at"] is not None
        datetime.fromisoformat(result["sent_at"])

    @pytest.mark.asyncio
    async def test_urgency_critical(self, tenant_ctx, worker):
        assert worker._get_urgency_level(7) == "critical"
        assert worker._get_urgency_level(1) == "critical"

    @pytest.mark.asyncio
    async def test_urgency_high(self, tenant_ctx, worker):
        assert worker._get_urgency_level(30) == "high"
        assert worker._get_urgency_level(8) == "high"

    @pytest.mark.asyncio
    async def test_urgency_medium(self, tenant_ctx, worker):
        assert worker._get_urgency_level(60) == "medium"
        assert worker._get_urgency_level(31) == "medium"

    @pytest.mark.asyncio
    async def test_urgency_low(self, tenant_ctx, worker):
        assert worker._get_urgency_level(61) == "low"
        assert worker._get_urgency_level(94) == "low"
        assert worker._get_urgency_level(365) == "low"

    @pytest.mark.asyncio
    async def test_interactive_buttons(self, tenant_ctx, valid_input):
        mock_client = AsyncMock(spec=StubWhatsAppClient)
        mock_client.send_template_message.return_value = "msg-123"
        worker = DoctorCmeReminderWorker(whatsapp_client=mock_client)

        await worker.execute(valid_input)

        call_args = mock_client.send_template_message.call_args
        template = call_args.kwargs["template"]
        components = template.components

        # 1 body + 2 buttons
        assert len(components) == 3

        button1 = components[1]
        assert button1["type"] == "button"
        assert button1["sub_type"] == "quick_reply"
        assert button1["parameters"][0]["text"] == "Ver Cursos"

        button2 = components[2]
        assert button2["type"] == "button"
        assert button2["sub_type"] == "quick_reply"
        assert button2["parameters"][0]["text"] == "Verificar Status"

    @pytest.mark.asyncio
    async def test_missing_doctor_id(self, tenant_ctx, worker, valid_input):
        del valid_input["doctor_id"]

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_input)

    @pytest.mark.asyncio
    async def test_whatsapp_failure(self, tenant_ctx, valid_input):
        mock_client = AsyncMock(spec=StubWhatsAppClient)
        mock_client.send_template_message.side_effect = Exception("WhatsApp API error")
        worker = DoctorCmeReminderWorker(whatsapp_client=mock_client)

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_input)

    @pytest.mark.asyncio
    async def test_output_fields(self, tenant_ctx, worker, valid_input):
        result = await worker.execute(valid_input)

        assert isinstance(result, dict)
        assert "notification_sent" in result
        assert "message_id" in result
        assert "sent_at" in result

    @pytest.mark.asyncio
    async def test_template_name(self, tenant_ctx, valid_input):
        mock_client = AsyncMock(spec=StubWhatsAppClient)
        mock_client.send_template_message.return_value = "msg-123"
        worker = DoctorCmeReminderWorker(whatsapp_client=mock_client)

        await worker.execute(valid_input)

        call_args = mock_client.send_template_message.call_args
        template = call_args.kwargs["template"]
        assert template.name == "cme_reminder_v1"
