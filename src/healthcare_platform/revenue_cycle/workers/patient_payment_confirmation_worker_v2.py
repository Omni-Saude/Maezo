"""
Patient Payment Confirmation Worker (Refactored)
Purpose: Send payment confirmation via WhatsApp with PDF receipt

TOPIC: financial.payment_confirmed

Archetype: NONE (no DMN) - Thin worker: template + document send.

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, HttpUrl, ValidationError

from healthcare_platform.shared.domain.exceptions import RevenueCycleException
from healthcare_platform.shared.integrations.whatsapp_client import (
    WhatsAppClientProtocol,
    WhatsAppTemplate,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


# ── Pydantic Models (for backward compat with tests) ──

class PatientPaymentConfirmationInput(BaseModel):
    """Input model for payment confirmation notification."""
    patient_id: str = Field(..., description="Patient identifier")
    phone_number: str = Field(..., description="Patient phone number (E.164 format)")
    payment_id: str = Field(..., description="Payment transaction identifier")
    amount: float = Field(..., ge=0, description="Payment amount in BRL")
    payment_method: str = Field(..., description="Payment method (e.g., PIX, Cartão)")
    receipt_url: HttpUrl = Field(..., description="Pre-signed URL to PDF receipt")
    remaining_balance: float = Field(..., ge=0, description="Remaining balance after payment")


class PatientPaymentConfirmationOutput(BaseModel):
    """Output model for payment confirmation notification."""
    notification_sent: bool = Field(..., description="Whether template message was sent")
    message_id: Optional[str] = Field(None, description="WhatsApp message ID")
    document_sent: bool = Field(..., description="Whether PDF receipt was sent")
    sent_at: str = Field(..., description="ISO 8601 timestamp when sent")


def format_brl(amount: float) -> str:
    """Format amount as Brazilian Real (R$ 1.234,56)."""
    formatted = f"R$ {amount:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


class PatientPaymentConfirmationWorker(BaseExternalTaskWorker):
    """
    Refactored payment confirmation worker.

    Responsibilities (thin worker, no DMN):
    1. Parse and validate input variables
    2. Format currency
    3. Send WhatsApp template message
    4. Send PDF receipt document
    """

    TOPIC = "financial.payment_confirmed"

    def __init__(
        self,
        whatsapp_client: Optional[WhatsAppClientProtocol] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.whatsapp_client = whatsapp_client

    def execute_task(self, context: TaskContext) -> TaskResult:
        """Execute payment confirmation notification for Camunda."""
        try:
            variables = context.variables
            patient_id = variables.get("patient_id", "")
            phone_number = variables.get("phone_number", "")
            payment_id = variables.get("payment_id", "")
            amount = float(variables.get("amount", 0))
            payment_method = variables.get("payment_method", "")
            receipt_url = variables.get("receipt_url", "")

            if not patient_id or not phone_number or not payment_id:
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_INPUT",
                    error_message="Missing patient_id, phone_number, or payment_id",
                )

            formatted_amount = format_brl(amount)

            # Send template message
            message_id = None
            if self.whatsapp_client:
                message_id = self.whatsapp_client.send_template(
                    to=phone_number,
                    template_name="payment_confirmed_v1",
                    language_code="pt_BR",
                    body_params=[formatted_amount, payment_method],
                )

            # Send PDF receipt document
            document_sent = False
            if self.whatsapp_client and receipt_url:
                try:
                    self.whatsapp_client.send_document(
                        to=phone_number,
                        document_url=receipt_url,
                        caption=f"Recibo de pagamento - {formatted_amount}",
                    )
                    document_sent = True
                except Exception as doc_err:
                    self.logger.warning(
                        f"Receipt document send failed: {doc_err}",
                        extra={"tenant_id": context.tenant_id, "payment_id": payment_id},
                    )

            self.logger.info(
                "Payment confirmation sent",
                extra={
                    "tenant_id": context.tenant_id,
                    "patient_id": patient_id,
                    "payment_id": payment_id,
                },
            )

            return TaskResult.success({
                "notification_sent": True,
                "message_id": message_id,
                "document_sent": document_sent,
                "sent_at": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            self.logger.error(f"Payment confirmation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_PAYMENT_CONFIRMATION",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )

    # ── Async execute for backward compatibility with tests ──

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Async execute method for backward compatibility with old tests.

        This method validates input with Pydantic and raises RevenueCycleException
        on errors, matching the old worker API.
        """
        _tenant = get_required_tenant()

        # Handle TaskContext or Dict input
        if isinstance(task_variables, TaskContext):
            task_variables = task_variables.variables

        # Validate input
        try:
            input_data = PatientPaymentConfirmationInput(**task_variables)
        except ValidationError as e:
            raise RevenueCycleException(
                message="Invalid payment confirmation input",
                details={"validation_errors": e.errors()},
            ) from e

        formatted_amount = format_brl(input_data.amount)

        # Send template message
        try:
            message_id = None
            if self.whatsapp_client:
                template = WhatsAppTemplate(
                    name="payment_confirmed_v1",
                    language_code="pt_BR",
                    body_params=[formatted_amount, input_data.payment_method],
                )
                message_id = self.whatsapp_client.send_template_message(
                    phone_number=input_data.phone_number,
                    template=template,
                )

            # Send PDF receipt document
            document_sent = False
            if self.whatsapp_client and input_data.receipt_url:
                try:
                    self.whatsapp_client.send_document(
                        phone_number=input_data.phone_number,
                        document_url=str(input_data.receipt_url),
                        caption=f"Recibo de pagamento - {formatted_amount}",
                    )
                    document_sent = True
                except Exception:
                    pass  # Document send is optional

            return {
                "notification_sent": True,
                "message_id": message_id,
                "document_sent": document_sent,
                "sent_at": datetime.utcnow().isoformat() + "Z",
            }
        except Exception as e:
            raise RevenueCycleException(
                message="Failed to send payment confirmation",
                details={"error": str(e), "payment_id": input_data.payment_id},
            ) from e
