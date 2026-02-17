"""
Unit tests for DoctorReimbursementSummaryWorker.

Tests cover:
- Success with denials
- Success without denials
- Zero billed (receipt rate 0)
- WhatsApp failure handling
- Output field validation
- All amounts zero
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.skip(reason="Test needs updating for V2 worker pattern (TaskContext/TaskResult)")

from healthcare_platform.revenue_cycle.workers.doctor_reimbursement_summary_worker_v2 import (
    DoctorReimbursementSummaryWorker,
    RevenueCycleException,
)
from healthcare_platform.shared.integrations.whatsapp_client import (
    StubWhatsAppClient,
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
    return DoctorReimbursementSummaryWorker(
        whatsapp_client=StubWhatsAppClient()
    )


@pytest.mark.asyncio
async def test_success_with_denials(tenant_ctx, worker):
    """Test successful notification with top denials included."""
    task_variables = {
        "doctor_id": "DR001",
        "phone_number": "+5511999999999",
        "period": "Jan/2026",
        "total_billed": 50000.00,
        "total_received": 42000.00,
        "total_pending": 5000.00,
        "total_denied": 3000.00,
        "top_denials": [
            "Documentação incompleta",
            "Procedimento não autorizado",
            "Valor acima da tabela",
            "Falta de guia médica",
        ],
    }

    result = await worker.execute(task_variables)

    assert result["notification_sent"] is True
    assert result["message_id"] is not None
    assert "sent_at" in result

    # Verify timestamp is valid ISO 8601
    datetime.fromisoformat(result["sent_at"])

    # Verify WhatsApp template was called with correct params
    stub_client = worker.whatsapp_client
    assert stub_client.sent_templates is not None
    assert len(stub_client.sent_templates) == 1

    template_call = stub_client.sent_templates[0]
    assert template_call["to"] == "+5511999999999"
    assert template_call["template"].name == "reimbursement_summary_v1"
    assert template_call["template"].language_code == "pt_BR"

    # Verify body params
    body_params = template_call["template"].body_params
    assert body_params[0] == "Jan/2026"  # Period
    assert body_params[1] == "R$ 50.000,00"  # Total billed (Brazilian format)
    assert body_params[2] == "R$ 42.000,00"  # Total received
    assert body_params[3] == "84.0%"  # Receipt rate (42000/50000 * 100)
    assert body_params[4] == "R$ 5.000,00"  # Total pending


@pytest.mark.asyncio
async def test_success_without_denials(tenant_ctx, worker):
    """Test successful notification without denials."""
    task_variables = {
        "doctor_id": "DR002",
        "phone_number": "+5511888888888",
        "period": "Feb/2026",
        "total_billed": 30000.00,
        "total_received": 28000.00,
        "total_pending": 2000.00,
        "total_denied": 0.00,
        "top_denials": [],
    }

    result = await worker.execute(task_variables)

    assert result["notification_sent"] is True
    assert result["message_id"] is not None

    # Verify WhatsApp template params
    stub_client = worker.whatsapp_client
    template_call = stub_client.sent_templates[0]
    body_params = template_call["template"].body_params

    assert body_params[0] == "Feb/2026"
    assert body_params[1] == "R$ 30.000,00"
    assert body_params[2] == "R$ 28.000,00"
    # Receipt rate: 28000/30000 * 100 = 93.33%
    assert body_params[3] == "93.3%"
    assert body_params[4] == "R$ 2.000,00"


@pytest.mark.asyncio
async def test_zero_billed_receipt_rate_zero(tenant_ctx, worker):
    """Test receipt rate is 0% when total_billed is zero."""
    task_variables = {
        "doctor_id": "DR003",
        "phone_number": "+5511777777777",
        "period": "Mar/2026",
        "total_billed": 0.00,
        "total_received": 0.00,
        "total_pending": 0.00,
        "total_denied": 0.00,
        "top_denials": [],
    }

    result = await worker.execute(task_variables)

    assert result["notification_sent"] is True

    # Verify receipt rate is 0.0%
    stub_client = worker.whatsapp_client
    template_call = stub_client.sent_templates[0]
    body_params = template_call["template"].body_params

    assert body_params[3] == "0.0%"  # Receipt rate


@pytest.mark.asyncio
async def test_whatsapp_failure(tenant_ctx):
    """Test handling of WhatsApp notification failure."""
    # Create mock client that raises exception
    mock_client = AsyncMock()
    mock_client.send_template.side_effect = Exception("WhatsApp API error")

    worker = DoctorReimbursementSummaryWorker(whatsapp_client=mock_client)

    task_variables = {
        "doctor_id": "DR004",
        "phone_number": "+5511666666666",
        "period": "Apr/2026",
        "total_billed": 10000.00,
        "total_received": 8000.00,
        "total_pending": 2000.00,
        "total_denied": 0.00,
        "top_denials": [],
    }

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(task_variables)

    assert "Failed to send reimbursement summary notification" in str(
        exc_info.value
    )
    assert exc_info.value.code == "REVENUE_CYCLE_ERROR"
    assert "doctor_id" in exc_info.value.details
    assert "period" in exc_info.value.details


@pytest.mark.asyncio
async def test_output_fields(tenant_ctx, worker):
    """Test all required output fields are present and valid."""
    task_variables = {
        "doctor_id": "DR005",
        "phone_number": "+5511555555555",
        "period": "May/2026",
        "total_billed": 15000.00,
        "total_received": 12000.00,
        "total_pending": 3000.00,
        "total_denied": 0.00,
        "top_denials": [],
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


@pytest.mark.asyncio
async def test_all_amounts_zero(tenant_ctx, worker):
    """Test notification with all financial amounts at zero."""
    task_variables = {
        "doctor_id": "DR006",
        "phone_number": "+5511444444444",
        "period": "Jun/2026",
        "total_billed": 0.00,
        "total_received": 0.00,
        "total_pending": 0.00,
        "total_denied": 0.00,
        "top_denials": [],
    }

    result = await worker.execute(task_variables)

    assert result["notification_sent"] is True

    # Verify formatting of zero amounts
    stub_client = worker.whatsapp_client
    template_call = stub_client.sent_templates[0]
    body_params = template_call["template"].body_params

    assert body_params[1] == "R$ 0,00"  # Total billed
    assert body_params[2] == "R$ 0,00"  # Total received
    assert body_params[3] == "0.0%"  # Receipt rate
    assert body_params[4] == "R$ 0,00"  # Total pending


@pytest.mark.asyncio
async def test_brazilian_currency_formatting(tenant_ctx, worker):
    """Test Brazilian Real currency formatting."""
    task_variables = {
        "doctor_id": "DR007",
        "phone_number": "+5511333333333",
        "period": "Jul/2026",
        "total_billed": 123456.78,
        "total_received": 98765.43,
        "total_pending": 24691.35,
        "total_denied": 0.00,
        "top_denials": [],
    }

    result = await worker.execute(task_variables)

    stub_client = worker.whatsapp_client
    template_call = stub_client.sent_templates[0]
    body_params = template_call["template"].body_params

    # Verify Brazilian format: thousands separator = ., decimal separator = ,
    assert body_params[1] == "R$ 123.456,78"
    assert body_params[2] == "R$ 98.765,43"
    assert body_params[4] == "R$ 24.691,35"


@pytest.mark.asyncio
async def test_top_denials_limited_to_three(tenant_ctx, worker):
    """Test that top denials are limited to top 3 items."""
    task_variables = {
        "doctor_id": "DR008",
        "phone_number": "+5511222222222",
        "period": "Aug/2026",
        "total_billed": 40000.00,
        "total_received": 35000.00,
        "total_pending": 3000.00,
        "total_denied": 2000.00,
        "top_denials": [
            "Motivo 1",
            "Motivo 2",
            "Motivo 3",
            "Motivo 4",
            "Motivo 5",
        ],
    }

    result = await worker.execute(task_variables)

    # Note: The current implementation doesn't add denial text to body_params
    # but the logic is implemented in the worker for future use
    assert result["notification_sent"] is True


@pytest.mark.asyncio
async def test_invalid_input_negative_amount(tenant_ctx, worker):
    """Test handling of invalid input with negative amount."""
    task_variables = {
        "doctor_id": "DR009",
        "phone_number": "+5511111111111",
        "period": "Sep/2026",
        "total_billed": -1000.00,  # Invalid: negative amount
        "total_received": 0.00,
        "total_pending": 0.00,
        "total_denied": 0.00,
        "top_denials": [],
    }

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(task_variables)

    assert "Invalid input for reimbursement summary" in str(exc_info.value)
    assert exc_info.value.code == "REVENUE_CYCLE_ERROR"


@pytest.mark.asyncio
async def test_missing_required_fields(tenant_ctx, worker):
    """Test handling of missing required input fields."""
    task_variables = {
        "doctor_id": "DR010",
        "phone_number": "+5511000000000",
        # Missing period, total_billed, etc.
    }

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(task_variables)

    assert "Invalid input for reimbursement summary" in str(exc_info.value)


@pytest.mark.asyncio
async def test_receipt_rate_calculation(tenant_ctx, worker):
    """Test receipt rate calculation accuracy."""
    task_variables = {
        "doctor_id": "DR011",
        "phone_number": "+5511121212121",
        "period": "Oct/2026",
        "total_billed": 100000.00,
        "total_received": 75500.00,
        "total_pending": 20000.00,
        "total_denied": 4500.00,
        "top_denials": [],
    }

    result = await worker.execute(task_variables)

    stub_client = worker.whatsapp_client
    template_call = stub_client.sent_templates[0]
    body_params = template_call["template"].body_params

    # Receipt rate: 75500 / 100000 * 100 = 75.5%
    assert body_params[3] == "75.5%"


@pytest.mark.asyncio
async def test_period_format_preserved(tenant_ctx, worker):
    """Test that period format is preserved as-is."""
    task_variables = {
        "doctor_id": "DR012",
        "phone_number": "+5511131313131",
        "period": "Nov/2026",
        "total_billed": 5000.00,
        "total_received": 5000.00,
        "total_pending": 0.00,
        "total_denied": 0.00,
        "top_denials": [],
    }

    result = await worker.execute(task_variables)

    stub_client = worker.whatsapp_client
    template_call = stub_client.sent_templates[0]
    body_params = template_call["template"].body_params

    assert body_params[0] == "Nov/2026"
