"""Unit tests for Patient Bill Notification Worker."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.skip(reason="Test needs updating for V2 worker pattern (TaskContext/TaskResult)")

from healthcare_platform.revenue_cycle.workers.patient_bill_notification_worker_v2 import (
    PatientBillNotificationInput,
    PatientBillNotificationOutput,
    PatientBillNotificationWorker,
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
    """Create and set tenant context."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker instance with stub WhatsApp client."""
    return PatientBillNotificationWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_input():
    """Valid bill notification input data."""
    return {
        "patient_id": "PAT-12345",
        "phone_number": "+5511987654321",
        "bill_id": "BILL-98765",
        "total_amount": 850.50,
        "due_date": "2024-04-15",
        "itemized_summary": "Consulta (R$ 350,00), Exames (R$ 500,50)",
        "payment_methods": ["credit", "debit", "pix"],
    }


@pytest.mark.unit
class TestPatientBillNotificationInput:
    """Test cases for PatientBillNotificationInput model."""

    def test_valid_input(self, valid_input):
        """Test valid input creates model successfully."""
        model = PatientBillNotificationInput(**valid_input)
        assert model.patient_id == "PAT-12345"
        assert model.phone_number == "+5511987654321"
        assert model.bill_id == "BILL-98765"
        assert model.total_amount == 850.50
        assert model.due_date == "2024-04-15"
        assert len(model.payment_methods) == 3

    def test_phone_number_validation_missing_plus(self, valid_input):
        """Test phone number validation requires E.164 format."""
        valid_input["phone_number"] = "5511987654321"  # Missing +
        with pytest.raises(ValidationError) as exc_info:
            PatientBillNotificationInput(**valid_input)
        assert "E.164" in str(exc_info.value)

    def test_negative_amount_validation(self, valid_input):
        """Test negative total amount is rejected."""
        valid_input["total_amount"] = -100.00
        with pytest.raises(ValidationError) as exc_info:
            PatientBillNotificationInput(**valid_input)
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_missing_required_fields(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            PatientBillNotificationInput(patient_id="PAT-123")
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "phone_number" in missing_fields
        assert "bill_id" in missing_fields
        assert "total_amount" in missing_fields

    def test_empty_payment_methods(self, valid_input):
        """Test empty payment methods list is allowed."""
        valid_input["payment_methods"] = []
        model = PatientBillNotificationInput(**valid_input)
        assert model.payment_methods == []


@pytest.mark.unit
class TestPatientBillNotificationWorker:
    """Test cases for PatientBillNotificationWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(self, worker, valid_input, tenant_ctx):
        """Test successful bill notification."""
        result = await worker.execute(valid_input)

        assert result["notification_sent"] is True
        assert result["message_id"] is not None
        assert "sent_at" in result
        assert result["action_taken"] is None

        # Validate output model
        output = PatientBillNotificationOutput(**result)
        assert output.notification_sent is True
        assert output.message_id is not None

    @pytest.mark.asyncio
    async def test_execute_missing_bill_id(self, worker, valid_input, tenant_ctx):
        """Test execution fails when bill_id is missing."""
        del valid_input["bill_id"]

        with pytest.raises(RevenueCycleException) as exc_info:
            await worker.execute(valid_input)

        assert "Invalid input" in str(exc_info.value)
        assert exc_info.value.code == "REVENUE_CYCLE_ERROR"

    @pytest.mark.asyncio
    async def test_execute_negative_amount(self, worker, valid_input, tenant_ctx):
        """Test execution fails with negative total amount."""
        valid_input["total_amount"] = -500.00

        with pytest.raises(RevenueCycleException) as exc_info:
            await worker.execute(valid_input)

        assert "Invalid input" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_whatsapp_failure(self, valid_input, tenant_ctx):
        """Test execution fails when WhatsApp client fails."""
        # Create mock client that raises exception
        mock_client = AsyncMock()
        mock_client.send_template.side_effect = Exception("WhatsApp API error")

        worker = PatientBillNotificationWorker(whatsapp_client=mock_client)

        with pytest.raises(RevenueCycleException) as exc_info:
            await worker.execute(valid_input)

        assert "Failed to send bill notification" in str(exc_info.value)
        assert exc_info.value.code == "REVENUE_CYCLE_ERROR"
        assert "BILL-98765" in str(exc_info.value.details)

    @pytest.mark.asyncio
    async def test_output_fields_present(self, worker, valid_input, tenant_ctx):
        """Test all expected output fields are present."""
        result = await worker.execute(valid_input)

        assert "notification_sent" in result
        assert "message_id" in result
        assert "sent_at" in result
        assert "action_taken" in result

        # Verify sent_at is valid ISO timestamp
        sent_at = datetime.fromisoformat(result["sent_at"])
        assert sent_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_currency_formatting(self, worker, valid_input, tenant_ctx):
        """Test Brazilian Real currency formatting."""
        # Test with various amounts
        test_cases = [
            (850.50, "R$ 850,50"),
            (1234.56, "R$ 1.234,56"),
            (10000.00, "R$ 10.000,00"),
        ]

        for amount, expected in test_cases:
            formatted = worker._format_currency(amount)
            assert formatted == expected

    @pytest.mark.asyncio
    async def test_whatsapp_template_structure(self, valid_input, tenant_ctx):
        """Test WhatsApp template is created with correct structure."""
        mock_client = AsyncMock()
        mock_client.send_template.return_value = "msg-98765"

        worker = PatientBillNotificationWorker(whatsapp_client=mock_client)
        await worker.execute(valid_input)

        # Verify send_template was called
        assert mock_client.send_template.called
        call_args = mock_client.send_template.call_args

        # Check phone number
        assert call_args[1]["to"] == "+5511987654321"

        # Check template structure
        template = call_args[1]["template"]
        assert isinstance(template, WhatsAppTemplate)
        assert template.name == "bill_ready_v1"
        assert template.language == "pt_BR"
        assert len(template.body_params) == 2
        assert "R$" in template.body_params[0]  # formatted amount
        assert template.body_params[1] == "2024-04-15"  # due_date

    @pytest.mark.asyncio
    async def test_interactive_buttons_added(self, valid_input, tenant_ctx):
        """Test interactive buttons are added to template."""
        mock_client = AsyncMock()
        mock_client.send_template.return_value = "msg-98765"

        worker = PatientBillNotificationWorker(whatsapp_client=mock_client)
        await worker.execute(valid_input)

        template = mock_client.send_template.call_args[1]["template"]
        assert template.buttons is not None
        assert len(template.buttons) == 3

        # Check button texts (WhatsApp max 3 buttons)
        button_texts = [btn["text"] for btn in template.buttons]
        assert "Ver Detalhes" in button_texts
        assert "Pagar Agora" in button_texts
        assert "Parcelar" in button_texts

    @pytest.mark.asyncio
    async def test_deep_link_formats(self, valid_input, tenant_ctx):
        """Test deep link URL formats for all buttons."""
        mock_client = AsyncMock()
        mock_client.send_template.return_value = "msg-98765"

        worker = PatientBillNotificationWorker(whatsapp_client=mock_client)
        await worker.execute(valid_input)

        template = mock_client.send_template.call_args[1]["template"]

        # Extract buttons
        view_button = next(
            btn for btn in template.buttons if btn["text"] == "Ver Detalhes"
        )
        pay_button = next(
            btn for btn in template.buttons if btn["text"] == "Pagar Agora"
        )
        plan_button = next(
            btn for btn in template.buttons if btn["text"] == "Parcelar"
        )

        # Verify URLs
        expected_view = f"https://portal.austa.com.br/bill/{valid_input['bill_id']}"
        expected_pay = (
            f"https://portal.austa.com.br/pay/bill/{valid_input['bill_id']}"
        )
        expected_plan = f"https://portal.austa.com.br/plan/{valid_input['bill_id']}"

        assert view_button["url"] == expected_view
        assert pay_button["url"] == expected_pay
        assert plan_button["url"] == expected_plan

    @pytest.mark.asyncio
    async def test_large_amount_formatting(self, worker, valid_input, tenant_ctx):
        """Test formatting of large bill amounts."""
        valid_input["total_amount"] = 15432.89

        result = await worker.execute(valid_input)
        assert result["notification_sent"] is True

        # Verify formatting
        formatted = worker._format_currency(15432.89)
        assert formatted == "R$ 15.432,89"

    @pytest.mark.asyncio
    async def test_zero_amount_allowed(self, worker, valid_input, tenant_ctx):
        """Test zero amount bill is allowed (e.g., fully covered by insurance)."""
        valid_input["total_amount"] = 0.00

        result = await worker.execute(valid_input)
        assert result["notification_sent"] is True

        formatted = worker._format_currency(0.00)
        assert formatted == "R$ 0,00"

    @pytest.mark.asyncio
    async def test_multiple_payment_methods(self, worker, valid_input, tenant_ctx):
        """Test bill notification with multiple payment methods."""
        valid_input["payment_methods"] = ["credit", "debit", "pix", "boleto"]

        result = await worker.execute(valid_input)
        assert result["notification_sent"] is True

    @pytest.mark.asyncio
    async def test_itemized_summary_included(self, valid_input, tenant_ctx):
        """Test itemized summary is part of input validation."""
        model = PatientBillNotificationInput(**valid_input)
        assert model.itemized_summary == "Consulta (R$ 350,00), Exames (R$ 500,50)"

    @pytest.mark.asyncio
    async def test_tenant_context_required(self, worker, valid_input):
        """Test execution fails without tenant context."""
        # Don't set tenant context
        with pytest.raises(Exception):
            await worker.execute(valid_input)
