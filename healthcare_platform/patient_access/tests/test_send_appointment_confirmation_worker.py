"""Tests for SendAppointmentConfirmationWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def confirmation_sender():
    """Mock confirmation sender protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, whatsapp_client):
    from healthcare_platform.patient_access.workers.send_appointment_confirmation_worker import SendAppointmentConfirmationWorker
    # Using confirmation_sender protocol that wraps whatsapp_client
    confirmation_sender = AsyncMock()
    confirmation_sender.whatsapp_client = whatsapp_client
    return SendAppointmentConfirmationWorker(fhir_client=fhir_client, confirmation_sender=confirmation_sender)


class TestSendAppointmentConfirmationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_sends_confirmation(self, worker, fhir_client, tenant_hospital_a, mock_appointment, mock_patient):
        """Test successful appointment confirmation."""
        fhir_client.read.side_effect = [mock_appointment, mock_patient]
        worker.confirmation_sender.send_whatsapp.return_value = {
            "message_id": "MSG-456",
            "status": "sent"
        }

        result = await worker.execute({
            "appointment_id": "appointment-789"
        })

        assert result["confirmation_sent"] is True
        assert result["message_id"] == "MSG-456"
        worker.confirmation_sender.send_whatsapp.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_hospital_a):
        """Test that missing appointment_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"appointment_id": "appointment-789"})

    @pytest.mark.asyncio
    async def test_confirmation_failure_logs_error(self, worker, fhir_client, tenant_hospital_a, mock_appointment, mock_patient):
        """Test that confirmation failure is handled gracefully."""
        fhir_client.read.side_effect = [mock_appointment, mock_patient]
        worker.confirmation_sender.send_whatsapp.side_effect = Exception("WhatsApp API unavailable")

        result = await worker.execute({
            "appointment_id": "appointment-789"
        })

        assert result["confirmation_sent"] is False
        assert "error" in result
