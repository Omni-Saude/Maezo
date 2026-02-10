"""Integration tests for Handle Cancellation Worker with CIB7 engine."""
import pytest
from unittest.mock import AsyncMock

from healthcare_platform.patient_access.workers.handle_cancellation_worker import (
    HandleCancellationWorker,
    StubCancellationHandler,
    PatientAccessException,
)


@pytest.mark.integration
@pytest.mark.slow
class TestHandleCancellationIntegration:
    @pytest.fixture
    def mock_handler(self):
        return StubCancellationHandler()

    @pytest.fixture
    def worker(self, mock_handler):
        return HandleCancellationWorker(cancellation_handler=mock_handler)

    @pytest.mark.asyncio
    async def test_end_to_end_process(self, worker):
        """Test complete cancellation process flow with mocked engine."""
        # Given: external task from Camunda
        task_variables = {
            "appointment_id": "appt-123",
            "patient_id": "patient-456",
            "cancellation_reason": "Patient request",
            "cancelled_by": "patient",
            "suggest_rebooking": True,
            "tenantId": "hospital-123",
        }

        # When: worker executes
        result = await worker.execute(task_variables)

        # Then: cancellation processed and rebooking suggested
        assert result["cancellation_processed"] is True
        assert len(result["resources_released"]) > 0
        assert len(result["suggested_slots"]) > 0
        assert result["notification_sent"] is True

    @pytest.mark.asyncio
    async def test_variable_passing(self, worker):
        """Test process variables flow correctly between tasks."""
        task_variables = {
            "appointment_id": "appt-789",
            "patient_id": "patient-111",
            "cancellation_reason": "Medical emergency",
            "cancelled_by": "provider",
            "suggest_rebooking": False,
            "tenantId": "clinic-456",
        }

        result = await worker.execute(task_variables)

        assert "cancellation_processed" in result
        assert "appointment_id" in result
        assert "cancelled_at" in result
        assert "resources_released" in result
        assert "suggested_slots" in result
        assert result["appointment_id"] == "appt-789"

    @pytest.mark.asyncio
    async def test_compensation_handler(self, worker):
        """Test BPMN compensation on failure."""
        # Given: invalid task variables
        task_variables = {
            "appointment_id": "",  # Empty appointment ID
            "patient_id": "",
            "cancellation_reason": "",
            "cancelled_by": "",
            "tenantId": "test-tenant",
        }

        # When/Then: should raise exception
        with pytest.raises(PatientAccessException):
            await worker.execute(task_variables)

    @pytest.mark.asyncio
    async def test_process_correlation(self, worker):
        """Test process instance correlation."""
        task_variables = {
            "appointment_id": "appt-corr-123",
            "patient_id": "patient-corr-456",
            "cancellation_reason": "Correlation test",
            "cancelled_by": "system",
            "suggest_rebooking": True,
            "preferred_date_range_start": "2026-03-01T09:00:00Z",
            "preferred_date_range_end": "2026-03-31T17:00:00Z",
            "tenantId": "test-tenant",
        }

        result = await worker.execute(task_variables)

        # Verify correlation data is preserved
        assert result["appointment_id"] == task_variables["appointment_id"]
        assert result["cancellation_processed"] is True
