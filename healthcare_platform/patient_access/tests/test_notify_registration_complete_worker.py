"""Tests for NotifyRegistrationCompleteWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def notifier():
    """Mock notifier protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, whatsapp_client):
    from healthcare_platform.patient_access.workers.notify_registration_complete_worker import NotifyRegistrationCompleteWorker
    # Using notifier protocol that wraps whatsapp_client
    notifier = AsyncMock()
    notifier.whatsapp_client = whatsapp_client
    return NotifyRegistrationCompleteWorker(fhir_client=fhir_client, notifier=notifier)


class TestNotifyRegistrationCompleteWorker:
    @pytest.mark.asyncio
    async def test_happy_path_sends_notification(self, worker, fhir_client, tenant_austa, mock_patient):
        """Test successful registration notification."""
        fhir_client.read.return_value = mock_patient
        worker.notifier.send_whatsapp.return_value = {"message_id": "MSG-123", "status": "sent"}

        result = await worker.execute({
            "patient_id": "patient-123",
            "mrn": "MRN123456"
        })

        assert result["notification_sent"] is True
        assert result["message_id"] == "MSG-123"
        worker.notifier.send_whatsapp.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"patient_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_notification_failure_logs_error(self, worker, fhir_client, tenant_austa, mock_patient):
        """Test that notification failure is handled gracefully."""
        fhir_client.read.return_value = mock_patient
        worker.notifier.send_whatsapp.side_effect = Exception("WhatsApp API unavailable")

        result = await worker.execute({
            "patient_id": "patient-123",
            "mrn": "MRN123456"
        })

        assert result["notification_sent"] is False
        assert "error" in result
