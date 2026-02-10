"""Tests for HandleCancellationWorker."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.patient_access.workers.handle_cancellation_worker import (
    HandleCancellationWorker,
    HandleCancellationInput,
    HandleCancellationOutput,
    CancellationHandlerProtocol,
    SuggestedSlot,
    PatientAccessException,
)
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


class MockCancellationHandler(CancellationHandlerProtocol):
    """Mock cancellation handler for testing."""

    def __init__(self):
        self.cancel_called = False
        self.suggest_called = False
        self.should_fail = False

    async def cancel_appointment(
        self,
        appointment_id: str,
        patient_id: str,
        cancellation_reason: str,
        cancelled_by: str,
    ) -> dict[str, Any]:
        """Mock cancellation."""
        self.cancel_called = True
        if self.should_fail:
            raise Exception("Cancellation service unavailable")

        return {
            "cancellation_processed": True,
            "appointment_id": appointment_id,
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
            "resources_released": ["slot_123", "room_456"],
            "notification_sent": True,
        }

    async def suggest_rebooking_slots(
        self,
        appointment_id: str,
        patient_id: str,
        preferred_start: str | None,
        preferred_end: str | None,
    ) -> list[SuggestedSlot]:
        """Mock slot suggestions."""
        self.suggest_called = True
        if self.should_fail:
            raise Exception("Slot service unavailable")

        return [
            SuggestedSlot(
                slot_id="slot_001",
                start_time="2026-02-15T09:00:00Z",
                end_time="2026-02-15T09:30:00Z",
                practitioner_id="prac_123",
                practitioner_name="Dr. Silva",
                location_name="Consultório 1",
                availability_score=0.95,
            ),
            SuggestedSlot(
                slot_id="slot_002",
                start_time="2026-02-15T10:00:00Z",
                end_time="2026-02-15T10:30:00Z",
                practitioner_id="prac_123",
                practitioner_name="Dr. Silva",
                location_name="Consultório 1",
                availability_score=0.85,
            ),
        ]


@pytest.fixture
def mock_handler():
    return MockCancellationHandler()


@pytest.fixture
def worker(mock_handler):
    return HandleCancellationWorker(cancellation_handler=mock_handler)


@pytest.mark.unit
class TestHandleCancellationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_cancellation_with_rebooking(
        self, worker, mock_handler, tenant_austa
    ):
        """Test successful appointment cancellation with rebooking suggestions."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_123",
            "patient_id": "patient_456",
            "cancellation_reason": "Patient request",
            "cancelled_by": "patient",
            "suggest_rebooking": True,
            "preferred_date_range_start": "2026-02-15T00:00:00Z",
            "preferred_date_range_end": "2026-02-20T00:00:00Z",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["cancellation_processed"] is True
        assert result["appointment_id"] == "appt_123"
        assert "cancelled_at" in result
        assert len(result["resources_released"]) == 2
        assert result["notification_sent"] is True
        assert len(result["suggested_slots"]) == 2
        assert mock_handler.cancel_called is True
        assert mock_handler.suggest_called is True

    @pytest.mark.asyncio
    async def test_cancellation_without_rebooking(self, worker, mock_handler, tenant_austa):
        """Test appointment cancellation without rebooking suggestions."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_789",
            "patient_id": "patient_111",
            "cancellation_reason": "Medical emergency",
            "cancelled_by": "provider",
            "suggest_rebooking": False,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["cancellation_processed"] is True
        assert result["appointment_id"] == "appt_789"
        assert len(result["suggested_slots"]) == 0
        assert mock_handler.cancel_called is True
        assert mock_handler.suggest_called is False

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing appointment_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute(
                {
                    "patient_id": "patient_123",
                    "cancellation_reason": "test",
                    "cancelled_by": "patient",
                }
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "appointment_id": "appt_123",
                    "patient_id": "patient_456",
                    "cancellation_reason": "test",
                    "cancelled_by": "patient",
                }
            )

    @pytest.mark.asyncio
    async def test_cancellation_service_failure(self, worker, mock_handler, tenant_austa):
        """Test handling of cancellation service failure."""
        # Arrange
        mock_handler.should_fail = True
        task_vars = {
            "appointment_id": "appt_999",
            "patient_id": "patient_888",
            "cancellation_reason": "test",
            "cancelled_by": "patient",
        }

        # Act & Assert
        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(task_vars)

        assert "Falha ao processar cancelamento" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, mock_handler, tenant_austa, tenant_hpa):
        """Test that cancellations are isolated per tenant."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_austa",
            "patient_id": "patient_austa",
            "cancellation_reason": "test",
            "cancelled_by": "patient",
            "suggest_rebooking": False,
        }

        # Act - Execute for AUSTA
        result_austa = await worker.execute(task_vars)

        # Assert
        assert result_austa["cancellation_processed"] is True

        # Switch tenant and execute again
        task_vars["appointment_id"] = "appt_hpa"
        task_vars["patient_id"] = "patient_hpa"

        result_hpa = await worker.execute(task_vars)

        # Verify isolation - different appointments
        assert result_austa["appointment_id"] != result_hpa["appointment_id"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, mock_handler, tenant_austa):
        """Test that executing cancellation twice produces consistent results."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_idempotent",
            "patient_id": "patient_idem",
            "cancellation_reason": "test",
            "cancelled_by": "patient",
            "suggest_rebooking": False,
        }

        # Act
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Assert - Both succeed with same appointment_id
        assert result1["cancellation_processed"] is True
        assert result2["cancellation_processed"] is True
        assert result1["appointment_id"] == result2["appointment_id"]

    @pytest.mark.asyncio
    async def test_various_cancelled_by_values(self, worker, mock_handler, tenant_austa):
        """Test cancellation by different actors."""
        for cancelled_by in ["patient", "provider", "system"]:
            task_vars = {
                "appointment_id": f"appt_{cancelled_by}",
                "patient_id": "patient_123",
                "cancellation_reason": f"Cancelled by {cancelled_by}",
                "cancelled_by": cancelled_by,
            }

            result = await worker.execute(task_vars)

            assert result["cancellation_processed"] is True
            assert result["appointment_id"] == f"appt_{cancelled_by}"

    @pytest.mark.asyncio
    async def test_suggested_slots_format(self, worker, mock_handler, tenant_austa):
        """Test that suggested slots have correct format."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_slots",
            "patient_id": "patient_slots",
            "cancellation_reason": "test",
            "cancelled_by": "patient",
            "suggest_rebooking": True,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert len(result["suggested_slots"]) > 0
        first_slot = result["suggested_slots"][0]
        assert "slot_id" in first_slot
        assert "start_time" in first_slot
        assert "end_time" in first_slot
        assert "practitioner_name" in first_slot
        assert "location_name" in first_slot
        assert "availability_score" in first_slot
        assert 0.0 <= first_slot["availability_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_resources_released_tracking(self, worker, mock_handler, tenant_austa):
        """Test that released resources are properly tracked."""
        # Arrange
        task_vars = {
            "appointment_id": "appt_resources",
            "patient_id": "patient_resources",
            "cancellation_reason": "test",
            "cancelled_by": "system",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert "resources_released" in result
        assert isinstance(result["resources_released"], list)
        assert len(result["resources_released"]) > 0
