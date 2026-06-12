"""
Worker: Doctor Reimbursement Summary Notification

CIB7 Topic: financial.reimbursement_summary
Purpose: Notify doctors with monthly billing and reimbursement summary.

Scheduling: Monthly on 5th business day.

Integration: WhatsApp notification via template reimbursement_summary_v1
LGPD Compliance: Never logs phone_number or financial details.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

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
    """Exception raised for revenue cycle errors.

        Archetype: FINANCIAL_CALCULATION
    """

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="REVENUE_CYCLE_ERROR",
            details=details,
            bpmn_error_code="REVENUE_CYCLE_ERROR",
        )


class DoctorReimbursementSummaryInput(BaseModel):
    """Input model for doctor reimbursement summary notification."""

    doctor_id: str = Field(..., description="Doctor unique identifier")
    phone_number: str = Field(..., description="Doctor WhatsApp phone number")
    period: str = Field(..., description="Period for summary (e.g., 'Jan/2026')")
    total_billed: float = Field(..., ge=0, description="Total amount billed")
    total_received: float = Field(..., ge=0, description="Total amount received")
    total_pending: float = Field(..., ge=0, description="Total amount pending")
    total_denied: float = Field(..., ge=0, description="Total amount denied")
    top_denials: list[str] = Field(
        default_factory=list, description="List of top denial reasons"
    )


class DoctorReimbursementSummaryOutput(BaseModel):
    """Output model for doctor reimbursement summary notification."""

    notification_sent: bool = Field(
        ..., description="Whether notification was sent"
    )
    message_id: str | None = Field(
        None, description="WhatsApp message ID if sent"
    )
    sent_at: str = Field(..., description="ISO 8601 timestamp of notification")


class DoctorReimbursementSummaryWorker:
    """
    Worker to send monthly reimbursement summary to doctors.

    Sends monthly WhatsApp notification with billing statistics including
    total billed, received, pending amounts, receipt rate, and top denials.
    """

    TOPIC = "financial.reimbursement_summary"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize worker with optional WhatsApp client."""
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _format_currency(self, amount: float) -> str:
        """
        Format amount as Brazilian Real currency.

        Args:
            amount: Amount to format.

        Returns:
            Formatted string (e.g., "R$ 1.234,56").
        """
        formatted = f"R$ {amount:,.2f}"
        # Convert to Brazilian format: . for thousands, , for decimals
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted

    @require_tenant
    @track_task_execution
    async def execute(
        self, task_variables: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Execute doctor reimbursement summary notification.

        Args:
            task_variables: Task input containing doctor_id, phone_number,
                          period, billing amounts, and top_denials.

        Returns:
            Dictionary with notification_sent, message_id, sent_at.

        Raises:
            RevenueCycleException: On validation or notification errors.
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = DoctorReimbursementSummaryInput(**task_variables)
        except Exception as e:
            raise RevenueCycleException(
                message=_("Invalid input for reimbursement summary"),
                details={"validation_error": str(e)},
            ) from e

        sent_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Processing reimbursement summary",
            extra={
                "tenant_id": tenant.tenant_id,
                "doctor_id": input_data.doctor_id,
                "period": input_data.period,
            },
        )

        # Calculate receipt rate
        if input_data.total_billed > 0:
            receipt_rate = (
                input_data.total_received / input_data.total_billed
            ) * 100
        else:
            receipt_rate = 0

        # Format amounts
        formatted_billed = self._format_currency(input_data.total_billed)
        formatted_received = self._format_currency(input_data.total_received)
        formatted_pending = self._format_currency(input_data.total_pending)

        # Build body parameters
        body_params = [
            input_data.period,
            formatted_billed,
            formatted_received,
            f"{receipt_rate:.1f}%",
            formatted_pending,
        ]

        # DEPRECATED: denial_text era usado no template WhatsApp de resumo de reembolso
        # denial_text = ""
        # if input_data.top_denials:
        #     top_three = input_data.top_denials[:3]
        #     denial_text = "Top negativas: " + ", ".join(top_three)

        # Send WhatsApp notification
        template = WhatsAppTemplate(
            name="reimbursement_summary_v1",
            language_code="pt_BR",
            body_params=body_params,
        )

        try:
            message_id = await self.whatsapp_client.send_template(
                to=input_data.phone_number, template=template
            )
        except Exception as e:
            raise RevenueCycleException(
                message=_("Failed to send reimbursement summary notification"),
                details={
                    "doctor_id": input_data.doctor_id,
                    "period": input_data.period,
                    "error": str(e),
                },
            ) from e

        logger.info(
            "Reimbursement summary notification sent",
            extra={
                "tenant_id": tenant.tenant_id,
                "doctor_id": input_data.doctor_id,
                "period": input_data.period,
                "message_id": message_id,
                "has_denials": bool(input_data.top_denials),
            },
        )

        output = DoctorReimbursementSummaryOutput(
            notification_sent=True,
            message_id=message_id,
            sent_at=sent_at,
        )

        return output.model_dump()
