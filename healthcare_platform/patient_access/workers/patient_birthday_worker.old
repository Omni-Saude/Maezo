"""
Patient Birthday Greeting Worker

CIB7 External Task Topic: relationship.birthday
BPMN Error Code: PATIENT_ACCESS_ERROR

Sends personalized birthday greeting with age-appropriate wellness tip.
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


class PatientBirthdayInput(BaseModel):
    """Input DTO for birthday greeting notification."""

    patient_id: str = Field(..., description="FHIR Patient ID")
    phone_number: str = Field(..., description="Patient phone E.164 format")
    patient_name: str = Field(..., description="Patient first name")
    birth_date: str = Field(..., description="Birth date ISO 8601")
    age: int = Field(..., description="Patient age in years", ge=0)
    health_conditions: list[str] = Field(
        default=[], description="Active health conditions"
    )


class PatientBirthdayOutput(BaseModel):
    """Output DTO for birthday greeting notification."""

    notification_sent: bool = Field(
        ..., description="Whether notification was sent successfully"
    )
    message_id: str | None = Field(None, description="Message ID from provider")
    sent_at: str = Field(..., description="Timestamp of sending (ISO 8601)")


class PatientBirthdayWorker:
    """Worker to send personalized birthday greetings to patients."""

    TOPIC = "relationship.birthday"

    def __init__(
        self,
        whatsapp_client: WhatsAppClientProtocol | None = None,
    ):
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    def _get_wellness_tip(self, age: int, conditions: list[str]) -> str:
        """Return age-appropriate wellness tip, adjusted for conditions."""

        if age < 18:
            tip = "Continue brincando e praticando atividades físicas todos os dias!"
        elif age <= 64:
            tip = "Mantenha seus check-ups em dia e pratique exercícios regularmente."
        else:
            tip = (
                "Mantenha-se ativo, hidratado e cultive suas conexões sociais."
            )

        condition_tips: list[str] = []
        lower_conditions = [c.lower() for c in conditions]

        if "diabetes" in lower_conditions:
            condition_tips.append(
                "Cuide da alimentação equilibrada para manter a glicemia estável."
            )
        if "hypertension" in lower_conditions:
            condition_tips.append(
                "Reduza o sal e pratique técnicas de relaxamento para o estresse."
            )
        if "cancer" in lower_conditions:
            condition_tips.append(
                "Continue acompanhando seus exames de seguimento com a equipe médica."
            )

        if condition_tips:
            tip = f"{tip} {' '.join(condition_tips)}"

        return tip

    @require_tenant
    @track_task_execution(task_type="relationship.birthday")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute birthday greeting notification."""

        tenant_id = get_required_tenant()

        try:
            input_data = PatientBirthdayInput(**task_variables)
        except ValidationError as ve:
            raise PatientAccessException(
                message=_("Dados inválidos para notificação de aniversário."),
                details={
                    "patient_id": task_variables.get("patient_id"),
                    "validation_errors": ve.errors(),
                },
            ) from ve

        try:
            # CRITICAL: NEVER log phone_number or health_conditions (LGPD)
            self.logger.info(
                "sending_birthday_greeting",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                age=input_data.age,
            )

            wellness_tip = self._get_wellness_tip(
                input_data.age, input_data.health_conditions
            )

            template = WhatsAppTemplate(
                name="birthday_greeting_v1",
                language="pt_BR",
                components=[
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": input_data.patient_name},
                            {"type": "text", "text": wellness_tip},
                        ],
                    }
                ],
            )

            message_id = await self.whatsapp_client.send_template_message(
                phone=input_data.phone_number,
                template=template,
            )

            sent_at = datetime.now(timezone.utc).isoformat()
            output = PatientBirthdayOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            self.logger.info(
                "birthday_greeting_sent",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                message_id=message_id,
                sent_at=sent_at,
            )

            return output.model_dump()

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "birthday_greeting_failed",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PatientAccessException(
                message=_(
                    "Falha ao enviar saudação de aniversário: {error}"
                ).format(error=str(e)),
                details={
                    "patient_id": task_variables.get("patient_id"),
                    "error_type": type(e).__name__,
                },
            ) from e
