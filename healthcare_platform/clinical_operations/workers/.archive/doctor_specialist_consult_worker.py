"""
Doctor Specialist Consult Worker

CIB7 External Task Topic: emergency.specialist_consult
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Requests specialist consultation via WhatsApp with patient summary.
Includes interactive buttons: [Accept] [Decline] [Call Back].
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

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

logger = get_logger(__name__, worker="clinical.specialist_consult")


class ClinicalOperationsException(DomainException):
    """    Clinical operations domain exception.
    
        Archetype: CLINICAL_ALERT
        """

    bpmn_error_code: str = "CLINICAL_OPERATIONS_ERROR"


class DoctorSpecialistConsultInput(BaseModel):
    """Input model for doctor specialist consult worker."""

    specialist_id: str = Field(
        ..., description=_("FHIR Practitioner ID of specialist")
    )
    requesting_doctor_id: str = Field(
        ..., description=_("FHIR Practitioner ID of requester")
    )
    patient_id: str = Field(..., description=_("FHIR Patient ID"))
    specialty: str = Field(..., description=_("Medical specialty"))
    urgency: str = Field(
        ..., description=_("Urgency level: low/medium/high/critical")
    )
    clinical_summary: str = Field(
        ..., description=_("Clinical summary for specialist - max 500 chars")
    )
    phone_number: str = Field(..., description=_("Specialist phone E.164"))

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "specialist_id": self.specialist_id,
            "requesting_doctor_id": self.requesting_doctor_id,
            "patient_id": self.patient_id,
            "specialty": self.specialty,
            "urgency": self.urgency,
            "clinical_summary": self.clinical_summary,
            "phone_number": self.phone_number,
        }


class DoctorSpecialistConsultOutput(BaseModel):
    """Output model for doctor specialist consult worker."""

    notification_sent: bool = Field(
        ..., description=_("Whether notification was sent successfully")
    )
    message_id: str | None = Field(
        None, description=_("WhatsApp message ID for tracking")
    )
    consult_request_id: str = Field(
        ..., description=_("Generated UUID for tracking")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "notification_sent": self.notification_sent,
            "message_id": self.message_id,
            "consult_request_id": self.consult_request_id,
        }


class DoctorSpecialistConsultWorker:
    """Worker for requesting specialist consultations via WhatsApp."""

    TOPIC = "emergency.specialist_consult"
    VALID_URGENCY_LEVELS = {"low", "medium", "high", "critical"}

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize with WhatsApp client dependency."""
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _validate_urgency(self, urgency: str) -> None:
        """Validate urgency level."""
        if urgency not in self.VALID_URGENCY_LEVELS:
            logger.error(
                _("Urgência inválida: %s. Níveis válidos: %s"),
                urgency,
                ", ".join(self.VALID_URGENCY_LEVELS),
            )
            raise ClinicalOperationsException(
                _("Urgência inválida: {urgency}. Use: low/medium/high/critical").format(
                    urgency=urgency
                )
            )

    def _truncate_clinical_summary(self, summary: str) -> str:
        """Truncate clinical summary to max 500 chars."""
        if len(summary) > 500:
            logger.warning(
                _("Resumo clínico truncado de %d para 500 caracteres"),
                len(summary),
            )
            return summary[:497] + "..."
        return summary

    def _build_interactive_buttons(self, consult_request_id: str) -> list[dict]:
        """Build interactive button components for specialist response."""
        return [
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "0",
                "parameters": [
                    {
                        "type": "payload",
                        "payload": f"accept:{consult_request_id}",
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
                        "payload": f"decline:{consult_request_id}",
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
                        "payload": f"callback:{consult_request_id}",
                    }
                ],
            },
        ]

    def _build_template(
        self,
        specialty: str,
        urgency: str,
        clinical_summary: str,
        requesting_doctor_id: str,
        consult_request_id: str,
    ) -> WhatsAppTemplate:
        """Build WhatsApp template for specialist consultation request."""
        body_component = {
            "type": "body",
            "parameters": [
                {"type": "text", "text": specialty},
                {"type": "text", "text": urgency},
                {"type": "text", "text": clinical_summary},
                {"type": "text", "text": requesting_doctor_id},
            ],
        }

        button_components = self._build_interactive_buttons(consult_request_id)

        return WhatsAppTemplate(
            name="specialist_consult_request_v1",
            language="pt_BR",
            components=[body_component] + button_components,
        )

    @require_tenant
    @track_task_execution(task_type="emergency.specialist_consult")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute specialist consultation request worker.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If validation or sending fails
        """
        tenant_id = get_required_tenant().tenant_id

        logger.info(
            _("Iniciando worker de consulta especialista tenant=%s"),
            tenant_id,
        )

        # Parse and validate input
        try:
            input_data = DoctorSpecialistConsultInput(**task_variables)
        except Exception as e:
            logger.error(
                _("Erro ao validar entrada: %s"),
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos: {error}").format(error=str(e))
            ) from e

        # Validate inputs
        if not input_data.specialist_id:
            logger.error(_("specialist_id não fornecido"))
            raise ClinicalOperationsException(
                _("specialist_id é obrigatório")
            )

        self._validate_urgency(input_data.urgency)

        # Truncate clinical summary if needed
        clinical_summary = self._truncate_clinical_summary(
            input_data.clinical_summary
        )

        # Generate consult request ID
        consult_request_id = str(uuid.uuid4())

        logger.info(
            _("Solicitando consulta especialista=%s urgência=%s request_id=%s"),
            input_data.specialist_id[:8],  # Only log first 8 chars for privacy
            input_data.urgency,
            consult_request_id,
        )

        # LGPD: NEVER log phone_number or full clinical_summary
        try:
            # Build template
            template = self._build_template(
                specialty=input_data.specialty,
                urgency=input_data.urgency,
                clinical_summary=clinical_summary,
                requesting_doctor_id=input_data.requesting_doctor_id,
                consult_request_id=consult_request_id,
            )

            # Send WhatsApp message
            message_id = await self._whatsapp_client.send_template_message(
                phone=input_data.phone_number, template=template
            )

            logger.info(
                _("Consulta especialista enviada: request_id=%s message_id=%s"),
                consult_request_id,
                message_id,
            )

            # Build output
            output = DoctorSpecialistConsultOutput(
                notification_sent=True,
                message_id=message_id,
                consult_request_id=consult_request_id,
            )

            logger.info(
                _("Worker de consulta especialista concluído: %s"),
                consult_request_id,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro ao enviar consulta especialista request_id=%s: %s"),
                consult_request_id,
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar consulta especialista: {error}").format(
                    error=str(e)
                )
            ) from e


# Worker configuration
TOPIC = "emergency.specialist_consult"
