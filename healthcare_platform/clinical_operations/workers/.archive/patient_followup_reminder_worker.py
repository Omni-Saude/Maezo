"""
Patient Follow-up Reminder Worker.

Sends WhatsApp reminder to patient to schedule follow-up appointment with self-service options.

CIB7 Topic: continuity.followup_reminder

Responsibilities:
- Remind patient to schedule follow-up with recommended doctor/specialty
- Provide self-service scheduling options via WhatsApp buttons
- Track reminder delivery and patient action
- Support LGPD-compliant notification logging

Integration:
- TASY: Patient demographics, appointment availability
- WhatsApp Business API: Interactive message delivery
"""

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
    """    Exception for clinical operations domain errors.
    
        Archetype: CLINICAL_ALERT
        """

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="CLINICAL_OPERATIONS_ERROR",
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )


class PatientFollowupReminderInput(BaseModel):
    """Input for patient follow-up reminder notification."""

    patient_id: str = Field(..., description=_("ID FHIR do paciente"))
    phone_number: str = Field(
        ..., description=_("Telefone do paciente em formato E.164")
    )
    doctor_name: str = Field(..., description=_("Nome do médico"))
    specialty: str = Field(..., description=_("Especialidade"))
    recommended_timeframe: str = Field(
        ..., description=_("Prazo recomendado (ex: '7 dias')")
    )
    available_slots: list[dict[str, str]] = Field(
        ..., description=_("Horários disponíveis (date, time)")
    )


class PatientFollowupReminderOutput(BaseModel):
    """Output for patient follow-up reminder notification."""

    notification_sent: bool = Field(
        ..., description=_("Se a notificação foi enviada com sucesso")
    )
    message_id: str | None = Field(
        None, description=_("ID da mensagem WhatsApp")
    )
    sent_at: str = Field(..., description=_("Timestamp de envio (ISO 8601)"))
    action_taken: str | None = Field(
        None,
        description=_(
            "Ação tomada pelo paciente (schedule_now/call_to_schedule/already_scheduled)"
        ),
    )
    reminder_id: str = Field(..., description=_("ID único do lembrete"))

    def to_variables(self) -> dict[str, Any]:
        """Convert to Temporal workflow variables."""
        return self.model_dump()


class PatientFollowupReminderWorker:
    """Worker for sending patient follow-up appointment reminders."""

    TOPIC = "continuity.followup_reminder"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="continuity.followup_reminder")
    async def execute(
        self, input_data: PatientFollowupReminderInput
    ) -> PatientFollowupReminderOutput:
        """
        Send follow-up appointment reminder to patient.

        Args:
            input_data: Reminder details and patient contact

        Returns:
            PatientFollowupReminderOutput with delivery status

        Raises:
            ClinicalOperationsException: If reminder delivery fails
        """
        tenant = get_required_tenant()
        reminder_id = str(uuid.uuid4())
        sent_at = datetime.now(UTC).isoformat()

        # LGPD: Never log phone_number or patient details
        logger.info(
            "Sending follow-up reminder",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": input_data.patient_id,
                "reminder_id": reminder_id,
                "specialty": input_data.specialty,
            },
        )

        try:
            # Build WhatsApp template with interactive buttons
            template = WhatsAppTemplate(
                name="followup_reminder_v1",
                language="pt_BR",
                components=[
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": input_data.doctor_name},
                            {"type": "text", "text": input_data.specialty},
                            {
                                "type": "text",
                                "text": input_data.recommended_timeframe,
                            },
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "0",
                        "parameters": [
                            {
                                "type": "payload",
                                "payload": f"schedule_now:{reminder_id}",
                            }
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "1",
                        "parameters": [
                            {
                                "type": "payload",
                                "payload": f"call_schedule:{reminder_id}",
                            }
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "2",
                        "parameters": [
                            {
                                "type": "payload",
                                "payload": f"already_scheduled:{reminder_id}",
                            }
                        ],
                    },
                ],
            )

            # Send WhatsApp message
            message_id = await self.whatsapp_client.send_template(
                to=input_data.phone_number, template=template
            )

            logger.info(
                "Follow-up reminder sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "reminder_id": reminder_id,
                    "message_id": message_id,
                },
            )

            return PatientFollowupReminderOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                action_taken=None,
                reminder_id=reminder_id,
            )

        except Exception as e:
            logger.error(
                "Failed to send follow-up reminder",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "reminder_id": reminder_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise ClinicalOperationsException(
                message=_("Erro ao enviar lembrete de retorno"),
                details={
                    "patient_id": input_data.patient_id,
                    "reminder_id": reminder_id,
                    "error": str(e),
                },
            ) from e


# Module-level topic constant
TOPIC = PatientFollowupReminderWorker.TOPIC
