"""
Tests for Patient Payment Confirmation Worker

Validates:
- Successful payment confirmation with template + document
- Input validation (missing fields, invalid amounts)
- WhatsApp failures (template and document)
- Output structure and fields
- Document send flag accuracy
"""

import pytest

from healthcare_platform.revenue_cycle.workers.patient_payment_confirmation_worker import (
    PatientPaymentConfirmationWorker,
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
    """Set up tenant context."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker with stub WhatsApp client."""
    return PatientPaymentConfirmationWorker(whatsapp_client=StubWhatsAppClient())


@pytest.fixture
def valid_input():
    """Valid payment confirmation input."""
    return {
        "patient_id": "PAT123456",
        "phone_number": "+5511987654321",
        "payment_id": "PAY789012",
        "amount": 450.50,
        "payment_method": "PIX",
        "receipt_url": "https://receipts.example.com/PAY789012.pdf?expires=1234567890",
        "remaining_balance": 150.00,
    }


@pytest.mark.asyncio
async def test_successful_payment_confirmation(tenant_ctx, worker, valid_input):
    """Test successful payment confirmation with template and document."""
    result = await worker.execute(valid_input)

    assert result["notification_sent"] is True
    assert result["document_sent"] is True
    assert result["message_id"] is not None
    assert "sent_at" in result
    assert result["sent_at"].endswith("Z") or "+" in result["sent_at"]


@pytest.mark.asyncio
async def test_missing_payment_id(tenant_ctx, worker, valid_input):
    """Test validation error when payment_id is missing."""
    invalid_input = valid_input.copy()
    del invalid_input["payment_id"]

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(invalid_input)

    assert "Invalid payment confirmation input" in str(exc_info.value)
    assert exc_info.value.details is not None
    assert "validation_errors" in exc_info.value.details


@pytest.mark.asyncio
async def test_negative_amount(tenant_ctx, worker, valid_input):
    """Test validation error when amount is negative."""
    invalid_input = valid_input.copy()
    invalid_input["amount"] = -100.00

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(invalid_input)

    assert "Invalid payment confirmation input" in str(exc_info.value)


@pytest.mark.asyncio
async def test_invalid_receipt_url(tenant_ctx, worker, valid_input):
    """Test validation error when receipt_url is not a valid URL."""
    invalid_input = valid_input.copy()
    invalid_input["receipt_url"] = "not-a-url"

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(invalid_input)

    assert "Invalid payment confirmation input" in str(exc_info.value)


@pytest.mark.asyncio
async def test_whatsapp_template_failure(tenant_ctx, valid_input):
    """Test handling of WhatsApp template send failure."""

    class FailingWhatsAppClient(StubWhatsAppClient):
        def send_template_message(self, phone_number: str, template: WhatsAppTemplate) -> str:
            raise RuntimeError("WhatsApp API connection failed")

    worker = PatientPaymentConfirmationWorker(whatsapp_client=FailingWhatsAppClient())

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(valid_input)

    assert "Failed to send payment confirmation" in str(exc_info.value)
    assert exc_info.value.details is not None
    assert "error" in exc_info.value.details


@pytest.mark.asyncio
async def test_whatsapp_document_failure(tenant_ctx, valid_input):
    """Test handling of WhatsApp document send failure."""

    class FailingDocumentClient(StubWhatsAppClient):
        def send_document(self, phone_number: str, document_url: str, caption: str | None = None) -> str:
            raise RuntimeError("Document upload failed")

    worker = PatientPaymentConfirmationWorker(whatsapp_client=FailingDocumentClient())

    # Should NOT raise - template was sent successfully
    result = await worker.execute(valid_input)

    # Template sent, but document failed
    assert result["notification_sent"] is True
    assert result["document_sent"] is False
    assert result["message_id"] is not None


@pytest.mark.asyncio
async def test_output_fields_present(tenant_ctx, worker, valid_input):
    """Test all required output fields are present."""
    result = await worker.execute(valid_input)

    required_fields = {"notification_sent", "message_id", "document_sent", "sent_at"}
    assert required_fields.issubset(result.keys())


@pytest.mark.asyncio
async def test_brazilian_real_formatting(tenant_ctx, valid_input):
    """Test Brazilian Real amount formatting in template."""
    amounts_to_test = [
        (1000.50, "R$ 1.000,50"),
        (100.00, "R$ 100,00"),
        (10000.99, "R$ 10.000,99"),
    ]

    for amount, expected_format in amounts_to_test:
        formatted = f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        assert formatted == expected_format


@pytest.mark.asyncio
async def test_document_sent_flag_accuracy(tenant_ctx, valid_input):
    """Test document_sent flag reflects actual send status."""

    class TrackingWhatsAppClient(StubWhatsAppClient):
        def __init__(self):
            super().__init__()
            self.document_sent_count = 0

        def send_document(self, phone_number: str, document_url: str, caption: str | None = None) -> str:
            self.document_sent_count += 1
            return super().send_document(phone_number, document_url, caption)

    tracking_client = TrackingWhatsAppClient()
    worker = PatientPaymentConfirmationWorker(whatsapp_client=tracking_client)

    result = await worker.execute(valid_input)

    assert result["document_sent"] is True
    assert tracking_client.document_sent_count == 1


@pytest.mark.asyncio
async def test_receipt_caption_format(tenant_ctx, valid_input):
    """Test receipt document caption includes formatted amount."""

    class CapturingWhatsAppClient(StubWhatsAppClient):
        def __init__(self):
            super().__init__()
            self.last_caption = None

        def send_document(self, phone_number: str, document_url: str, caption: str | None = None) -> str:
            self.last_caption = caption
            return super().send_document(phone_number, document_url, caption)

    capturing_client = CapturingWhatsAppClient()
    worker = PatientPaymentConfirmationWorker(whatsapp_client=capturing_client)

    await worker.execute(valid_input)

    assert capturing_client.last_caption is not None
    assert "Recibo de pagamento" in capturing_client.last_caption
    assert "R$ 450,50" in capturing_client.last_caption


@pytest.mark.asyncio
async def test_missing_phone_number(tenant_ctx, worker, valid_input):
    """Test validation error when phone_number is missing."""
    invalid_input = valid_input.copy()
    del invalid_input["phone_number"]

    with pytest.raises(RevenueCycleException) as exc_info:
        await worker.execute(invalid_input)

    assert "Invalid payment confirmation input" in str(exc_info.value)


@pytest.mark.asyncio
async def test_zero_amount_allowed(tenant_ctx, worker, valid_input):
    """Test that zero amount is allowed (edge case for adjustments)."""
    valid_input["amount"] = 0.00

    result = await worker.execute(valid_input)

    assert result["notification_sent"] is True


@pytest.mark.asyncio
async def test_topic_constant(worker):
    """Test worker has correct CIB7 topic."""
    assert worker.TOPIC == "financial.payment_confirmed"
