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
    """Doctor_Referral_Status worker.
    
    Archetype: COMPLIANCE_VALIDATION
    """
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="CLINICAL_OPERATIONS_ERROR",
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )


class DoctorReferralStatusInput(BaseModel):
    doctor_id: str = Field(description=_("ID FHIR do médico"))
    phone_number: str = Field(description=_("Telefone do médico em formato E.164"))
    referral_id: str = Field(description=_("ID do encaminhamento"))
    patient_name: str = Field(description=_("Nome do paciente"))
    specialist_name: str = Field(description=_("Nome do especialista"))
    specialty: str = Field(description=_("Especialidade"))
    status: str = Field(description=_("Status do encaminhamento (approved/denied/completed)"))
    notes: str = Field(default="", description=_("Observações"))


class DoctorReferralStatusOutput(BaseModel):
    notification_sent: bool = Field(description=_("Indica se a notificação foi enviada"))
    message_id: str | None = Field(description=_("ID da mensagem WhatsApp enviada"))
    sent_at: str = Field(description=_("Data/hora de envio (ISO 8601)"))

    def to_variables(self) -> dict[str, Any]:
        return self.model_dump()


class DoctorReferralStatusWorker:
    TOPIC = "continuity.referral_status"

    def __init__(self, whatsapp_client: WhatsAppClientProtocol | None = None) -> None:
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="continuity.referral_status")
    async def execute(self, task_variables: dict[str, Any]) -> DoctorReferralStatusOutput:
        tenant = get_required_tenant()
        logger.info(
            "Sending referral status notification",
            extra={
                "tenant_id": tenant.tenant_id,
                "referral_id": task_variables.get("referral_id"),
                "status": task_variables.get("status"),
            },
        )

        try:
            input_data = DoctorReferralStatusInput(**task_variables)
        except Exception as e:
            raise ClinicalOperationsException(
                message="Invalid input for doctor referral status notification",
                details={"error": str(e)},
            ) from e

        template = WhatsAppTemplate(
            name="referral_status_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": input_data.patient_name},
                        {"type": "text", "text": input_data.specialist_name},
                        {"type": "text", "text": input_data.specialty},
                        {"type": "text", "text": input_data.status},
                        {"type": "text", "text": input_data.notes},
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
                "Referral status notification sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "referral_id": input_data.referral_id,
                    "message_id": message_id,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to send referral status notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "referral_id": input_data.referral_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                message="Failed to send referral status notification",
                details={"referral_id": input_data.referral_id, "error": str(e)},
            ) from e

        return DoctorReferralStatusOutput(
            notification_sent=notification_sent,
            message_id=message_id,
            sent_at=datetime.now(UTC).isoformat(),
        )


TOPIC = DoctorReferralStatusWorker.TOPIC
