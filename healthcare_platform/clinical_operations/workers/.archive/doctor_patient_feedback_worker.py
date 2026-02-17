"""
Doctor Patient Feedback Worker

CIB7 External Task Topic: relationship.patient_feedback
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Sends anonymized patient feedback to doctors using initials only (LGPD).
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

logger = get_logger(__name__, worker="relationship.patient_feedback")


class ClinicalOperationsException(DomainException):
    """    Clinical operations domain exception.
    
        Archetype: FINANCIAL_CALCULATION
        """

    bpmn_error_code: str = "CLINICAL_OPERATIONS_ERROR"


class DoctorPatientFeedbackInput(BaseModel):
    """Input model for doctor patient feedback worker."""

    doctor_id: str = Field(..., description=_("FHIR Practitioner ID"))
    phone_number: str = Field(..., description=_("Doctor phone E.164"))
    patient_initials: str = Field(
        ..., max_length=5, description=_("Patient initials only (LGPD)")
    )
    feedback_text: str = Field(..., description=_("Patient feedback content"))
    visit_date: str = Field(..., description=_("Visit date ISO format"))
    feedback_category: str = Field(
        ..., description=_("Feedback category identifier")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "doctor_id": self.doctor_id,
            "phone_number": self.phone_number,
            "patient_initials": self.patient_initials,
            "feedback_text": self.feedback_text,
            "visit_date": self.visit_date,
            "feedback_category": self.feedback_category,
        }


class DoctorPatientFeedbackOutput(BaseModel):
    """Output model for doctor patient feedback worker."""

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


class DoctorPatientFeedbackWorker:
    """Worker for sending patient feedback to doctors via WhatsApp."""

    TOPIC = "relationship.patient_feedback"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize with WhatsApp client dependency."""
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _get_category_emoji(self, category: str) -> str:
        """
        Map feedback category to display emoji.

        Args:
            category: Feedback category identifier.

        Returns:
            Emoji string for the category.
        """
        mapping = {
            "gratitude": "\U0001f64f",
            "recommendation": "\U0001f44d",
            "recovery_success": "\U0001f4aa",
            "communication": "\U0001f4ac",
        }
        return mapping.get(category, "\U0001f499")

    def _build_template(
        self,
        input_data: DoctorPatientFeedbackInput,
        category_emoji: str,
    ) -> WhatsAppTemplate:
        """Build WhatsApp template for patient feedback."""
        feedback_with_emoji = f"{category_emoji} {input_data.feedback_text}"

        body_component = {
            "type": "body",
            "parameters": [
                {"type": "text", "text": feedback_with_emoji},
                {"type": "text", "text": input_data.patient_initials},
                {"type": "text", "text": input_data.visit_date},
            ],
        }

        return WhatsAppTemplate(
            name="patient_feedback_v1",
            language="pt_BR",
            components=[body_component],
        )

    @require_tenant
    @track_task_execution(task_type="relationship.patient_feedback")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute patient feedback worker.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If validation or sending fails
        """
        tenant_id = get_required_tenant().tenant_id

        logger.info(
            _("Iniciando worker de patient feedback tenant=%s"),
            tenant_id,
        )

        # Parse and validate input
        try:
            input_data = DoctorPatientFeedbackInput(**task_variables)
        except ValidationError as e:
            logger.error(
                _("Erro ao validar entrada: %s"),
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos: {error}").format(error=str(e))
            ) from e

        category_emoji = self._get_category_emoji(input_data.feedback_category)

        # LGPD: NEVER log phone_number, feedback_text, or patient names
        logger.info(
            _("Patient feedback: doctor=%s category=%s visit=%s"),
            input_data.doctor_id[:8],
            input_data.feedback_category,
            input_data.visit_date,
        )

        try:
            template = self._build_template(input_data, category_emoji)

            message_id = await self._whatsapp_client.send_template_message(
                phone=input_data.phone_number, template=template
            )

            sent_at = datetime.now(timezone.utc).isoformat()

            logger.info(
                _("Patient feedback enviado: doctor=%s message_id=%s"),
                input_data.doctor_id[:8],
                message_id,
            )

            output = DoctorPatientFeedbackOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro ao enviar patient feedback doctor=%s: %s"),
                input_data.doctor_id[:8],
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar patient feedback: {error}").format(
                    error=str(e)
                )
            ) from e


# Worker configuration
TOPIC = "relationship.patient_feedback"
