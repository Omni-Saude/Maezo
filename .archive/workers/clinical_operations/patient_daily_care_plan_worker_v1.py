"""
Patient Daily Care Plan Worker

CIB7 External Task Topic: inpatient.daily_plan
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Sends morning care plan update to inpatient with daily schedule,
procedures, and care team on duty.
"""

from __future__ import annotations

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


class ScheduledItem(BaseModel):
    """Model for scheduled care plan item."""

    time: str = Field(..., description=_("Horário do item (formato HH:MM)"))
    description: str = Field(..., description=_("Descrição do procedimento/atividade"))


class PatientDailyCarePlanInput(BaseModel):
    """Input model for daily care plan notification."""

    patient_id: str = Field(..., description=_("ID FHIR do paciente"))
    phone_number: str = Field(..., description=_("Telefone do paciente em formato E.164"))
    date: str = Field(..., description=_("Data do plano de cuidados (formato YYYY-MM-DD)"))
    scheduled_items: list[dict[str, str]] = Field(
        ..., description=_("Lista de itens agendados com time e description")
    )
    care_team_on_duty: list[str] = Field(
        ..., description=_("Lista de nomes dos profissionais de plantão")
    )


class PatientDailyCarePlanOutput(BaseModel):
    """Output model for daily care plan notification."""

    notification_sent: bool = Field(..., description=_("Se a notificação foi enviada"))
    message_id: str | None = Field(
        None, description=_("ID da mensagem WhatsApp se enviado com sucesso")
    )
    sent_at: str = Field(..., description=_("Timestamp ISO 8601 do envio"))

    def to_variables(self) -> dict[str, Any]:
        """Convert output to Camunda process variables."""
        return self.model_dump()


class PatientDailyCarePlanWorker:
    """
    Worker to send daily care plan to inpatient.

    Sends WhatsApp notification with morning care plan including
    scheduled procedures, medications, and care team on duty.
    """

    TOPIC = "inpatient.daily_plan"

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
    @track_task_execution(task_type="inpatient.daily_plan")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute daily care plan notification.

        Args:
            task_variables: Task variables containing care plan details

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If notification fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = PatientDailyCarePlanInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for daily care plan input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para plano de cuidados diário"),
                details={"validation_error": str(e)},
            ) from e

        # Log care plan (LGPD: no phone_number)
        logger.info(
            "Processing daily care plan notification",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": input_data.patient_id,
                "date": input_data.date,
                "scheduled_items_count": len(input_data.scheduled_items),
                "care_team_count": len(input_data.care_team_on_duty),
            },
        )

        # Format scheduled items and care team
        items_summary = self._format_schedule_items(input_data.scheduled_items)
        care_team = ", ".join(input_data.care_team_on_duty)

        # Build WhatsApp template
        template = WhatsAppTemplate(
            name="daily_care_plan_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": input_data.date},
                        {"type": "text", "text": items_summary},
                        {"type": "text", "text": care_team},
                    ],
                }
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
                "Daily care plan notification sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "message_id": message_id,
                    "date": input_data.date,
                },
            )

            # Build output
            output = PatientDailyCarePlanOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                "Failed to send daily care plan notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar notificação de plano de cuidados diário"),
                details={
                    "patient_id": input_data.patient_id,
                    "error": str(e),
                },
            ) from e

    def _format_schedule_items(self, scheduled_items: list[dict[str, str]]) -> str:
        """
        Format scheduled items into readable list.

        Args:
            scheduled_items: List of dicts with 'time' and 'description'

        Returns:
            Formatted string with schedule items
        """
        if not scheduled_items:
            return _("Nenhum procedimento agendado")

        formatted_items = []
        for item in scheduled_items:
            time = item.get("time", "")
            description = item.get("description", "")
            if time and description:
                formatted_items.append(f"{time} - {description}")

        return "\n".join(formatted_items) if formatted_items else _("Nenhum procedimento agendado")


TOPIC = "inpatient.daily_plan"
