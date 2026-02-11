"""
Doctor Patient Arrival Worker

CIB7 External Task Topic: scheduling.patient_arrival
BPMN Error Code: PATIENT_ACCESS_ERROR

Notifies doctor when patient checks in for scheduled appointment.
Message: 'Patient [Name] arrived for your [Time] appointment at [Location]'
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

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


class DoctorPatientArrivalInput(BaseModel):
    """Input variables for doctor patient arrival notification."""

    doctor_id: str = Field(..., description="FHIR Practitioner ID")
    patient_id: str = Field(..., description="FHIR Patient ID")
    appointment_id: str = Field(..., description="FHIR Appointment ID")
    appointment_time: str = Field(..., description="HH:MM format")
    location: str = Field(..., description="Facility/clinic location")
    phone_number: str = Field(..., description="Doctor phone E.164")
    patient_name: str = Field(
        default="Paciente", description="Patient display name for notification"
    )


class DoctorPatientArrivalOutput(BaseModel):
    """Output variables for doctor patient arrival notification."""

    notification_sent: bool
    message_id: str | None
    sent_at: str = Field(..., description="ISO 8601 timestamp")


class DoctorPatientArrivalWorker:
    """
    Worker that notifies doctors when patients arrive for appointments.

    Processes scheduling.patient_arrival tasks from CIB7.
    Sends WhatsApp notification to doctor with patient arrival details.
    """

    TOPIC = "scheduling.patient_arrival"

    def __init__(self, whatsapp_client: WhatsAppClientProtocol | None = None):
        """
        Initialize worker with WhatsApp client.

        Args:
            whatsapp_client: WhatsApp client for sending messages.
                           Defaults to StubWhatsAppClient for testing.
        """
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="scheduling.patient_arrival")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute patient arrival notification task.

        Args:
            task_variables: Task variables from CIB7 containing appointment details.

        Returns:
            dict containing notification_sent, message_id, and sent_at.

        Raises:
            PatientAccessException: If required fields are missing or notification fails.
        """
        tenant_ctx = get_required_tenant()

        # Validate and parse input
        try:
            input_data = DoctorPatientArrivalInput(**task_variables)
        except Exception as e:
            logger.error(
                "Invalid input for patient arrival notification",
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "error": str(e),
                    "has_appointment_id": "appointment_id" in task_variables,
                },
            )
            raise PatientAccessException(
                message=_("Invalid input for patient arrival notification"),
                details={"error": str(e)},
            ) from e

        # Validate required fields
        if not input_data.appointment_id:
            raise PatientAccessException(
                message=_("Missing required field: appointment_id"),
                details={"field": "appointment_id"},
            )

        logger.info(
            "Processing patient arrival notification",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "doctor_id": input_data.doctor_id,
                "patient_id": input_data.patient_id,
                "appointment_id": input_data.appointment_id,
                "location": input_data.location,
                # LGPD: NEVER log phone_number
            },
        )

        # Prepare WhatsApp template
        template = WhatsAppTemplate(
            name="patient_arrival_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": input_data.patient_name},
                        {"type": "text", "text": input_data.appointment_time},
                        {"type": "text", "text": input_data.location},
                    ],
                }
            ],
        )

        # Send notification
        try:
            message_id = await self.whatsapp_client.send_template_message(
                phone_number=input_data.phone_number, template=template
            )

            sent_at = datetime.now(timezone.utc).isoformat()

            logger.info(
                "Patient arrival notification sent successfully",
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "doctor_id": input_data.doctor_id,
                    "appointment_id": input_data.appointment_id,
                    "message_id": message_id,
                },
            )

            output = DoctorPatientArrivalOutput(
                notification_sent=True, message_id=message_id, sent_at=sent_at
            )
            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to send patient arrival notification",
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "doctor_id": input_data.doctor_id,
                    "appointment_id": input_data.appointment_id,
                    "error": str(e),
                },
            )
            raise PatientAccessException(
                message=_("Failed to send patient arrival notification"),
                details={
                    "doctor_id": input_data.doctor_id,
                    "appointment_id": input_data.appointment_id,
                    "error": str(e),
                },
            ) from e
