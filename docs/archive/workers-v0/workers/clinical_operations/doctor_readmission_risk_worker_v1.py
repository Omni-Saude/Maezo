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
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="CLINICAL_OPERATIONS_ERROR",
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )


class DoctorReadmissionRiskInput(BaseModel):
    doctor_id: str = Field(description=_("ID FHIR do médico"))
    phone_number: str = Field(description=_("Telefone do médico em formato E.164"))
    patient_id: str = Field(description=_("ID FHIR do paciente"))
    patient_name: str = Field(description=_("Nome do paciente"))
    risk_score: float = Field(description=_("Pontuação de risco de readmissão (0-100)"))
    risk_factors: list[str] = Field(description=_("Fatores de risco identificados"))
    recommended_actions: list[str] = Field(description=_("Ações recomendadas"))
    discharge_date: str = Field(description=_("Data da alta (ISO 8601)"))


class DoctorReadmissionRiskOutput(BaseModel):
    notification_sent: bool = Field(description=_("Indica se a notificação foi enviada"))
    message_id: str | None = Field(description=_("ID da mensagem WhatsApp enviada"))
    sent_at: str = Field(description=_("Data/hora de envio (ISO 8601)"))
    alert_id: str = Field(description=_("ID único do alerta"))

    def to_variables(self) -> dict[str, Any]:
        return self.model_dump()


class DoctorReadmissionRiskWorker:
    TOPIC = "continuity.readmission_risk"

    def __init__(self, whatsapp_client: WhatsAppClientProtocol | None = None) -> None:
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="continuity.readmission_risk")
    async def execute(self, task_variables: dict[str, Any]) -> DoctorReadmissionRiskOutput:
        tenant = get_required_tenant()
        logger.info(
            "Sending readmission risk alert",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": task_variables.get("patient_id"),
                "risk_score": task_variables.get("risk_score"),
            },
        )

        try:
            input_data = DoctorReadmissionRiskInput(**task_variables)
        except Exception as e:
            raise ClinicalOperationsException(
                message="Invalid input for doctor readmission risk alert",
                details={"error": str(e)},
            ) from e

        alert_id = str(uuid.uuid4())

        template = WhatsAppTemplate(
            name="readmission_risk_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": input_data.patient_name},
                        {"type": "text", "text": f"{input_data.risk_score}%"},
                        {"type": "text", "text": ", ".join(input_data.risk_factors)},
                        {"type": "text", "text": ", ".join(input_data.recommended_actions)},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": "0",
                    "parameters": [
                        {"type": "payload", "payload": f"review:{alert_id}"},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": "1",
                    "parameters": [
                        {"type": "payload", "payload": f"ack:{alert_id}"},
                    ],
                },
            ],
        )

        try:
            message_id = await self.whatsapp_client.send_template_message(
                to=input_data.phone_number,
                template=template,
            )
            notification_sent = True
            logger.info(
                "Readmission risk alert sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "alert_id": alert_id,
                    "message_id": message_id,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to send readmission risk alert",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "alert_id": alert_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                message="Failed to send readmission risk alert",
                details={"patient_id": input_data.patient_id, "alert_id": alert_id, "error": str(e)},
            ) from e

        return DoctorReadmissionRiskOutput(
            notification_sent=notification_sent,
            message_id=message_id,
            sent_at=datetime.now(UTC).isoformat(),
            alert_id=alert_id,
        )


TOPIC = DoctorReadmissionRiskWorker.TOPIC
