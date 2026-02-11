"""
Patient Preventive Reminder Worker

CIB7 External Task Topic: relationship.preventive
BPMN Error Code: PATIENT_ACCESS_ERROR

Reminds patients about overdue preventive care with scheduling options.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError

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


class PatientAccessException(DomainException):
    """Domain exception for patient access operations."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="PATIENT_ACCESS_ERROR",
            details=details,
            bpmn_error_code="PATIENT_ACCESS_ERROR",
        )


class PatientPreventiveReminderInput(BaseModel):
    """Input DTO for preventive care reminder notification."""

    patient_id: str = Field(..., description="FHIR Patient ID")
    phone_number: str = Field(..., description="Patient phone E.164 format")
    patient_name: str = Field(..., description="Patient first name")
    preventive_type: str = Field(..., description="Type of preventive care")
    last_date: str = Field(..., description="Last procedure date ISO 8601")
    recommended_frequency: str = Field(
        ..., description="Recommended frequency (e.g. 'annual')"
    )
    available_slots: list[str] = Field(
        default=[], description="Available scheduling slots"
    )


class PatientPreventiveReminderOutput(BaseModel):
    """Output DTO for preventive care reminder notification."""

    notification_sent: bool = Field(
        ..., description="Whether notification was sent successfully"
    )
    message_id: str | None = Field(None, description="Message ID from provider")
    sent_at: str = Field(..., description="Timestamp of sending (ISO 8601)")
    action_taken: str | None = Field(
        default=None, description="Patient action after notification"
    )


class PatientPreventiveReminderWorker:
    """Worker to send preventive care reminders to patients."""

    TOPIC = "relationship.preventive"

    def __init__(
        self,
        whatsapp_client: WhatsAppClientProtocol | None = None,
    ):
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    def _get_preventive_label(self, preventive_type: str) -> str:
        """Map preventive type to Portuguese display label."""

        labels = {
            "annual_checkup": "check-up anual",
            "flu_vaccine": "vacina da gripe",
            "mammogram": "mamografia",
            "colonoscopy": "colonoscopia",
            "eye_exam": "exame de vista",
            "dental_checkup": "consulta odontológica",
        }
        return labels.get(preventive_type, preventive_type)

    @require_tenant
    @track_task_execution(task_type="relationship.preventive")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute preventive care reminder notification."""

        tenant_id = get_required_tenant()

        try:
            input_data = PatientPreventiveReminderInput(**task_variables)
        except ValidationError as ve:
            raise PatientAccessException(
                message=_("Dados inválidos para lembrete preventivo."),
                details={
                    "patient_id": task_variables.get("patient_id"),
                    "validation_errors": ve.errors(),
                },
            ) from ve

        try:
            # CRITICAL: NEVER log phone_number (LGPD)
            self.logger.info(
                "sending_preventive_reminder",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                preventive_type=input_data.preventive_type,
                recommended_frequency=input_data.recommended_frequency,
            )

            preventive_label = self._get_preventive_label(
                input_data.preventive_type
            )

            template = WhatsAppTemplate(
                name="preventive_reminder_v1",
                language="pt_BR",
                components=[
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": input_data.patient_name},
                            {"type": "text", "text": preventive_label},
                            {"type": "text", "text": input_data.last_date},
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "0",
                        "parameters": [
                            {"type": "text", "text": "Agendar Agora"},
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "1",
                        "parameters": [
                            {"type": "text", "text": "Lembrar Depois"},
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "2",
                        "parameters": [
                            {"type": "text", "text": "Já Realizei"},
                        ],
                    },
                ],
            )

            message_id = await self.whatsapp_client.send_template_message(
                phone=input_data.phone_number,
                template=template,
            )

            sent_at = datetime.now(timezone.utc).isoformat()
            output = PatientPreventiveReminderOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                action_taken=None,
            )

            self.logger.info(
                "preventive_reminder_sent",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                message_id=message_id,
                sent_at=sent_at,
                preventive_type=input_data.preventive_type,
            )

            return output.model_dump()

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "preventive_reminder_failed",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PatientAccessException(
                message=_(
                    "Falha ao enviar lembrete preventivo: {error}"
                ).format(error=str(e)),
                details={
                    "patient_id": task_variables.get("patient_id"),
                    "preventive_type": task_variables.get("preventive_type"),
                    "error_type": type(e).__name__,
                },
            ) from e
