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
    """Clinical operations domain exception with BPMN error code."""

    def __init__(self, message: str, error_code: str = "CLINICAL_OPS_ERROR") -> None:
        super().__init__(message)
        self.error_code = error_code


class DoctorPatientRecoveryAlertInput(BaseModel):
    """Input for doctor patient recovery alert notification."""

    doctor_id: str = Field(..., description=_("ID FHIR do médico"))
    phone_number: str = Field(..., description=_("Telefone do médico em formato E.164"))
    patient_id: str = Field(..., description=_("ID FHIR do paciente"))
    patient_name: str = Field(..., description=_("Nome do paciente"))
    reported_status: str = Field(..., description=_("Status reportado pelo paciente"))
    symptoms: list[str] = Field(..., description=_("Lista de sintomas reportados"))
    discharge_date: str = Field(..., description=_("Data da alta (ISO 8601)"))
    days_since_discharge: int = Field(..., description=_("Dias desde a alta"))


class DoctorPatientRecoveryAlertOutput(BaseModel):
    """Output from doctor patient recovery alert notification."""

    notification_sent: bool = Field(..., description=_("Se a notificação foi enviada"))
    message_id: str | None = Field(None, description=_("ID da mensagem WhatsApp"))
    sent_at: str = Field(..., description=_("Timestamp do envio (ISO 8601)"))
    acknowledged: bool = Field(False, description=_("Se foi reconhecido pelo médico"))
    priority: str = Field("HIGH", description=_("Prioridade do alerta"))

    def to_variables(self) -> dict[str, Any]:
        """Convert output to Temporal workflow variables."""
        return {
            "notification_sent": self.notification_sent,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
            "acknowledged": self.acknowledged,
            "priority": self.priority,
        }


class DoctorPatientRecoveryAlertWorker:
    """Worker to alert doctor when patient reports worsening condition."""

    TOPIC = "continuity.recovery_alert"

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
    ) -> DoctorPatientRecoveryAlertOutput:
        """Execute recovery alert notification to doctor."""
        tenant = get_required_tenant()
        logger.info(
            "Starting doctor patient recovery alert",
            extra={
                "tenant_id": tenant.tenant_id,
                "doctor_id": task_variables.get("doctor_id"),
                "patient_id": task_variables.get("patient_id"),
            },
        )

        try:
            input_data = DoctorPatientRecoveryAlertInput(**task_variables)
        except Exception as e:
            raise ClinicalOperationsException(
                f"Invalid input for recovery alert: {e}",
                error_code="INVALID_RECOVERY_ALERT_INPUT",
            ) from e

        # Generate unique alert ID
        alert_id = str(uuid.uuid4())

        # Build WhatsApp template
        symptoms_text = ", ".join(input_data.symptoms)
        template = WhatsAppTemplate(
            name="recovery_alert_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": input_data.patient_name},
                        {"type": "text", "text": str(input_data.days_since_discharge)},
                        {"type": "text", "text": symptoms_text},
                        {"type": "text", "text": input_data.reported_status},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": "0",
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": f"call_now:{alert_id}",
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
                            "payload": f"schedule_visit:{alert_id}",
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
                            "payload": f"reviewed:{alert_id}",
                        }
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
                "Recovery alert sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "doctor_id": input_data.doctor_id,
                    "alert_id": alert_id,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to send recovery alert",
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

        return DoctorPatientRecoveryAlertOutput(
            notification_sent=notification_sent,
            message_id=message_id,
            sent_at=sent_at,
            acknowledged=False,
            priority="HIGH",
        )


TOPIC = "continuity.recovery_alert"
