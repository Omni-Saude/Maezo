"""
Patient Health Anniversary Worker

CIB7 External Task Topic: relationship.anniversary
BPMN Error Code: PATIENT_ACCESS_ERROR

Celebrates health milestones (cancer-free, transplant, etc.) with sharing options.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError

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


class PatientAccessException(DomainException):
    """Domain exception for patient access operations."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="PATIENT_ACCESS_ERROR",
            details=details,
            bpmn_error_code="PATIENT_ACCESS_ERROR",
        )


class PatientHealthAnniversaryInput(BaseModel):
    """Input DTO for health anniversary notification."""

    patient_id: str = Field(..., description="FHIR Patient ID")
    phone_number: str = Field(..., description="Patient phone E.164 format")
    patient_name: str = Field(..., description="Patient first name")
    milestone_type: str = Field(..., description="Type of health milestone")
    milestone_date: str = Field(..., description="Original milestone date ISO 8601")
    years_since: int = Field(..., description="Years since milestone", ge=1)


class PatientHealthAnniversaryOutput(BaseModel):
    """Output DTO for health anniversary notification."""

    notification_sent: bool = Field(
        ..., description="Whether notification was sent successfully"
    )
    message_id: str | None = Field(None, description="Message ID from provider")
    sent_at: str = Field(..., description="Timestamp of sending (ISO 8601)")
    feedback_received: bool = Field(
        default=False, description="Whether patient responded"
    )


class PatientHealthAnniversaryWorker:
    """Worker to celebrate patient health milestones."""

    TOPIC = "relationship.anniversary"

    def __init__(
        self,
        whatsapp_client: WhatsAppClientProtocol | None = None,
    ):
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    def _get_milestone_label(self, milestone_type: str) -> str:
        """Map milestone type to Portuguese display label."""

        labels = {
            "cancer_free": "livre de câncer",
            "transplant": "de transplante",
            "surgery_recovery": "de recuperação cirúrgica",
            "diabetes_managed": "controlando diabetes",
        }
        return labels.get(milestone_type, milestone_type)

    @require_tenant
    @track_task_execution(task_type="relationship.anniversary")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute health anniversary notification."""

        tenant_id = get_required_tenant()

        try:
            input_data = PatientHealthAnniversaryInput(**task_variables)
        except ValidationError as ve:
            raise PatientAccessException(
                message=_("Dados inválidos para notificação de aniversário de saúde."),
                details={
                    "patient_id": task_variables.get("patient_id"),
                    "validation_errors": ve.errors(),
                },
            ) from ve

        try:
            # CRITICAL: NEVER log phone_number (LGPD)
            self.logger.info(
                "sending_health_anniversary",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                milestone_type=input_data.milestone_type,
                years_since=input_data.years_since,
            )

            milestone_label = self._get_milestone_label(input_data.milestone_type)

            template = WhatsAppTemplate(
                name="health_anniversary_v1",
                language="pt_BR",
                components=[
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": input_data.patient_name},
                            {"type": "text", "text": str(input_data.years_since)},
                            {"type": "text", "text": milestone_label},
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "0",
                        "parameters": [
                            {"type": "text", "text": "Compartilhar História"},
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "1",
                        "parameters": [
                            {"type": "text", "text": "Agradecer Equipe"},
                        ],
                    },
                ],
            )

            message_id = await self.whatsapp_client.send_template_message(
                phone=input_data.phone_number,
                template=template,
            )

            sent_at = datetime.now(timezone.utc).isoformat()
            output = PatientHealthAnniversaryOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                feedback_received=False,
            )

            self.logger.info(
                "health_anniversary_sent",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                message_id=message_id,
                sent_at=sent_at,
                milestone_type=input_data.milestone_type,
            )

            return output.model_dump()

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "health_anniversary_failed",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PatientAccessException(
                message=_(
                    "Falha ao enviar notificação de aniversário de saúde: {error}"
                ).format(error=str(e)),
                details={
                    "patient_id": task_variables.get("patient_id"),
                    "milestone_type": task_variables.get("milestone_type"),
                    "error_type": type(e).__name__,
                },
            ) from e
