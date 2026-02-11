"""Patient Bill Notification Worker.

Notifies patient when bill is ready with self-service payment options via WhatsApp.
Phase 5.4 Financial Self-Service - Patient-facing bill notification.

CIB7 Topic: financial.bill_ready
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

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

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="REVENUE_CYCLE_ERROR",
            details=details,
            bpmn_error_code="REVENUE_CYCLE_ERROR",
        )


class PatientBillNotificationInput(BaseModel):
    """Input model for patient bill notification."""

    patient_id: str = Field(..., description="Unique patient identifier")
    phone_number: str = Field(..., description="Patient phone number in E.164 format")
    bill_id: str = Field(..., description="Bill identifier")
    total_amount: float = Field(..., ge=0, description="Total bill amount in BRL")
    due_date: str = Field(..., description="Bill due date in ISO format or readable format")
    itemized_summary: str = Field(..., description="Brief itemized summary of charges")
    payment_methods: list[str] = Field(
        ..., description="Available payment methods (e.g., credit, debit, pix)"
    )

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        """Validate E.164 phone number format."""
        if not v.startswith("+"):
            raise ValueError("Phone number must be in E.164 format (start with +)")
        return v


class PatientBillNotificationOutput(BaseModel):
    """Output model for patient bill notification."""

    notification_sent: bool = Field(..., description="Whether notification was sent")
    message_id: str | None = Field(None, description="WhatsApp message ID")
    sent_at: str = Field(..., description="Timestamp when notification was sent")
    action_taken: str | None = Field(
        None, description="Action taken by patient (view, pay, plan)"
    )


class PatientBillNotificationWorker:
    """Worker for sending patient bill notifications via WhatsApp.

    Sends bill ready notification with self-service options including:
    - Formatted total amount in Brazilian Real
    - Due date
    - Interactive buttons (View Details, Pay Now, Payment Plan)
    - Deep links for self-service portal
    """

    TOPIC = "financial.bill_ready"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize worker with WhatsApp client.

        Args:
            whatsapp_client: WhatsApp client for sending messages.
                Defaults to StubWhatsAppClient for testing.
        """
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _format_currency(self, amount: float) -> str:
        """Format amount in Brazilian Real (R$).

        Args:
            amount: Amount to format

        Returns:
            Formatted currency string (e.g., "R$ 1.234,56")
        """
        formatted = f"R$ {amount:,.2f}"
        # Brazilian format: thousands with ".", decimals with ","
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute patient bill notification.

        Args:
            task_variables: Task input variables

        Returns:
            Dictionary with notification results

        Raises:
            RevenueCycleException: If validation or sending fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = PatientBillNotificationInput(**task_variables)
        except Exception as e:
            logger.error(
                "Validation error for bill notification",
                extra={"error": str(e), "tenant_id": tenant.id},
            )
            raise RevenueCycleException(
                message=_("Invalid input for bill notification"),
                details={"validation_error": str(e)},
            ) from e

        logger.info(
            "Sending bill notification",
            extra={
                "patient_id": input_data.patient_id,
                "bill_id": input_data.bill_id,
                "tenant_id": tenant.id,
                # LGPD: Never log phone_number or payment details
            },
        )

        # Format total amount in Brazilian Real
        formatted_amount = self._format_currency(input_data.total_amount)

        # Create WhatsApp template
        template = WhatsAppTemplate(
            name="bill_ready_v1",
            language="pt_BR",
            body_params=[
                formatted_amount,
                input_data.due_date,
            ],
        )

        # Add interactive buttons (WhatsApp max 3 buttons)
        try:
            view_url = f"https://portal.austa.com.br/bill/{input_data.bill_id}"
            pay_url = f"https://portal.austa.com.br/pay/bill/{input_data.bill_id}"
            plan_url = f"https://portal.austa.com.br/plan/{input_data.bill_id}"

            template.buttons = [
                {"type": "url", "text": "Ver Detalhes", "url": view_url},
                {"type": "url", "text": "Pagar Agora", "url": pay_url},
                {"type": "url", "text": "Parcelar", "url": plan_url},
            ]
        except Exception as e:
            logger.warning(
                "Could not add interactive buttons to template",
                extra={"error": str(e), "tenant_id": tenant.id},
            )

        # Send WhatsApp notification
        try:
            message_id = await self.whatsapp_client.send_template(
                to=input_data.phone_number, template=template
            )
            notification_sent = True
        except Exception as e:
            logger.error(
                "Failed to send bill notification",
                extra={
                    "patient_id": input_data.patient_id,
                    "bill_id": input_data.bill_id,
                    "error": str(e),
                    "tenant_id": tenant.id,
                },
            )
            raise RevenueCycleException(
                message=_("Failed to send bill notification"),
                details={"error": str(e), "bill_id": input_data.bill_id},
            ) from e

        sent_at = datetime.now(timezone.utc).isoformat()

        # Create output
        output = PatientBillNotificationOutput(
            notification_sent=notification_sent,
            message_id=message_id,
            sent_at=sent_at,
            action_taken=None,  # Will be updated if patient interacts
        )

        logger.info(
            "Bill notification sent successfully",
            extra={
                "patient_id": input_data.patient_id,
                "bill_id": input_data.bill_id,
                "message_id": message_id,
                "tenant_id": tenant.id,
            },
        )

        return output.model_dump()
