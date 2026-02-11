"""Unit tests for Patient Copay Estimate Worker."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from healthcare_platform.revenue_cycle.workers.patient_copay_estimate_worker import (
    PatientCopayEstimateInput,
    PatientCopayEstimateOutput,
    PatientCopayEstimateWorker,
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
    """Create and set tenant context."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker instance with stub WhatsApp client."""
    return PatientCopayEstimateWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_input():
    """Valid copay estimate input data."""
    return {
        "patient_id": "PAT-12345",
        "phone_number": "+5511987654321",
        "appointment_id": "APPT-67890",
        "procedure_codes": ["99213", "80053"],
        "estimated_copay": 150.00,
        "insurance_coverage": 80.0,
        "appointment_date": "2024-03-15",
    }


@pytest.mark.unit
class TestPatientCopayEstimateInput:
    """Test cases for PatientCopayEstimateInput model."""

    def test_valid_input(self, valid_input):
        """Test valid input creates model successfully."""
        model = PatientCopayEstimateInput(**valid_input)
        assert model.patient_id == "PAT-12345"
        assert model.phone_number == "+5511987654321"
        assert model.estimated_copay == 150.00
        assert model.insurance_coverage == 80.0

    def test_phone_number_validation_missing_plus(self, valid_input):
        """Test phone number validation requires E.164 format."""
        valid_input["phone_number"] = "5511987654321"  # Missing +
        with pytest.raises(ValidationError) as exc_info:
            PatientCopayEstimateInput(**valid_input)
        assert "E.164" in str(exc_info.value)

    def test_negative_copay_validation(self, valid_input):
        """Test negative copay amount is rejected."""
        valid_input["estimated_copay"] = -50.00
        with pytest.raises(ValidationError) as exc_info:
            PatientCopayEstimateInput(**valid_input)
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_coverage_above_100_validation(self, valid_input):
        """Test insurance coverage above 100% is rejected."""
        valid_input["insurance_coverage"] = 105.0
        with pytest.raises(ValidationError) as exc_info:
            PatientCopayEstimateInput(**valid_input)
        assert "less than or equal to 100" in str(exc_info.value).lower()

    def test_coverage_below_0_validation(self, valid_input):
        """Test insurance coverage below 0% is rejected."""
        valid_input["insurance_coverage"] = -10.0
        with pytest.raises(ValidationError) as exc_info:
            PatientCopayEstimateInput(**valid_input)
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_missing_required_fields(self):
        """Test missing required fields raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            PatientCopayEstimateInput(patient_id="PAT-123")
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "phone_number" in missing_fields
        assert "appointment_id" in missing_fields


@pytest.mark.unit
class TestPatientCopayEstimateWorker:
    """Test cases for PatientCopayEstimateWorker."""

    @pytest.mark.asyncio
    async def test_execute_success(self, worker, valid_input, tenant_ctx):
        """Test successful copay estimate notification."""
        result = await worker.execute(valid_input)

        assert result["notification_sent"] is True
        assert result["message_id"] is not None
        assert "sent_at" in result
        assert result["payment_action"] is None

        # Validate output model
        output = PatientCopayEstimateOutput(**result)
        assert output.notification_sent is True
        assert output.message_id is not None

    @pytest.mark.asyncio
    async def test_execute_missing_patient_id(self, worker, valid_input, tenant_ctx):
        """Test execution fails when patient_id is missing."""
        del valid_input["patient_id"]

        with pytest.raises(RevenueCycleException) as exc_info:
            await worker.execute(valid_input)

        assert "Invalid input" in str(exc_info.value)
        assert exc_info.value.code == "REVENUE_CYCLE_ERROR"

    @pytest.mark.asyncio
    async def test_execute_negative_copay(self, worker, valid_input, tenant_ctx):
        """Test execution fails with negative copay amount."""
        valid_input["estimated_copay"] = -100.00

        with pytest.raises(RevenueCycleException) as exc_info:
            await worker.execute(valid_input)

        assert "Invalid input" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_coverage_above_100(self, worker, valid_input, tenant_ctx):
        """Test execution fails with coverage above 100%."""
        valid_input["insurance_coverage"] = 150.0

        with pytest.raises(RevenueCycleException) as exc_info:
            await worker.execute(valid_input)

        assert "Invalid input" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_whatsapp_failure(self, valid_input, tenant_ctx):
        """Test execution fails when WhatsApp client fails."""
        # Create mock client that raises exception
        mock_client = AsyncMock()
        mock_client.send_template.side_effect = Exception("WhatsApp API error")

        worker = PatientCopayEstimateWorker(whatsapp_client=mock_client)

        with pytest.raises(RevenueCycleException) as exc_info:
            await worker.execute(valid_input)

        assert "Failed to send copay estimate notification" in str(exc_info.value)
        assert exc_info.value.code == "REVENUE_CYCLE_ERROR"
        assert "APPT-67890" in str(exc_info.value.details)

    @pytest.mark.asyncio
    async def test_output_fields_present(self, worker, valid_input, tenant_ctx):
        """Test all expected output fields are present."""
        result = await worker.execute(valid_input)

        assert "notification_sent" in result
        assert "message_id" in result
        assert "sent_at" in result
        assert "payment_action" in result

        # Verify sent_at is valid ISO timestamp
        sent_at = datetime.fromisoformat(result["sent_at"])
        assert sent_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_currency_formatting(self, worker, valid_input, tenant_ctx):
        """Test Brazilian Real currency formatting."""
        # Test with various amounts
        test_cases = [
            (150.00, "R$ 150,00"),
            (1500.50, "R$ 1.500,50"),
            (12345.67, "R$ 12.345,67"),
        ]

        for amount, expected in test_cases:
            formatted = worker._format_currency(amount)
            assert formatted == expected

    @pytest.mark.asyncio
    async def test_whatsapp_template_structure(self, valid_input, tenant_ctx):
        """Test WhatsApp template is created with correct structure."""
        mock_client = AsyncMock()
        mock_client.send_template.return_value = "msg-12345"

        worker = PatientCopayEstimateWorker(whatsapp_client=mock_client)
        await worker.execute(valid_input)

        # Verify send_template was called
        assert mock_client.send_template.called
        call_args = mock_client.send_template.call_args

        # Check phone number
        assert call_args[1]["to"] == "+5511987654321"

        # Check template structure
        template = call_args[1]["template"]
        assert isinstance(template, WhatsAppTemplate)
        assert template.name == "copay_estimate_v1"
        assert template.language == "pt_BR"
        assert len(template.body_params) == 3
        assert template.body_params[0] == "2024-03-15"  # appointment_date
        assert "R$" in template.body_params[1]  # formatted copay
        assert "80%" in template.body_params[2]  # coverage

    @pytest.mark.asyncio
    async def test_interactive_buttons_added(self, valid_input, tenant_ctx):
        """Test interactive buttons are added to template."""
        mock_client = AsyncMock()
        mock_client.send_template.return_value = "msg-12345"

        worker = PatientCopayEstimateWorker(whatsapp_client=mock_client)
        await worker.execute(valid_input)

        template = mock_client.send_template.call_args[1]["template"]
        assert template.buttons is not None
        assert len(template.buttons) == 3

        # Check button types and text
        button_texts = [btn["text"] for btn in template.buttons]
        assert "Pagar Agora" in button_texts
        assert "Pagar na Consulta" in button_texts
        assert "Dúvidas" in button_texts

    @pytest.mark.asyncio
    async def test_deep_link_format(self, valid_input, tenant_ctx):
        """Test deep link URL format for payment."""
        mock_client = AsyncMock()
        mock_client.send_template.return_value = "msg-12345"

        worker = PatientCopayEstimateWorker(whatsapp_client=mock_client)
        await worker.execute(valid_input)

        template = mock_client.send_template.call_args[1]["template"]
        pay_now_button = next(
            btn for btn in template.buttons if btn["text"] == "Pagar Agora"
        )

        expected_url = f"https://portal.austa.com.br/pay/{valid_input['appointment_id']}"
        assert pay_now_button["url"] == expected_url
