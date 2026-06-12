"""
Patient Bill Notification Worker (Refactored)
Purpose: Notify patient when bill is ready with self-service payment options via WhatsApp

TOPIC: financial.bill_ready

Archetype: NONE (no DMN) - Thin worker: template + WhatsApp send with interactive buttons.

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from healthcare_platform.shared.integrations.whatsapp_client import (
    WhatsAppClientProtocol,
)
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


# ── Pydantic Models (for backward compat with tests) ──

class PatientBillNotificationInput(BaseModel):
    """Input model for bill notification."""
    patient_id: str = Field(..., description="Patient identifier")
    phone_number: str = Field(..., pattern=r'^\+', description="Patient phone number (E.164 format)")
    bill_id: str = Field(..., description="Bill identifier")
    total_amount: float = Field(..., ge=0, description="Total bill amount in BRL")
    due_date: str = Field(..., description="Bill due date")
    itemized_summary: Optional[str] = Field(None, description="Itemized billing summary")
    payment_methods: List[str] = Field(default_factory=list, description="Available payment methods")


class PatientBillNotificationOutput(BaseModel):
    """Output model for bill notification."""
    notification_sent: bool = Field(..., description="Whether notification was sent")
    message_id: Optional[str] = Field(None, description="WhatsApp message ID")
    sent_at: str = Field(..., description="ISO 8601 timestamp when sent")
    action_taken: Optional[str] = Field(None, description="Action taken")


def format_brl(amount: float) -> str:
    """Format amount as Brazilian Real (R$ 1.234,56)."""
    formatted = f"R$ {amount:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


class PatientBillNotificationWorker(BaseExternalTaskWorker):
    """
    Refactored patient bill notification worker.

    Responsibilities (thin worker, no DMN):
    1. Parse and validate input variables
    2. Format currency
    3. Build interactive button URLs
    4. Send WhatsApp notification with buttons
    """

    TOPIC = "financial.bill_ready"

    def __init__(
        self,
        whatsapp_client: Optional[WhatsAppClientProtocol] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.whatsapp_client = whatsapp_client

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute patient bill notification."""
        try:
            variables = context.variables
            patient_id = variables.get("patientId", "")
            phone_number = variables.get("phoneNumber", "")
            bill_id = variables.get("billId", "")
            total_amount = float(variables.get("totalAmount", 0))
            due_date = variables.get("dueDate", "")

            if not patient_id or not phone_number or not bill_id:
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_INPUT",
                    error_message="Missing patientId, phoneNumber, or billId",
                )

            formatted_amount = format_brl(total_amount)

            # Build interactive button URLs
            view_url = f"https://portal.maezo.com.br/bill/{bill_id}"
            pay_url = f"https://portal.maezo.com.br/pay/bill/{bill_id}"
            plan_url = f"https://portal.maezo.com.br/plan/{bill_id}"

            # Send WhatsApp notification
            message_id = None
            if self.whatsapp_client:
                message_id = self.whatsapp_client.send_template(
                    to=phone_number,
                    template_name="bill_ready_v1",
                    language_code="pt_BR",
                    body_params=[formatted_amount, due_date],
                    buttons=[
                        {"type": "url", "text": "Ver Conta", "url": view_url},
                        {"type": "url", "text": "Pagar Agora", "url": pay_url},
                        {"type": "url", "text": "Parcelar", "url": plan_url},
                    ],
                )

            self.logger.info(
                "Bill notification sent",
                extra={
                    "tenant_id": context.tenant_id,
                    "patient_id": patient_id,
                    "bill_id": bill_id,
                },
            )

            return TaskResult.success({
                "notificationSent": True,
                "messageId": message_id,
                "sentAt": datetime.utcnow().isoformat(),
                "viewUrl": view_url,
                "payUrl": pay_url,
            })

        except Exception as e:
            self.logger.error(f"Bill notification failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_BILL_NOTIFICATION",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
