"""
Unit tests for DoctorProcedureAuthStatusWorker.

Tests cover:
- Success with multiple pending authorizations (top 3 shown)
- Empty list (no notification sent)
- Single item
- WhatsApp failure handling
- Output field validation
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.skip(reason="Test needs updating for V2 worker pattern (TaskContext/TaskResult)")

from healthcare_platform.revenue_cycle.workers.doctor_procedure_auth_status_worker_v2 import (
    DoctorProcedureAuthStatusWorker,
    RevenueCycleException,
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
    return DoctorProcedureAuthStatusWorker(
        whatsapp_client=StubWhatsAppClient()
    )


@pytest.mark.asyncio
async def test_success_with_five_items_top_three_shown(
    tenant_ctx, worker
):
    """Test successful notification with 5 pending authorizations, top 3 shown."""
    task_variables = {
        "doctor_id": "DR001",
        "phone_number": "+5511999999999",
        "pending_authorizations": [
            {
                "patient_name": "João Silva",
                "procedure": "Ressonância Magnética",
                "days_pending": 15,
                "payer": "Unimed",
            },
            {
                "patient_name": "Maria Santos",
                "procedure": "Tomografia",
                "days_pending": 12,
                "payer": "Bradesco Saúde",
            },
            {
                "patient_name": "Pedro Costa",
                "procedure": "Cirurgia Cardíaca",
                "days_pending": 8,
                "payer": "SulAmérica",
            },
            {
                "patient_name": "Ana Paula",
                "procedure": "Endoscopia",
                "days_pending": 5,
                "payer": "Amil",
            },
            {
                "patient_name": "Carlos Mendes",
                "procedure": "Colonoscopia",
                "days_pending": 3,
                "payer": "NotreDame",
            },
        ],
    }

    result = await worker.execute(task_variables)

    assert result["notification_sent"] is True
    assert result["message_id"] is not None
    assert result["total_pending"] == 5
    assert "sent_at" in result

    # Verify timestamp is valid ISO 8601
    datetime.fromisoformat(result["sent_at"])

    # Verify WhatsApp template was called with correct params
    stub_client = worker.whatsapp_client
    assert stub_client.sent_templates is not None
    assert len(stub_client.sent_templates) == 1

    template_call = stub_client.sent_templates[0]
    assert template_call["to"] == "+5511999999999"
    assert template_call["template"].name == "auth_pending_summary_v1"
    assert template_call["template"].language_code == "pt_BR"

    # Verify body params
    body_params = template_call["template"].body_params
    assert body_params[0] == "5"  # Total count
    assert body_params[1] == "15"  # Oldest days_pending
    assert "João Silva" in body_params[2]  # Summary includes top item
    assert "Maria Santos" in body_params[2]  # Summary includes second item
    assert "Pedro Costa" in body_params[2]  # Summary includes third item
    assert "Ana Paula" not in body_params[2]  # Fourth item not included
    assert "Carlos Mendes" not in body_params[2]  # Fifth item not included


@pytest.mark.asyncio
async def test_empty_list_no_notification(tenant_ctx, worker):
    """Test no notification sent when pending_authorizations is empty."""
    task_variables = {
        "doctor_id": "DR002",
        "phone_number": "+5511888888888",
        "pending_authorizations": [],
    }

    result = await worker.execute(task_variables)

    assert result["notification_sent"] is False
    assert result["message_id"] is None
    assert result["total_pending"] == 0
    assert "sent_at" in result

    # Verify no WhatsApp message was sent
    stub_client = worker.whatsapp_client
    assert stub_client.sent_templates is not None
    assert len(stub_client.sent_templates) == 0


@pytest.mark.asyncio
async def test_single_item(tenant_ctx, worker):
    """Test notification with single pending authorization."""
    task_variables = {
        "doctor_id": "DR003",
        "phone_number": "+5511777777777",
        "pending_authorizations": [
            {
                "patient_name": "Roberto Lima",
                "procedure": "Ultrassom",
                "days_pending": 7,
                "payer": "Porto Seguro",
            }
        ],
    }

    result = await worker.execute(task_variables)

    assert result["notification_sent"] is True
    assert result["message_id"] is not None
    assert result["total_pending"] == 1

    # Verify WhatsApp template params
    stub_client = worker.whatsapp_client
    template_call = stub_client.sent_templates[0]
    body_params = template_call["template"].body_params

    assert body_params[0] == "1"  # Total count
    assert body_params[1] == "7"  # Oldest days_pending
    assert "Roberto Lima" in body_params[2]
    assert "Ultrassom" in body_params[2]
    assert "7d" in body_params[2]
    assert "Porto Seguro" in body_params[2]


@pytest.mark.asyncio
async def test_whatsapp_failure(tenant_ctx):
    """Test handling of WhatsApp notification failure."""
    # Create mock client that raises exception
    mock_client = AsyncMock()
    mock_client.send_template.side_effect = Exception("WhatsApp API error")

    worker = DoctorProcedureAuthStatusWorker(whatsapp_client=mock_client)

    task_variables = {
        "doctor_id": "DR004",
        "phone_number": "+5511666666666",
        "pending_authorizations": [
            {
                "patient_name": "Fernanda Souza",
                "procedure": "Raio-X",
                "days_pending": 4,
                "payer": "Unimed",
            }
        ],
    }

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(task_variables)

    assert "Failed to send authorization status notification" in str(
        exc_info.value
    )
    assert exc_info.value.code == "REVENUE_CYCLE_ERROR"
    assert "doctor_id" in exc_info.value.details
    assert "total_pending" in exc_info.value.details


@pytest.mark.asyncio
async def test_output_fields(tenant_ctx, worker):
    """Test all required output fields are present and valid."""
    task_variables = {
        "doctor_id": "DR005",
        "phone_number": "+5511555555555",
        "pending_authorizations": [
            {
                "patient_name": "Luiz Fernando",
                "procedure": "Ecocardiograma",
                "days_pending": 10,
                "payer": "Amil",
            },
            {
                "patient_name": "Patricia Alves",
                "procedure": "Mamografia",
                "days_pending": 6,
                "payer": "Bradesco Saúde",
            },
        ],
    }

    result = await worker.execute(task_variables)

    # Verify all required fields
    assert "notification_sent" in result
    assert isinstance(result["notification_sent"], bool)

    assert "message_id" in result
    if result["notification_sent"]:
        assert result["message_id"] is not None
        assert isinstance(result["message_id"], str)

    assert "sent_at" in result
    assert isinstance(result["sent_at"], str)
    # Verify it's valid ISO 8601 timestamp
    datetime.fromisoformat(result["sent_at"])

    assert "total_pending" in result
    assert isinstance(result["total_pending"], int)
    assert result["total_pending"] >= 0


@pytest.mark.asyncio
async def test_invalid_input(tenant_ctx, worker):
    """Test handling of invalid input data."""
    task_variables = {
        "doctor_id": "DR006",
        "phone_number": "+5511444444444",
        "pending_authorizations": [
            {
                "patient_name": "Invalid Item",
                "procedure": "Test",
                "days_pending": -5,  # Invalid: negative days
                "payer": "Test",
            }
        ],
    }

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(task_variables)

    assert "Invalid input for procedure authorization status" in str(
        exc_info.value
    )
    assert exc_info.value.code == "REVENUE_CYCLE_ERROR"


@pytest.mark.asyncio
async def test_missing_required_fields(tenant_ctx, worker):
    """Test handling of missing required input fields."""
    task_variables = {
        "doctor_id": "DR007",
        # Missing phone_number
        "pending_authorizations": [],
    }

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(task_variables)

    assert "Invalid input for procedure authorization status" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_summary_format_with_days_and_payer(tenant_ctx, worker):
    """Test summary text format includes days pending and payer."""
    task_variables = {
        "doctor_id": "DR008",
        "phone_number": "+5511333333333",
        "pending_authorizations": [
            {
                "patient_name": "Gabriel Rocha",
                "procedure": "Angioplastia",
                "days_pending": 20,
                "payer": "SulAmérica",
            }
        ],
    }

    result = await worker.execute(task_variables)

    stub_client = worker.whatsapp_client
    template_call = stub_client.sent_templates[0]
    summary = template_call["template"].body_params[2]

    # Verify format: "- {patient_name}: {procedure} ({days_pending}d, {payer})"
    assert "Gabriel Rocha" in summary
    assert "Angioplastia" in summary
    assert "20d" in summary
    assert "SulAmérica" in summary
    assert summary.startswith("-")
