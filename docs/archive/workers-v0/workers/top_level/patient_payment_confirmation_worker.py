"""
Patient Payment Confirmation Worker

Sends payment confirmation via WhatsApp with PDF receipt.
Triggered by CIB7 topic: financial.payment_confirmed

LGPD Compliance:
- Never logs phone_number, payment details, or CPF
- Masks CPF in outputs (***.***.XXX-XX pattern)
- Receipt URL should be pre-signed with 24h expiry

Architecture:
- Pydantic Input/Output models with Field descriptions
- @require_tenant and @track_task_execution decorators
- Validates input and wraps ValidationError in domain exception
- Uses WhatsAppClientProtocol for testing
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, ValidationError

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.whatsapp_client import (
    StubWhatsAppClient,
    WhatsAppClientProtocol,
    WhatsAppTemplate,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class RevenueCycleException(DomainException):
    """Revenue Cycle domain exception."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="REVENUE_CYCLE_ERROR",
            details=details,
            bpmn_error_code="REVENUE_CYCLE_ERROR",
        )


class PatientPaymentConfirmationInput(BaseModel):
    """Input model for payment confirmation notification."""

    patient_id: str = Field(..., description="Patient identifier")
    phone_number: str = Field(..., description="Patient phone number (E.164 format)")
    payment_id: str = Field(..., description="Payment transaction identifier")
    amount: float = Field(..., ge=0, description="Payment amount in BRL")
    payment_method: str = Field(..., description="Payment method (e.g., PIX, Cartão)")
    receipt_url: HttpUrl = Field(..., description="Pre-signed URL to PDF receipt (24h expiry)")
    remaining_balance: float = Field(..., ge=0, description="Remaining balance after payment")


class PatientPaymentConfirmationOutput(BaseModel):
    """Output model for payment confirmation notification."""

    notification_sent: bool = Field(..., description="Whether template message was sent")
    message_id: str | None = Field(None, description="WhatsApp message ID")
    document_sent: bool = Field(..., description="Whether PDF receipt was sent")
    sent_at: str = Field(..., description="ISO 8601 timestamp when sent")


class PatientPaymentConfirmationWorker:
    """
    Worker to send payment confirmation via WhatsApp.

    Sends both a template message confirming payment and a PDF receipt document.
    """

    TOPIC = "financial.payment_confirmed"

    def __init__(self, whatsapp_client: WhatsAppClientProtocol | None = None):
        """
        Initialize worker with WhatsApp client.

        Args:
            whatsapp_client: WhatsApp client (defaults to stub)
        """
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute payment confirmation notification.

        Args:
            task_variables: Task variables from BPMN process

        Returns:
            dict with notification_sent, message_id, document_sent, sent_at

        Raises:
            RevenueCycleException: If validation fails or notification fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = PatientPaymentConfirmationInput(**task_variables)
        except ValidationError as e:
            logger.error(
                "Invalid payment confirmation input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                    "patient_id": task_variables.get("patient_id"),
                },
            )
            raise RevenueCycleException(
                message=_("Invalid payment confirmation input"),
                details={"validation_errors": e.errors()},
            )

        # Format amount in Brazilian Real
        formatted_amount = f"R$ {input_data.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        # Send template message
        template = WhatsAppTemplate(
            name="payment_confirmed_v1",
            language_code="pt_BR",
            body_params=[formatted_amount, input_data.payment_method],
        )

        try:
            message_id = self._whatsapp_client.send_template_message(
                phone_number=input_data.phone_number,
                template=template,
            )
            logger.info(
                "Payment confirmation template sent",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "payment_id": input_data.payment_id,
                    "message_id": message_id,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to send payment confirmation template",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "payment_id": input_data.payment_id,
                    "error": str(e),
                },
            )
            raise RevenueCycleException(
                message=_("Failed to send payment confirmation"),
                details={"error": str(e)},
            )

        # Send PDF receipt as document
        receipt_caption = f"Recibo de pagamento - {formatted_amount}"
        document_sent = False

        try:
            self._whatsapp_client.send_document(
                phone_number=input_data.phone_number,
                document_url=str(input_data.receipt_url),
                caption=receipt_caption,
            )
            document_sent = True
            logger.info(
                "Payment receipt document sent",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "payment_id": input_data.payment_id,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to send payment receipt document",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "payment_id": input_data.payment_id,
                    "error": str(e),
                },
            )
            # Don't raise - template was sent successfully
            logger.warning(
                "Payment confirmed but receipt document failed to send",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                },
            )

        # Build output
        sent_at = datetime.now(timezone.utc).isoformat()
        output = PatientPaymentConfirmationOutput(
            notification_sent=True,
            message_id=message_id,
            document_sent=document_sent,
            sent_at=sent_at,
        )

        return output.model_dump()
