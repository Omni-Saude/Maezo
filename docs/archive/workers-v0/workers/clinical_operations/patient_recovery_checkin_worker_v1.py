"""
Patient Recovery Check-in Worker.

Sends WhatsApp check-in to monitor patient recovery status post-discharge.

CIB7 Topic: continuity.recovery_checkin

Responsibilities:
- Check on patient recovery status at scheduled intervals (Day 1, 3, 7, 14)
- Provide simple self-assessment options via WhatsApp buttons
- Track check-in delivery and patient responses
- Trigger alerts if patient reports worsening condition
- Support LGPD-compliant notification logging

Integration:
- TASY: Discharge records, patient demographics
- WhatsApp Business API: Interactive message delivery
- BPMN: If reported_status == "feeling_worse", trigger doctor_patient_recovery_alert_worker

Schedule: Day 1, 3, 7, 14 post-discharge
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
    """Exception for clinical operations domain errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="CLINICAL_OPERATIONS_ERROR",
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )


class PatientRecoveryCheckinInput(BaseModel):
    """Input for patient recovery check-in notification."""

    patient_id: str = Field(..., description=_("ID FHIR do paciente"))
    phone_number: str = Field(
        ..., description=_("Telefone do paciente em formato E.164")
    )
    discharge_date: str = Field(
        ..., description=_("Data da alta (ISO 8601)")
    )
    days_since_discharge: int = Field(
        ..., description=_("Dias desde a alta")
    )
    condition_name: str = Field(
        ..., description=_("Nome da condição tratada")
    )
    checkin_number: int = Field(
        ..., description=_("Número do check-in (1, 2, 3, 4)")
    )


class PatientRecoveryCheckinOutput(BaseModel):
    """Output for patient recovery check-in notification."""

    notification_sent: bool = Field(
        ..., description=_("Se a notificação foi enviada com sucesso")
    )
    message_id: str | None = Field(
        None, description=_("ID da mensagem WhatsApp")
    )
    sent_at: str = Field(..., description=_("Timestamp de envio (ISO 8601)"))
    checkin_id: str = Field(..., description=_("ID único do check-in"))
    response_received: bool = Field(
        default=False, description=_("Se resposta foi recebida")
    )
    reported_status: str | None = Field(
        None,
        description=_(
            "Status reportado (much_better/about_same/feeling_worse)"
        ),
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Temporal workflow variables."""
        return self.model_dump()


class PatientRecoveryCheckinWorker:
    """Worker for sending patient recovery check-in messages."""

    TOPIC = "continuity.recovery_checkin"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="continuity.recovery_checkin")
    async def execute(
        self, input_data: PatientRecoveryCheckinInput
    ) -> PatientRecoveryCheckinOutput:
        """
        Send recovery check-in to patient.

        CRITICAL: If reported_status == "feeling_worse", the BPMN workflow
        should trigger doctor_patient_recovery_alert_worker to notify the
        care team immediately.

        Args:
            input_data: Check-in details and patient contact

        Returns:
            PatientRecoveryCheckinOutput with delivery status

        Raises:
            ClinicalOperationsException: If check-in delivery fails
        """
        tenant = get_required_tenant()
        checkin_id = str(uuid.uuid4())
        sent_at = datetime.now(UTC).isoformat()

        # LGPD: Never log phone_number or patient health details
        logger.info(
            "Sending recovery check-in",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": input_data.patient_id,
                "checkin_id": checkin_id,
                "checkin_number": input_data.checkin_number,
                "days_since_discharge": input_data.days_since_discharge,
            },
        )

        try:
            # Build WhatsApp template with interactive buttons
            template = WhatsAppTemplate(
                name="recovery_checkin_v1",
                language="pt_BR",
                components=[
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": input_data.condition_name},
                            {
                                "type": "text",
                                "text": str(input_data.days_since_discharge),
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
                                "payload": f"much_better:{checkin_id}",
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
                                "payload": f"about_same:{checkin_id}",
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
                                "payload": f"feeling_worse:{checkin_id}",
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
                "Recovery check-in sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "checkin_id": checkin_id,
                    "message_id": message_id,
                },
            )

            return PatientRecoveryCheckinOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                checkin_id=checkin_id,
                response_received=False,
                reported_status=None,
            )

        except Exception as e:
            logger.error(
                "Failed to send recovery check-in",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "checkin_id": checkin_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise ClinicalOperationsException(
                message=_("Erro ao enviar check-in de recuperação"),
                details={
                    "patient_id": input_data.patient_id,
                    "checkin_id": checkin_id,
                    "error": str(e),
                },
            ) from e


# Module-level topic constant
TOPIC = PatientRecoveryCheckinWorker.TOPIC
