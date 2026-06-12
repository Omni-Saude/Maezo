"""
Doctor CME Reminder Worker

CIB7 External Task Topic: relationship.cme_reminder
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Sends continuing medical education credit reminders with urgency levels.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.whatsapp_client import (
    WhatsAppClientProtocol,
    WhatsAppTemplate,
    StubWhatsAppClient,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__, worker="relationship.cme_reminder")


class ClinicalOperationsException(DomainException):
    """Clinical operations domain exception."""

    bpmn_error_code: str = "CLINICAL_OPERATIONS_ERROR"


class DoctorCmeReminderInput(BaseModel):
    """Input model for doctor CME reminder worker."""

    doctor_id: str = Field(..., description=_("FHIR Practitioner ID"))
    phone_number: str = Field(..., description=_("Doctor phone E.164"))
    credits_required: int = Field(
        ..., ge=0, description=_("Total credits required")
    )
    credits_completed: int = Field(
        ..., ge=0, description=_("Credits completed so far")
    )
    expiration_date: str = Field(
        ..., description=_("Credential expiration ISO date")
    )
    days_until_expiration: int = Field(
        ..., description=_("Days until credential expiration")
    )
    recommended_courses: list[str] = Field(
        default=[], description=_("List of recommended course names")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "doctor_id": self.doctor_id,
            "phone_number": self.phone_number,
            "credits_required": self.credits_required,
            "credits_completed": self.credits_completed,
            "expiration_date": self.expiration_date,
            "days_until_expiration": self.days_until_expiration,
            "recommended_courses": self.recommended_courses,
        }


class DoctorCmeReminderOutput(BaseModel):
    """Output model for doctor CME reminder worker."""

    notification_sent: bool = Field(
        ..., description=_("Whether notification was sent successfully")
    )
    message_id: str | None = Field(
        None, description=_("WhatsApp message ID for tracking")
    )
    sent_at: str = Field(..., description=_("ISO timestamp of sending"))

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "notification_sent": self.notification_sent,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
        }


class DoctorCmeReminderWorker:
    """Worker for sending CME credit reminders via WhatsApp."""

    TOPIC = "relationship.cme_reminder"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize with WhatsApp client dependency."""
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _get_urgency_level(self, days_until: int) -> str:
        """
        Determine urgency level based on days until expiration.

        Args:
            days_until: Days remaining until credential expiration.

        Returns:
            Urgency level string: critical, high, medium, or low.
        """
        if days_until <= 7:
            return "critical"
        if days_until <= 30:
            return "high"
        if days_until <= 60:
            return "medium"
        return "low"

    def _build_template(
        self, input_data: DoctorCmeReminderInput
    ) -> WhatsAppTemplate:
        """Build WhatsApp template for CME reminder."""
        body_component = {
            "type": "body",
            "parameters": [
                {"type": "text", "text": str(input_data.credits_completed)},
                {"type": "text", "text": str(input_data.credits_required)},
                {"type": "text", "text": input_data.expiration_date},
                {
                    "type": "text",
                    "text": str(input_data.days_until_expiration),
                },
            ],
        }

        button_view_courses = {
            "type": "button",
            "sub_type": "quick_reply",
            "index": "0",
            "parameters": [{"type": "text", "text": "Ver Cursos"}],
        }

        button_check_status = {
            "type": "button",
            "sub_type": "quick_reply",
            "index": "1",
            "parameters": [{"type": "text", "text": "Verificar Status"}],
        }

        return WhatsAppTemplate(
            name="cme_reminder_v1",
            language="pt_BR",
            components=[body_component, button_view_courses, button_check_status],
        )

    @require_tenant
    @track_task_execution(task_type="relationship.cme_reminder")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute CME reminder worker.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If validation or sending fails
        """
        tenant_id = get_required_tenant().tenant_id

        logger.info(
            _("Iniciando worker de CME reminder tenant=%s"),
            tenant_id,
        )

        # Parse and validate input
        try:
            input_data = DoctorCmeReminderInput(**task_variables)
        except ValidationError as e:
            logger.error(
                _("Erro ao validar entrada: %s"),
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos: {error}").format(error=str(e))
            ) from e

        urgency = self._get_urgency_level(input_data.days_until_expiration)

        # LGPD: NEVER log phone_number
        logger.info(
            _(
                "CME reminder: doctor=%s credits=%d/%d days=%d urgency=%s"
            ),
            input_data.doctor_id[:8],
            input_data.credits_completed,
            input_data.credits_required,
            input_data.days_until_expiration,
            urgency,
        )

        try:
            template = self._build_template(input_data)

            message_id = await self._whatsapp_client.send_template_message(
                phone=input_data.phone_number, template=template
            )

            sent_at = datetime.now(timezone.utc).isoformat()

            logger.info(
                _("CME reminder enviado: doctor=%s urgency=%s message_id=%s"),
                input_data.doctor_id[:8],
                urgency,
                message_id,
            )

            output = DoctorCmeReminderOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro ao enviar CME reminder doctor=%s: %s"),
                input_data.doctor_id[:8],
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar CME reminder: {error}").format(
                    error=str(e)
                )
            ) from e


# Worker configuration
TOPIC = "relationship.cme_reminder"
