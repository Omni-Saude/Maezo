"""Tests for SendReminderNotificationWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import DomainException


@pytest.fixture
def reminder_sender():
    """Mock reminder sender protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, whatsapp_client):
    from platform.patient_access.workers.send_reminder_notification_worker import SendReminderNotificationWorker
    # Using reminder_sender protocol that wraps whatsapp_client
    reminder_sender = AsyncMock()
    reminder_sender.whatsapp_client = whatsapp_client
    return SendReminderNotificationWorker(fhir_client=fhir_client, reminder_sender=reminder_sender)


class TestSendReminderNotificationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_sends_reminder(self, worker, fhir_client, tenant_austa, mock_appointment, mock_patient):
        """Test successful reminder notification."""
        fhir_client.read.side_effect = [mock_appointment, mock_patient]
        worker.reminder_sender.send_whatsapp.return_value = {
            "message_id": "MSG-789",
            "status": "sent"
        }

        result = await worker.execute({
            "appointment_id": "appointment-789",
            "reminder_type": "24h_before"
        })

        assert result["reminder_sent"] is True
        assert result["message_id"] == "MSG-789"
        worker.reminder_sender.send_whatsapp.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing appointment_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"appointment_id": "appointment-789"})

    @pytest.mark.asyncio
    async def test_multiple_reminder_types(self, worker, fhir_client, tenant_austa, mock_appointment, mock_patient):
        """Test different reminder types."""
        fhir_client.read.side_effect = [mock_appointment, mock_patient]
        worker.reminder_sender.send_whatsapp.return_value = {
            "message_id": "MSG-789",
            "status": "sent"
        }

        for reminder_type in ["24h_before", "1h_before", "day_before"]:
            result = await worker.execute({
                "appointment_id": "appointment-789",
                "reminder_type": reminder_type
            })
            assert result["reminder_sent"] is True
