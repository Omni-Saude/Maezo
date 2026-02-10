"""Tests for HandleCancellationWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.handle_cancellation_worker import HandleCancellationWorker
    return HandleCancellationWorker(fhir_client=fhir_client)


class TestHandleCancellationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_cancels_appointment(self, worker, fhir_client, tenant_austa, mock_appointment):
        """Test successful appointment cancellation."""
        fhir_client.read.return_value = mock_appointment
        cancelled_appointment = {**mock_appointment, "status": "cancelled"}
        fhir_client.update.return_value = cancelled_appointment

        result = await worker.execute({
            "appointment_id": "appointment-789",
            "cancellation_reason": "Patient request"
        })

        assert result["status"] == "cancelled"
        assert result["cancellation_reason"] == "Patient request"
        fhir_client.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
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
    async def test_already_cancelled_raises(self, worker, fhir_client, tenant_austa):
        """Test that cancelling already cancelled appointment raises."""
        cancelled_appointment = {
            "resourceType": "Appointment",
            "id": "appointment-789",
            "status": "cancelled"
        }
        fhir_client.read.return_value = cancelled_appointment

        with pytest.raises(DomainException):
            await worker.execute({
                "appointment_id": "appointment-789",
                "cancellation_reason": "Patient request"
            })
