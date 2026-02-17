"""
Doctor Triage Escalation Worker

CIB7 External Task Topic: emergency.triage_escalation
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Notifies attending physician when triage nurse escalates a patient
requiring immediate attention. HIGH urgency - bypasses frequency limits.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
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


def _(message: str) -> str:
    """Translation helper for Portuguese error messages."""
    return message


class ClinicalOperationsException(DomainException):
    """    Exception for clinical operations errors.
    
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


class DoctorTriageEscalationInput(BaseModel):
    """Input model for doctor triage escalation notification."""

    patient_id: str = Field(..., description="FHIR Patient ID")
    doctor_id: str = Field(..., description="FHIR Practitioner ID")
    phone_number: str = Field(..., description="Doctor phone in E.164 format")
    triage_level: int = Field(
        ..., ge=1, le=5, description="Triage level 1-5, where 1 is most critical"
    )
    chief_complaint: str = Field(..., description="Patient chief complaint")
    escalation_reason: str = Field(..., description="Reason for escalation")


class DoctorTriageEscalationOutput(BaseModel):
    """Output model for doctor triage escalation notification."""

    notification_sent: bool = Field(..., description="Whether notification was sent")
    message_id: str | None = Field(
        None, description="WhatsApp message ID if sent successfully"
    )
    sent_at: str = Field(..., description="ISO 8601 timestamp when notification sent")


class DoctorTriageEscalationWorker:
    """
    Worker to notify attending physician of triage escalation.

    Sends WhatsApp notification to doctor when nurse escalates patient
    requiring immediate attention. Uses HIGH urgency template.
    """

    TOPIC = "emergency.triage_escalation"

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
    @track_task_execution(task_type="emergency.triage_escalation")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute triage escalation notification.

        Args:
            task_variables: Task variables containing notification details

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If notification fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = DoctorTriageEscalationInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for triage escalation input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para escalação de triagem"),
                details={"validation_error": str(e)},
            ) from e

        # Log escalation (LGPD: no phone_number)
        urgency_label = self._get_urgency_label(input_data.triage_level)
        logger.info(
            "Processing triage escalation notification",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": input_data.patient_id,
                "doctor_id": input_data.doctor_id,
                "triage_level": input_data.triage_level,
                "urgency": urgency_label,
            },
        )

        # Build WhatsApp template
        template = WhatsAppTemplate(
            name="triage_escalation_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(input_data.triage_level)},
                        {"type": "text", "text": input_data.chief_complaint},
                        {"type": "text", "text": input_data.escalation_reason},
                        {"type": "text", "text": input_data.patient_id},
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
                "Triage escalation notification sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "doctor_id": input_data.doctor_id,
                    "message_id": message_id,
                    "triage_level": input_data.triage_level,
                },
            )

            # Build output
            output = DoctorTriageEscalationOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to send triage escalation notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "doctor_id": input_data.doctor_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar notificação de escalação de triagem"),
                details={
                    "patient_id": input_data.patient_id,
                    "doctor_id": input_data.doctor_id,
                    "error": str(e),
                },
            ) from e

    def _get_urgency_label(self, triage_level: int) -> str:
        """
        Get Portuguese urgency label for triage level.

        Args:
            triage_level: Triage level 1-5

        Returns:
            Portuguese urgency label
        """
        urgency_map = {
            1: "EMERGÊNCIA",
            2: "MUITO URGENTE",
            3: "URGENTE",
            4: "POUCO URGENTE",
            5: "NÃO URGENTE",
        }
        return urgency_map.get(triage_level, "DESCONHECIDO")
