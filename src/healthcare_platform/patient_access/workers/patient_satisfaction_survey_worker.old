"""
Patient Satisfaction Survey Worker

CIB7 External Task Topic: relationship.survey
BPMN Error Code: PATIENT_ACCESS_ERROR

Sends post-visit satisfaction survey with NPS rating buttons.
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


class PatientSatisfactionSurveyInput(BaseModel):
    """Input DTO for satisfaction survey notification."""

    patient_id: str = Field(..., description="FHIR Patient ID")
    phone_number: str = Field(..., description="Patient phone E.164 format")
    visit_date: str = Field(..., description="Visit date ISO 8601")
    visit_type: str = Field(..., description="Type of visit (e.g. consultation)")
    provider_name: str = Field(..., description="Healthcare provider name")
    department: str = Field(..., description="Department name")


class PatientSatisfactionSurveyOutput(BaseModel):
    """Output DTO for satisfaction survey notification."""

    notification_sent: bool = Field(
        ..., description="Whether notification was sent successfully"
    )
    message_id: str | None = Field(None, description="Message ID from provider")
    sent_at: str = Field(..., description="Timestamp of sending (ISO 8601)")
    response_received: bool = Field(
        default=False, description="Whether patient responded"
    )
    nps_score: int | None = Field(
        default=None, description="NPS score 1-5", ge=1, le=5
    )
    feedback: str | None = Field(
        default=None, description="Patient feedback text"
    )


class PatientSatisfactionSurveyWorker:
    """Worker to send post-visit satisfaction surveys."""

    TOPIC = "relationship.survey"

    def __init__(
        self,
        whatsapp_client: WhatsAppClientProtocol | None = None,
    ):
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    def _get_followup_action(self, score: int) -> str:
        """Determine follow-up action based on NPS score."""

        if score <= 2:
            return "trigger_followup_call"
        if score == 3:
            return "send_thanks"
        return "send_referral_info"

    def _get_nps_category(self, score: int) -> str:
        """Categorize NPS score."""

        if score <= 2:
            return "detractor"
        if score == 3:
            return "passive"
        return "promoter"

    @require_tenant
    @track_task_execution(task_type="relationship.survey")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute satisfaction survey notification."""

        tenant_id = get_required_tenant()

        try:
            input_data = PatientSatisfactionSurveyInput(**task_variables)
        except ValidationError as ve:
            raise PatientAccessException(
                message=_("Dados inválidos para pesquisa de satisfação."),
                details={
                    "patient_id": task_variables.get("patient_id"),
                    "validation_errors": ve.errors(),
                },
            ) from ve

        try:
            # CRITICAL: NEVER log phone_number or feedback content (LGPD)
            self.logger.info(
                "sending_satisfaction_survey",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                visit_type=input_data.visit_type,
                department=input_data.department,
            )

            stars = ["1", "2", "3", "4", "5"]
            star_labels = [
                "\u2b50",
                "\u2b50\u2b50",
                "\u2b50\u2b50\u2b50",
                "\u2b50\u2b50\u2b50\u2b50",
                "\u2b50\u2b50\u2b50\u2b50\u2b50",
            ]

            button_components = [
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(i),
                    "parameters": [
                        {"type": "text", "text": star_labels[i]},
                    ],
                }
                for i in range(len(stars))
            ]

            template = WhatsAppTemplate(
                name="satisfaction_survey_v1",
                language="pt_BR",
                components=[
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": input_data.provider_name},
                            {"type": "text", "text": input_data.visit_date},
                        ],
                    },
                    *button_components,
                ],
            )

            message_id = await self.whatsapp_client.send_template_message(
                phone=input_data.phone_number,
                template=template,
            )

            sent_at = datetime.now(timezone.utc).isoformat()
            output = PatientSatisfactionSurveyOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                response_received=False,
                nps_score=None,
                feedback=None,
            )

            self.logger.info(
                "satisfaction_survey_sent",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                message_id=message_id,
                sent_at=sent_at,
                visit_type=input_data.visit_type,
            )

            return output.model_dump()

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "satisfaction_survey_failed",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PatientAccessException(
                message=_(
                    "Falha ao enviar pesquisa de satisfação: {error}"
                ).format(error=str(e)),
                details={
                    "patient_id": task_variables.get("patient_id"),
                    "visit_type": task_variables.get("visit_type"),
                    "department": task_variables.get("department"),
                    "error_type": type(e).__name__,
                },
            ) from e
