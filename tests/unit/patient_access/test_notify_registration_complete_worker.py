"""Tests for NotifyRegistrationCompleteWorker."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.patient_access.workers.notify_registration_complete_worker import (
    NotifyRegistrationCompleteWorker,
    RegistrationNotificationInput,
    RegistrationNotificationOutput,
    RegistrationNotifierProtocol,
    PatientAccessException,
)
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


class MockRegistrationNotifier(RegistrationNotifierProtocol):
    """Mock notifier for testing."""

    def __init__(self):
        self.send_called = False
        self.should_fail = False
        self.sent_messages = []

    async def send_registration_notification(
        self,
        phone_number: str,
        patient_name: str,
        mrn: str,
        card_number: str,
        facility_name: str,
        card_url: str | None,
    ) -> tuple[bool, str | None, str | None]:
        """Mock notification sending."""
        self.send_called = True
        self.sent_messages.append({
            "phone_hash": hashlib.sha256(phone_number.encode()).hexdigest(),
            "patient_name": patient_name,
            "mrn": mrn,
        })

        if self.should_fail:
            return False, None, "WhatsApp API unavailable"

        return True, f"wamid_{mrn}", None


@pytest.fixture
def mock_notifier():
    return MockRegistrationNotifier()


@pytest.fixture
def worker(mock_notifier):
    return NotifyRegistrationCompleteWorker(notifier=mock_notifier)


@pytest.mark.unit
class TestNotifyRegistrationCompleteWorker:
    @pytest.mark.asyncio
    async def test_happy_path_notification_sent(self, worker, mock_notifier, tenant_austa):
        """Test successful registration notification."""
        # Arrange
        task_vars = {
            "patient_id": "patient_123",
            "patient_name": "João Silva",
            "phone_number": "+5511987654321",
            "mrn": "MRN-12345",
            "card_number": "CARD-67890",
            "facility_name": "Hospital AUSTA",
            "card_url": "https://portal.austa.health/cards/12345",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["patient_id"] == "patient_123"
        assert result["notification_sent"] is True
        assert result["message_id"] == "wamid_MRN-12345"
        assert result["error_message"] is None
        assert "phone_number_hash" in result
        assert mock_notifier.send_called is True

    @pytest.mark.asyncio
    async def test_notification_without_card_url(self, worker, mock_notifier, tenant_austa):
        """Test notification without optional card_url."""
        # Arrange
        task_vars = {
            "patient_id": "patient_456",
            "patient_name": "Maria Santos",
            "phone_number": "+5511912345678",
            "mrn": "MRN-67890",
            "card_number": "CARD-11111",
            "facility_name": "Hospital HPA",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["notification_sent"] is True
        assert result["patient_id"] == "patient_456"

    @pytest.mark.asyncio
    async def test_phone_number_hashing_lgpd_compliance(
        self, worker, mock_notifier, tenant_austa
    ):
        """Test that phone numbers are hashed for LGPD compliance."""
        # Arrange
        phone = "+5511999887766"
        task_vars = {
            "patient_id": "patient_lgpd",
            "patient_name": "Ana Costa",
            "phone_number": phone,
            "mrn": "MRN-LGPD",
            "card_number": "CARD-LGPD",
            "facility_name": "Hospital Test",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert - Phone hash matches expected
        expected_hash = hashlib.sha256(phone.encode()).hexdigest()
        assert result["phone_number_hash"] == expected_hash
        # Original phone should NOT be in result
        assert phone not in str(result)

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing patient_name raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute(
                {
                    "patient_id": "patient_123",
                    "phone_number": "+5511987654321",
                    "mrn": "MRN-123",
                    "card_number": "CARD-123",
                }
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "patient_id": "patient_123",
                    "patient_name": "Test",
                    "phone_number": "+5511987654321",
                    "mrn": "MRN-123",
                    "card_number": "CARD-123",
                    "facility_name": "Hospital",
                }
            )

    @pytest.mark.asyncio
    async def test_whatsapp_service_failure(self, worker, mock_notifier, tenant_austa):
        """Test handling of WhatsApp service failure."""
        # Arrange
        mock_notifier.should_fail = True
        task_vars = {
            "patient_id": "patient_fail",
            "patient_name": "Pedro Oliveira",
            "phone_number": "+5511988776655",
            "mrn": "MRN-FAIL",
            "card_number": "CARD-FAIL",
            "facility_name": "Hospital Test",
        }

        # Act & Assert
        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(task_vars)

        assert "Falha ao enviar notificação" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(
        self, worker, mock_notifier, tenant_austa, tenant_hpa
    ):
        """Test that notifications are isolated per tenant."""
        # Arrange
        task_vars_austa = {
            "patient_id": "patient_austa",
            "patient_name": "Paciente AUSTA",
            "phone_number": "+5511111111111",
            "mrn": "MRN-AUSTA",
            "card_number": "CARD-AUSTA",
            "facility_name": "Hospital AUSTA",
        }

        task_vars_hpa = {
            "patient_id": "patient_hpa",
            "patient_name": "Paciente HPA",
            "phone_number": "+5522222222222",
            "mrn": "MRN-HPA",
            "card_number": "CARD-HPA",
            "facility_name": "Hospital HPA",
        }

        # Act
        result_austa = await worker.execute(task_vars_austa)
        result_hpa = await worker.execute(task_vars_hpa)

        # Assert - Different patients, different hashes
        assert result_austa["phone_number_hash"] != result_hpa["phone_number_hash"]
        assert len(mock_notifier.sent_messages) == 2

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, mock_notifier, tenant_austa):
        """Test that sending notification twice is safe."""
        # Arrange
        task_vars = {
            "patient_id": "patient_idem",
            "patient_name": "Idempotent Test",
            "phone_number": "+5511333333333",
            "mrn": "MRN-IDEM",
            "card_number": "CARD-IDEM",
            "facility_name": "Hospital Test",
        }

        # Act
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Assert - Both succeed
        assert result1["notification_sent"] is True
        assert result2["notification_sent"] is True
        assert result1["phone_number_hash"] == result2["phone_number_hash"]

    @pytest.mark.asyncio
    async def test_special_characters_in_name(self, worker, mock_notifier, tenant_austa):
        """Test handling of special characters in patient name."""
        # Arrange
        task_vars = {
            "patient_id": "patient_special",
            "patient_name": "José André Müller-Peña",
            "phone_number": "+5511444444444",
            "mrn": "MRN-SPECIAL",
            "card_number": "CARD-SPECIAL",
            "facility_name": "Hospital São José",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["notification_sent"] is True

    @pytest.mark.asyncio
    async def test_timestamp_is_set(self, worker, mock_notifier, tenant_austa):
        """Test that sent_timestamp is properly set."""
        # Arrange
        task_vars = {
            "patient_id": "patient_timestamp",
            "patient_name": "Timestamp Test",
            "phone_number": "+5511555555555",
            "mrn": "MRN-TS",
            "card_number": "CARD-TS",
            "facility_name": "Hospital Test",
        }

        # Act
        before = datetime.utcnow()
        result = await worker.execute(task_vars)
        after = datetime.utcnow()

        # Assert - Timestamp is between before and after
        sent_time = datetime.fromisoformat(result["sent_timestamp"].replace("Z", "+00:00"))
        assert before <= sent_time <= after
