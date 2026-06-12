"""
Patient Triage Status Worker

CIB7 External Task Topic: emergency.triage_status
BPMN Error Code: PATIENT_ACCESS_ERROR

Notifies patient of triage classification result.
Message: 'Triage complete. Priority: [Level]. [Description]. Next: [Steps]'
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from healthcare_platform.shared.decorators import require_tenant, track_task_execution
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.whatsapp_client import (
    StubWhatsAppClient,
    WhatsAppClientProtocol,
    WhatsAppTemplate,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant

logger = logging.getLogger(__name__)


class PatientAccessException(DomainException):
    """Exception for patient access operations."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="PATIENT_ACCESS_ERROR",
            details=details,
            bpmn_error_code="PATIENT_ACCESS_ERROR",
        )


class TriageStatusInput(BaseModel):
    """Input variables for patient triage status notification."""

    patient_id: str = Field(..., description="FHIR Patient ID")
    phone_number: str = Field(..., description="Patient phone number in E.164 format")
    triage_level: int = Field(
        ..., description="Triage classification level (1-5)", ge=1, le=5
    )
    triage_description: str = Field(
        ..., description="Human-readable triage description"
    )
    next_steps: str = Field(..., description="Instructions for patient next steps")


class TriageStatusOutput(BaseModel):
    """Output variables for patient triage status notification."""

    notification_sent: bool = Field(..., description="Whether notification was sent")
    message_id: str | None = Field(
        ..., description="WhatsApp message ID if sent successfully"
    )
    sent_at: str = Field(..., description="Timestamp when notification was sent (ISO 8601)")


class PatientTriageStatusWorker:
    """
    Worker for notifying patients of their triage classification.

    Sends WhatsApp template message with triage level, description,
    and next steps for the patient.
    """

    TOPIC = "emergency.triage_status"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """
        Initialize the patient triage status worker.

        Args:
            whatsapp_client: WhatsApp client for sending messages.
                           Defaults to StubWhatsAppClient for testing.
        """
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="emergency.triage_status")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute patient triage status notification.

        Args:
            task_variables: Task variables containing patient and triage info

        Returns:
            Dictionary with notification_sent, message_id, and sent_at

        Raises:
            PatientAccessException: If notification fails
            ValidationError: If input validation fails
        """
        tenant = get_required_tenant()
        logger.info(
            "Processing triage status notification",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": task_variables.get("patient_id"),
                # LGPD: Never log phone_number
            },
        )

        # Validate input
        try:
            input_data = TriageStatusInput(**task_variables)
        except ValidationError as e:
            logger.error(
                "Invalid input for triage status notification",
                extra={"tenant_id": tenant.tenant_id, "errors": e.errors()},
            )
            raise PatientAccessException(
                message=_("Invalid input for triage status notification"),
                details={"validation_errors": e.errors()},
            ) from e

        # Get priority label from triage level
        priority_label = self._get_priority_label(input_data.triage_level)

        # Build WhatsApp template
        template = WhatsAppTemplate(
            name="triage_status_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": priority_label},
                        {"type": "text", "text": input_data.triage_description},
                        {"type": "text", "text": input_data.next_steps},
                    ],
                }
            ],
        )

        # Send notification
        try:
            message_id = await self.whatsapp_client.send_template_message(
                phone=input_data.phone_number,
                template=template,
            )

            sent_at = datetime.now(UTC).isoformat()

            logger.info(
                "Triage status notification sent",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "triage_level": input_data.triage_level,
                    "message_id": message_id,
                },
            )

            # Build output
            output = TriageStatusOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to send triage status notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "error": str(e),
                },
            )
            raise PatientAccessException(
                message=_("Failed to send triage status notification"),
                details={
                    "patient_id": input_data.patient_id,
                    "error": str(e),
                },
            ) from e

    @staticmethod
    def _get_priority_label(triage_level: int) -> str:
        """
        Get human-readable priority label from triage level.

        Args:
            triage_level: Triage classification level (1-5)

        Returns:
            Priority label in Portuguese

        Raises:
            ValueError: If triage level is invalid
        """
        priority_map = {
            1: "Emergência",
            2: "Muito Urgente",
            3: "Urgente",
            4: "Pouco Urgente",
            5: "Não Urgente",
        }

        label = priority_map.get(triage_level)
        if label is None:
            raise ValueError(f"Invalid triage level: {triage_level}")

        return label
