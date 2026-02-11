"""
Patient Emergency Wait Update Worker

CIB7 External Task Topic: emergency.wait_update
BPMN Error Code: PATIENT_ACCESS_ERROR

Updates patient on estimated emergency department wait time.
Message: 'Current estimated wait: [X] minutes. Your position: [Y].'
"""

from __future__ import annotations

from datetime import datetime, timezone
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


class PatientAccessException(DomainException):
    """Domain exception for patient access operations."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="PATIENT_ACCESS_ERROR",
            details=details,
            bpmn_error_code="PATIENT_ACCESS_ERROR",
        )


class PatientEmergencyWaitUpdateInput(BaseModel):
    """Input DTO for emergency wait update notification."""

    patient_id: str = Field(..., description="FHIR Patient ID")
    phone_number: str = Field(..., description="Patient phone E.164 format")
    estimated_wait_minutes: int = Field(
        ..., description="Estimated wait in minutes", ge=0
    )
    queue_position: int = Field(..., description="Position in queue", ge=1)
    triage_level: int = Field(
        ..., description="Triage classification 1-5", ge=1, le=5
    )


class PatientEmergencyWaitUpdateOutput(BaseModel):
    """Output DTO for emergency wait update notification."""

    notification_sent: bool = Field(
        ..., description="Whether notification was sent successfully"
    )
    message_id: str | None = Field(None, description="Message ID from provider")
    sent_at: str = Field(..., description="Timestamp of sending (ISO 8601)")


class PatientEmergencyWaitUpdateWorker:
    """Worker to send emergency wait time updates to patients."""

    TOPIC = "emergency.wait_update"

    def __init__(
        self,
        whatsapp_client: WhatsAppClientProtocol | None = None,
    ):
        """
        Initialize worker.

        Args:
            whatsapp_client: WhatsApp client for sending messages (defaults to stub)
        """
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(task_type="emergency.wait_update")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute emergency wait update notification.

        Args:
            task_variables: Task variables from CIB7 process

        Returns:
            Dictionary with notification status

        Raises:
            PatientAccessException: If notification fails
        """
        tenant_id = get_required_tenant()

        try:
            # Parse and validate input
            input_data = PatientEmergencyWaitUpdateInput(**task_variables)

            # CRITICAL: NEVER log phone_number (LGPD compliance)
            self.logger.info(
                "sending_emergency_wait_update",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                estimated_wait_minutes=input_data.estimated_wait_minutes,
                queue_position=input_data.queue_position,
                triage_level=input_data.triage_level,
            )

            # Prepare WhatsApp template
            template = WhatsAppTemplate(
                name="emergency_wait_update_v1",
                language="pt_BR",
                components=[
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(input_data.estimated_wait_minutes)},
                            {"type": "text", "text": str(input_data.queue_position)},
                        ],
                    }
                ],
            )

            # Send message via WhatsApp
            message_id = await self.whatsapp_client.send_template_message(
                phone=input_data.phone_number,
                template=template,
            )

            # Prepare output
            sent_at = datetime.now(timezone.utc).isoformat()
            output = PatientEmergencyWaitUpdateOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            self.logger.info(
                "emergency_wait_update_sent",
                tenant_id=tenant_id,
                patient_id=input_data.patient_id,
                message_id=message_id,
                sent_at=sent_at,
            )

            return output.model_dump()

        except Exception as e:
            self.logger.error(
                "emergency_wait_update_failed",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PatientAccessException(
                message=_(
                    "Falha ao enviar atualização de espera de emergência: {error}"
                ).format(error=str(e)),
                details={
                    "patient_id": task_variables.get("patient_id"),
                    "estimated_wait_minutes": task_variables.get("estimated_wait_minutes"),
                    "queue_position": task_variables.get("queue_position"),
                    "error_type": type(e).__name__,
                },
            ) from e
