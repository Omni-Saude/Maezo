"""
Patient Medication Reminder Worker

CIB7 External Task Topic: inpatient.medication_reminder
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Sends interactive medication reminder to inpatient with confirmation buttons
for medication adherence tracking.
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
    """Exception for clinical operations errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="CLINICAL_OPERATIONS_ERROR",
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )


class PatientMedicationReminderInput(BaseModel):
    """Input model for medication reminder notification."""

    patient_id: str = Field(..., description=_("ID FHIR do paciente"))
    phone_number: str = Field(..., description=_("Telefone do paciente em formato E.164"))
    medication_name: str = Field(..., description=_("Nome do medicamento"))
    dosage: str = Field(..., description=_("Dosagem do medicamento"))
    scheduled_time: str = Field(..., description=_("Horário agendado (formato HH:MM)"))
    instructions: str = Field(..., description=_("Instruções de administração"))


class PatientMedicationReminderOutput(BaseModel):
    """Output model for medication reminder notification."""

    notification_sent: bool = Field(..., description=_("Se a notificação foi enviada"))
    message_id: str | None = Field(
        None, description=_("ID da mensagem WhatsApp se enviado com sucesso")
    )
    sent_at: str = Field(..., description=_("Timestamp ISO 8601 do envio"))
    reminder_id: str = Field(..., description=_("ID único do lembrete para rastreamento"))
    response_received: bool = Field(
        default=False, description=_("Se resposta do paciente foi recebida")
    )
    response_action: str | None = Field(
        None, description=_("Ação da resposta (taken/remind_later/need_help)")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert output to Camunda process variables."""
        return self.model_dump()


class PatientMedicationReminderWorker:
    """
    Worker to send medication reminder to inpatient.

    Sends WhatsApp notification with interactive buttons for
    medication adherence confirmation and support requests.
    """

    TOPIC = "inpatient.medication_reminder"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """
        Initialize worker with WhatsApp client.

        Args:
            whatsapp_client: WhatsApp client for sending messages.
                           Defaults to StubWhatsAppClient for testing.
        """
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="inpatient.medication_reminder")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute medication reminder notification.

        Args:
            task_variables: Task variables containing medication details

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If notification fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = PatientMedicationReminderInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for medication reminder input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para lembrete de medicação"),
                details={"validation_error": str(e)},
            ) from e

        # Generate unique reminder ID
        reminder_id = str(uuid.uuid4())

        # Log reminder (LGPD: no phone_number or medication details in logs)
        logger.info(
            "Processing medication reminder notification",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": input_data.patient_id,
                "reminder_id": reminder_id,
                "scheduled_time": input_data.scheduled_time,
            },
        )

        # Build WhatsApp template with interactive buttons
        template = WhatsAppTemplate(
            name="medication_reminder_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": input_data.medication_name},
                        {"type": "text", "text": input_data.dosage},
                        {"type": "text", "text": input_data.scheduled_time},
                        {"type": "text", "text": input_data.instructions},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": "0",
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": f"taken:{reminder_id}",
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
                            "payload": f"remind_later:{reminder_id}",
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
                            "payload": f"need_help:{reminder_id}",
                        }
                    ],
                },
            ],
        )

        # Send notification
        try:
            message_id = self._whatsapp_client.send_template_message(
                phone_number=input_data.phone_number,
                template=template,
            )

            sent_at = datetime.now(UTC).isoformat()

            logger.info(
                "Medication reminder notification sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "message_id": message_id,
                    "reminder_id": reminder_id,
                },
            )

            # Build output
            output = PatientMedicationReminderOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                reminder_id=reminder_id,
                response_received=False,
                response_action=None,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                "Failed to send medication reminder notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "reminder_id": reminder_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar notificação de lembrete de medicação"),
                details={
                    "patient_id": input_data.patient_id,
                    "reminder_id": reminder_id,
                    "error": str(e),
                },
            ) from e


TOPIC = "inpatient.medication_reminder"
