"""Patient Copay Estimate Worker.

Sends pre-visit copay estimate with payment options via WhatsApp.
Phase 5.4 Financial Self-Service - Patient-facing financial communication.

CIB7 Topic: financial.copay_estimate
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
            bpmn_error_code="REVENUE_CYCLE_ERROR",
            details=details,
        )


class PatientCopayEstimateInput(BaseModel):
    """Input model for patient copay estimate notification."""

    patient_id: str = Field(..., description="Unique patient identifier")
    phone_number: str = Field(..., description="Patient phone number in E.164 format")
    appointment_id: str = Field(..., description="Appointment identifier")
    procedure_codes: list[str] = Field(
        ..., description="List of procedure codes for the visit"
    )
    estimated_copay: float = Field(
        ..., ge=0, description="Estimated copay amount in BRL"
    )
    insurance_coverage: float = Field(
        ..., ge=0, le=100, description="Insurance coverage percentage"
    )
    appointment_date: str = Field(..., description="Appointment date in ISO format")

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        """Validate E.164 phone number format."""
        if not v.startswith("+"):
            raise ValueError("Phone number must be in E.164 format (start with +)")
        return v

    @field_validator("insurance_coverage")
    @classmethod
    def validate_coverage(cls, v: float) -> float:
        """Validate insurance coverage is between 0 and 100."""
        if v < 0 or v > 100:
            raise ValueError("Insurance coverage must be between 0 and 100 percent")
        return v


class PatientCopayEstimateOutput(BaseModel):
    """Output model for patient copay estimate notification."""

    notification_sent: bool = Field(..., description="Whether notification was sent")
    message_id: str | None = Field(None, description="WhatsApp message ID")
    sent_at: str = Field(..., description="Timestamp when notification was sent")
    payment_action: str | None = Field(
        None, description="Payment action taken by patient"
    )


class PatientCopayEstimateWorker:
    """Worker for sending patient copay estimates via WhatsApp.

    Sends pre-visit copay estimate with payment options including:
    - Formatted copay amount in Brazilian Real
    - Insurance coverage percentage
    - Interactive payment buttons (Pay Now, Pay at Visit, Question)
    - Deep link for online payment
    """

    TOPIC = "financial.copay_estimate"

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
    @track_task_execution(metric_name="patient_copay_estimate")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute patient copay estimate notification.

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
            input_data = PatientCopayEstimateInput(**task_variables)
        except Exception as e:
            logger.error(
                "Validation error for copay estimate",
                extra={"error": str(e), "tenant_id": tenant.tenant_code},
            )
            raise RevenueCycleException(
                message=_("Invalid input for copay estimate notification"),
                details={"validation_error": str(e)},
            ) from e

        logger.info(
            "Sending copay estimate notification",
            extra={
                "patient_id": input_data.patient_id,
                "appointment_id": input_data.appointment_id,
                "tenant_id": tenant.tenant_code,
                # LGPD: Never log phone_number, payment details, or copay amount
            },
        )

        # Format copay amount in Brazilian Real
        formatted_copay = self._format_currency(input_data.estimated_copay)

        # Create WhatsApp template with body component
        payment_url = (
            f"https://portal.maezo.com.br/pay/{input_data.appointment_id}"
        )
        
        body_component = {
            "type": "body",
            "parameters": [
                {"type": "text", "text": input_data.appointment_date},
                {"type": "text", "text": formatted_copay},
                {"type": "text", "text": f"{input_data.insurance_coverage:.0f}%"},
            ],
        }
        
        # Add interactive buttons (WhatsApp supports up to 3 buttons)
        button_components = [
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "text": payment_url}],
            },
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "1",
                "parameters": [{"type": "text", "text": "Pagar na Consulta"}],
            },
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "2",
                "parameters": [{"type": "text", "text": "Dúvidas"}],
            },
        ]
        
        template = WhatsAppTemplate(
            name="copay_estimate_v1",
            language="pt_BR",
            components=[body_component] + button_components,
        )

        # Send WhatsApp message
        try:
            message_id = await self.whatsapp_client.send_template_message(
                phone=input_data.phone_number, template=template
            )
            notification_sent = True
        except Exception as e:
            logger.error(
                "Failed to send copay estimate notification",
                extra={
                    "patient_id": input_data.patient_id,
                    "appointment_id": input_data.appointment_id,
                    "error": str(e),
                    "tenant_id": tenant.tenant_code,
                },
            )
            raise RevenueCycleException(
                message=_("Failed to send copay estimate notification"),
                details={"error": str(e), "appointment_id": input_data.appointment_id},
            ) from e

        sent_at = datetime.now(timezone.utc).isoformat()

        # Create output
        output = PatientCopayEstimateOutput(
            notification_sent=notification_sent,
            message_id=message_id,
            sent_at=sent_at,
            payment_action=None,  # Will be updated if patient interacts
        )

        logger.info(
            "Copay estimate notification sent successfully",
            extra={
                "patient_id": input_data.patient_id,
                "appointment_id": input_data.appointment_id,
                "message_id": message_id,
                "tenant_id": tenant.tenant_code,
            },
        )

        return output.model_dump()
