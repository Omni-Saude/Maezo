from __future__ import annotations

import uuid
from datetime import UTC, datetime
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


class ClinicalOperationsException(DomainException):
    """    Clinical operations domain exception with BPMN error code.
    
        Archetype: COMPLIANCE_VALIDATION
        """

    def __init__(self, message: str, error_code: str = "CLINICAL_OPS_ERROR") -> None:
        super().__init__(message)
        self.error_code = error_code


class DoctorFollowupCompletionInput(BaseModel):
    """Input for doctor follow-up completion notification."""

    doctor_id: str = Field(..., description=_("ID FHIR do médico"))
    phone_number: str = Field(..., description=_("Telefone do médico em formato E.164"))
    pending_patients: list[dict[str, Any]] = Field(
        ...,
        description=_(
            "Lista de pacientes pendentes (id, name, discharge_date, days_overdue, recommended_followup_type)"
        ),
    )


class DoctorFollowupCompletionOutput(BaseModel):
    """Output from doctor follow-up completion notification."""

    notification_sent: bool = Field(..., description=_("Se a notificação foi enviada"))
    message_id: str | None = Field(None, description=_("ID da mensagem WhatsApp"))
    sent_at: str = Field(..., description=_("Timestamp do envio (ISO 8601)"))
    total_pending: int = Field(..., description=_("Total de pacientes pendentes"))

    def to_variables(self) -> dict[str, Any]:
        """Convert output to Temporal workflow variables."""
        return {
            "notification_sent": self.notification_sent,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
            "total_pending": self.total_pending,
        }


class DoctorFollowupCompletionWorker:
    """Worker to notify doctor of patients with pending follow-up scheduling."""

    TOPIC = "continuity.followup_pending"

    def __init__(
        self,
        whatsapp_client: WhatsAppClientProtocol | None = None,
    ) -> None:
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution
    async def execute(
        self,
        task_variables: dict[str, Any],
    ) -> DoctorFollowupCompletionOutput:
        """Execute follow-up pending notification to doctor."""
        tenant = get_required_tenant()
        logger.info(
            "Starting doctor follow-up completion notification",
            extra={
                "tenant_id": tenant.tenant_id,
                "doctor_id": task_variables.get("doctor_id"),
            },
        )

        try:
            input_data = DoctorFollowupCompletionInput(**task_variables)
        except Exception as e:
            raise ClinicalOperationsException(
                f"Invalid input for followup completion: {e}",
                error_code="INVALID_FOLLOWUP_COMPLETION_INPUT",
            ) from e

        if not input_data.pending_patients:
            raise ClinicalOperationsException(
                "No pending patients provided",
                error_code="NO_PENDING_PATIENTS",
            )

        # Calculate total pending and oldest overdue
        total_pending = len(input_data.pending_patients)
        oldest_overdue = max(
            patient.get("days_overdue", 0) for patient in input_data.pending_patients
        )
        first_patient_name = input_data.pending_patients[0].get("name", "Unknown")

        # Build WhatsApp template
        template = WhatsAppTemplate(
            name="followup_pending_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(total_pending)},
                        {"type": "text", "text": str(oldest_overdue)},
                        {"type": "text", "text": first_patient_name},
                    ],
                },
            ],
        )

        # Send WhatsApp notification
        try:
            message_id = await self.whatsapp_client.send_template(
                to=input_data.phone_number,
                template=template,
            )
            notification_sent = True
            logger.info(
                "Follow-up pending notification sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "doctor_id": input_data.doctor_id,
                    "total_pending": total_pending,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to send follow-up pending notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "doctor_id": input_data.doctor_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                f"WhatsApp notification failed: {e}",
                error_code="WHATSAPP_SEND_FAILED",
            ) from e

        sent_at = datetime.now(UTC).isoformat()

        return DoctorFollowupCompletionOutput(
            notification_sent=notification_sent,
            message_id=message_id,
            sent_at=sent_at,
            total_pending=total_pending,
        )


TOPIC = "continuity.followup_pending"
