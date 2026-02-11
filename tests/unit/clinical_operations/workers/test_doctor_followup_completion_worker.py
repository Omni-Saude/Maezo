from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.doctor_followup_completion_worker import (
    ClinicalOperationsException,
    DoctorFollowupCompletionInput,
    DoctorFollowupCompletionOutput,
    DoctorFollowupCompletionWorker,
)
from healthcare_platform.shared.domain.exceptions import InvalidTenant
from healthcare_platform.shared.integrations.whatsapp_client import StubWhatsAppClient
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Provide a test tenant context."""
    ctx = TenantContext(tenant_id="test-tenant", region="us-east-1")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker() -> DoctorFollowupCompletionWorker:
    """Create worker instance with stub WhatsApp client."""
    return DoctorFollowupCompletionWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_task_variables() -> dict[str, Any]:
    """Valid task variables for followup completion."""
    return {
        "doctor_id": "doc-123",
        "phone_number": "+5511999998888",
        "pending_patients": [
            {
                "id": "patient-001",
                "name": "Maria Santos",
                "discharge_date": "2024-01-01T10:00:00Z",
                "days_overdue": 7,
                "recommended_followup_type": "cardiology",
            },
            {
                "id": "patient-002",
                "name": "Pedro Costa",
                "discharge_date": "2024-01-05T10:00:00Z",
                "days_overdue": 3,
                "recommended_followup_type": "general",
            },
            {
                "id": "patient-003",
                "name": "Ana Oliveira",
                "discharge_date": "2024-01-08T10:00:00Z",
                "days_overdue": 5,
                "recommended_followup_type": "surgery",
            },
        ],
    }


@pytest.mark.unit
class TestDoctorFollowupCompletionWorker:
    """Test suite for DoctorFollowupCompletionWorker."""

    async def test_execute_success(
        self,
        worker: DoctorFollowupCompletionWorker,
        tenant_ctx: TenantContext,
        valid_task_variables: dict[str, Any],
    ) -> None:
        """Test successful followup pending notification."""
        output = await worker.execute(valid_task_variables)

        assert output.notification_sent is True
        assert output.message_id is not None
        assert output.sent_at is not None
        assert output.total_pending == 3

    async def test_output_fields(
        self,
        worker: DoctorFollowupCompletionWorker,
        tenant_ctx: TenantContext,
        valid_task_variables: dict[str, Any],
    ) -> None:
        """Test all output fields are correctly populated."""
        output = await worker.execute(valid_task_variables)

        # Validate ISO 8601 timestamp
        datetime.fromisoformat(output.sent_at.replace("Z", "+00:00"))

        # Validate to_variables method
        variables = output.to_variables()
        assert variables["notification_sent"] is True
        assert variables["message_id"] is not None
        assert variables["sent_at"] is not None
        assert variables["total_pending"] == 3

    async def test_template_parameters(
        self,
        worker: DoctorFollowupCompletionWorker,
        tenant_ctx: TenantContext,
        valid_task_variables: dict[str, Any],
    ) -> None:
        """Test that WhatsApp template uses correct parameters."""
        mock_client = AsyncMock(spec=StubWhatsAppClient)
        mock_client.send_template = AsyncMock(return_value="msg-uuid-123")
        worker.whatsapp_client = mock_client

        await worker.execute(valid_task_variables)

        # Verify send_template was called
        assert mock_client.send_template.called
        call_args = mock_client.send_template.call_args

        # Verify template structure
        template = call_args.kwargs["template"]
        assert template.name == "followup_pending_v1"
        assert template.language == "pt_BR"

        # Verify body component only (no buttons)
        assert len(template.components) == 1
        body_component = template.components[0]
        assert body_component["type"] == "body"
        assert len(body_component["parameters"]) == 3

        # total_pending = 3
        assert body_component["parameters"][0]["text"] == "3"
        # oldest_overdue = 7 (max from list)
        assert body_component["parameters"][1]["text"] == "7"
        # first_patient_name
        assert body_component["parameters"][2]["text"] == "Maria Santos"

    async def test_whatsapp_failure(
        self,
        worker: DoctorFollowupCompletionWorker,
        tenant_ctx: TenantContext,
        valid_task_variables: dict[str, Any],
    ) -> None:
        """Test handling of WhatsApp send failure."""
        mock_client = AsyncMock(spec=StubWhatsAppClient)
        mock_client.send_template = AsyncMock(
            side_effect=Exception("WhatsApp API error")
        )
        worker.whatsapp_client = mock_client

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert exc_info.value.error_code == "WHATSAPP_SEND_FAILED"
        assert "WhatsApp notification failed" in str(exc_info.value)

    async def test_missing_doctor_id(
        self,
        worker: DoctorFollowupCompletionWorker,
        tenant_ctx: TenantContext,
        valid_task_variables: dict[str, Any],
    ) -> None:
        """Test validation failure when doctor_id is missing."""
        del valid_task_variables["doctor_id"]

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert exc_info.value.error_code == "INVALID_FOLLOWUP_COMPLETION_INPUT"

    async def test_empty_pending_patients(
        self,
        worker: DoctorFollowupCompletionWorker,
        tenant_ctx: TenantContext,
        valid_task_variables: dict[str, Any],
    ) -> None:
        """Test failure when pending_patients list is empty."""
        valid_task_variables["pending_patients"] = []

        with pytest.raises(ClinicalOperationsException) as exc_info:
            await worker.execute(valid_task_variables)

        assert exc_info.value.error_code == "NO_PENDING_PATIENTS"

    async def test_no_tenant_context(
        self,
        worker: DoctorFollowupCompletionWorker,
        valid_task_variables: dict[str, Any],
    ) -> None:
        """Test that worker requires tenant context."""
        clear_tenant()

        with pytest.raises(InvalidTenant):
            await worker.execute(valid_task_variables)

    async def test_single_pending_patient(
        self,
        worker: DoctorFollowupCompletionWorker,
        tenant_ctx: TenantContext,
        valid_task_variables: dict[str, Any],
    ) -> None:
        """Test with single pending patient."""
        valid_task_variables["pending_patients"] = [
            {
                "id": "patient-001",
                "name": "Single Patient",
                "discharge_date": "2024-01-01T10:00:00Z",
                "days_overdue": 10,
                "recommended_followup_type": "cardiology",
            }
        ]

        output = await worker.execute(valid_task_variables)

        assert output.notification_sent is True
        assert output.total_pending == 1

    async def test_oldest_overdue_calculation(
        self,
        worker: DoctorFollowupCompletionWorker,
        tenant_ctx: TenantContext,
        valid_task_variables: dict[str, Any],
    ) -> None:
        """Test that oldest_overdue is correctly calculated as max."""
        mock_client = AsyncMock(spec=StubWhatsAppClient)
        mock_client.send_template = AsyncMock(return_value="msg-uuid-123")
        worker.whatsapp_client = mock_client

        # days_overdue: 7, 3, 5 -> max should be 7
        await worker.execute(valid_task_variables)

        call_args = mock_client.send_template.call_args
        template = call_args.kwargs["template"]
        body_component = template.components[0]

        # Second parameter is oldest_overdue
        assert body_component["parameters"][1]["text"] == "7"

    async def test_input_validation_direct(self) -> None:
        """Test input model validation directly."""
        with pytest.raises(ValidationError):
            DoctorFollowupCompletionInput(
                doctor_id="doc-123",
                phone_number="+5511999998888",
                # Missing required pending_patients
            )

    async def test_output_model_to_variables(self) -> None:
        """Test output model to_variables conversion."""
        output = DoctorFollowupCompletionOutput(
            notification_sent=True,
            message_id="msg-123",
            sent_at="2024-01-15T10:00:00Z",
            total_pending=5,
        )

        variables = output.to_variables()

        assert variables == {
            "notification_sent": True,
            "message_id": "msg-123",
            "sent_at": "2024-01-15T10:00:00Z",
            "total_pending": 5,
        }
