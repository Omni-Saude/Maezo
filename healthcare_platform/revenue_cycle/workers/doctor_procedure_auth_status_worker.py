"""
Worker: Doctor Procedure Authorization Status Notification

CIB7 Topic: financial.auth_pending
Purpose: Notify doctors about pending procedure authorizations requiring attention.

Scheduling: Daily at 8 AM if pending authorizations exist.

Integration: WhatsApp notification via template auth_pending_summary_v1
LGPD Compliance: Never logs phone_number, patient_name, or procedure details.
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


class PendingAuthorization(BaseModel):
    """Model for a single pending authorization."""

    patient_name: str = Field(
        ..., description="Name of patient requiring authorization"
    )
    procedure: str = Field(..., description="Procedure requiring authorization")
    days_pending: int = Field(..., ge=0, description="Days since authorization requested")
    payer: str = Field(..., description="Insurance payer name")


class DoctorProcedureAuthStatusInput(BaseModel):
    """Input model for doctor procedure authorization status notification."""

    doctor_id: str = Field(..., description="Doctor unique identifier")
    phone_number: str = Field(..., description="Doctor WhatsApp phone number")
    pending_authorizations: list[PendingAuthorization] = Field(
        default_factory=list, description="List of pending authorizations"
    )


class DoctorProcedureAuthStatusOutput(BaseModel):
    """Output model for doctor procedure authorization status notification."""

    notification_sent: bool = Field(
        ..., description="Whether notification was sent"
    )
    message_id: str | None = Field(
        None, description="WhatsApp message ID if sent"
    )
    sent_at: str = Field(..., description="ISO 8601 timestamp of notification")
    total_pending: int = Field(..., ge=0, description="Total pending authorizations")


class DoctorProcedureAuthStatusWorker:
    """
    Worker to notify doctors about pending procedure authorizations.

    Sends daily WhatsApp notification summarizing pending authorizations
    that require attention, including oldest items and total count.
    """

    TOPIC = "financial.auth_pending"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize worker with optional WhatsApp client."""
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution
    async def execute(
        self, task_variables: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Execute doctor procedure authorization status notification.

        Args:
            task_variables: Task input containing doctor_id, phone_number,
                          and pending_authorizations list.

        Returns:
            Dictionary with notification_sent, message_id, sent_at, total_pending.

        Raises:
            RevenueCycleException: On validation or notification errors.
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = DoctorProcedureAuthStatusInput(**task_variables)
        except Exception as e:
            raise RevenueCycleException(
                message=_("Invalid input for procedure authorization status"),
                details={"validation_error": str(e)},
            ) from e

        total_pending = len(input_data.pending_authorizations)
        sent_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Processing procedure authorization status",
            extra={
                "tenant_id": tenant.tenant_id,
                "doctor_id": input_data.doctor_id,
                "total_pending": total_pending,
            },
        )

        # If no pending authorizations, skip notification
        if total_pending == 0:
            logger.info(
                "No pending authorizations, skipping notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "doctor_id": input_data.doctor_id,
                },
            )
            output = DoctorProcedureAuthStatusOutput(
                notification_sent=False,
                message_id=None,
                sent_at=sent_at,
                total_pending=0,
            )
            return output.model_dump()

        # Find oldest pending days
        oldest_days = max(
            auth.days_pending for auth in input_data.pending_authorizations
        )

        # Build summary of top 3 items
        top_items = sorted(
            input_data.pending_authorizations,
            key=lambda x: x.days_pending,
            reverse=True,
        )[:3]

        summary_lines = [
            f"- {auth.patient_name}: {auth.procedure} ({auth.days_pending}d, {auth.payer})"
            for auth in top_items
        ]
        summary_text = "\n".join(summary_lines)

        # Send WhatsApp notification
        template = WhatsAppTemplate(
            name="auth_pending_summary_v1",
            language_code="pt_BR",
            body_params=[
                str(total_pending),
                str(oldest_days),
                summary_text,
            ],
        )

        try:
            message_id = await self.whatsapp_client.send_template(
                to=input_data.phone_number, template=template
            )
        except Exception as e:
            raise RevenueCycleException(
                message=_("Failed to send authorization status notification"),
                details={
                    "doctor_id": input_data.doctor_id,
                    "total_pending": total_pending,
                    "error": str(e),
                },
            ) from e

        logger.info(
            "Authorization status notification sent",
            extra={
                "tenant_id": tenant.tenant_id,
                "doctor_id": input_data.doctor_id,
                "total_pending": total_pending,
                "message_id": message_id,
            },
        )

        output = DoctorProcedureAuthStatusOutput(
            notification_sent=True,
            message_id=message_id,
            sent_at=sent_at,
            total_pending=total_pending,
        )

        return output.model_dump()
