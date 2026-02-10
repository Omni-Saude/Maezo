"""
Send Reminder Notification Worker

CIB7 External Task Topic: scheduling.send_reminder
BPMN Error Code: PATIENT_ACCESS_ERROR

Sends WhatsApp reminders at 24h and 1h before appointment.
Includes interactive buttons for confirmation/cancellation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from pydantic import BaseModel, Field

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
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


class WhatsAppClientProtocol(Protocol):
    """Protocol for WhatsApp messaging client."""

    async def send_interactive_message(
        self,
        phone_number: str,
        template_name: str,
        language_code: str,
        parameters: dict[str, Any],
        buttons: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Send an interactive message with buttons via WhatsApp."""
        ...


class SendReminderNotificationInput(BaseModel):
    """Input DTO for reminder notification."""

    appointment_id: str = Field(..., description="FHIR Appointment ID")
    patient_id: str = Field(..., description="FHIR Patient ID")
    phone_number: str = Field(..., description="Patient phone number (E.164 format)")
    appointment_date: str = Field(..., description="Appointment date (ISO 8601)")
    appointment_time: str = Field(..., description="Appointment time (HH:MM)")
    location_name: str = Field(..., description="Facility/clinic name")
    doctor_name: str = Field(..., description="Doctor's full name")
    reminder_type: str = Field(
        ..., description="Reminder type (24h_before or 1h_before)"
    )
    enable_interactive_buttons: bool = Field(
        default=True, description="Whether to include confirm/cancel buttons"
    )


class SendReminderNotificationOutput(BaseModel):
    """Output DTO for reminder notification."""

    reminder_sent: bool = Field(..., description="Whether reminder was sent")
    message_id: str | None = Field(None, description="Message ID from provider")
    sent_at: str = Field(..., description="Timestamp of sending (ISO 8601)")
    reminder_type: str = Field(..., description="Type of reminder sent")
    delivery_status: str = Field(
        default="sent", description="Delivery status (sent, delivered, failed)"
    )
    interactive_enabled: bool = Field(
        ..., description="Whether interactive buttons were included"
    )
    error_message: str | None = Field(None, description="Error message if failed")


class ReminderNotificationSenderProtocol(ABC):
    """Protocol for sending reminder notifications."""

    @abstractmethod
    async def send_reminder(
        self,
        appointment_id: str,
        patient_id: str,
        phone_number: str,
        reminder_details: dict[str, Any],
        reminder_type: str,
        enable_interactive: bool,
    ) -> dict[str, Any]:
        """
        Send reminder notification to patient.

        Args:
            appointment_id: FHIR Appointment ID
            patient_id: FHIR Patient ID
            phone_number: Patient phone number (E.164 format)
            reminder_details: Reminder details for template
            reminder_type: Type of reminder (24h_before or 1h_before)
            enable_interactive: Whether to include interactive buttons

        Returns:
            Dictionary with reminder status
        """
        pass


class StubReminderNotificationSender(ReminderNotificationSenderProtocol):
    """Stub implementation for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()
        # DMN integration point: auth_timing_008
        # Inputs: {'appointment_id': appointment_id, 'reminder_type': reminder_type}
        # Call: self.dmn_service.evaluate(tenant_id=..., category='authorization', table_name='auth_timing_008', inputs={...})


    def __init__(self):
        self.logger = get_logger(__name__, worker="scheduling.send_reminder")

    async def send_reminder(
        self,
        appointment_id: str,
        patient_id: str,
        phone_number: str,
        reminder_details: dict[str, Any],
        reminder_type: str,
        enable_interactive: bool,
    ) -> dict[str, Any]:
        """Stub implementation - logs and returns success."""
        # NEVER log phone numbers for LGPD compliance
        self.logger.info(
            "stub_reminder_sent",
            appointment_id=appointment_id,
            patient_id=patient_id,
            reminder_type=reminder_type,
            interactive_enabled=enable_interactive,
            phone_masked=f"***{phone_number[-4:]}" if len(phone_number) > 4 else "****",
        )

        from datetime import datetime, timezone

        return {
            "reminder_sent": True,
            "message_id": f"stub_reminder_{appointment_id}_{reminder_type}",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "reminder_type": reminder_type,
            "delivery_status": "sent",
            "interactive_enabled": enable_interactive,
            "error_message": None,
        }


class SendReminderNotificationWorker:
    """Worker to send appointment reminder notifications."""

    TOPIC = "scheduling.send_reminder"

    def __init__(
        self,
        reminder_sender: ReminderNotificationSenderProtocol | None = None,
    ):
        """
        Initialize worker.

        Args:
            reminder_sender: Service to send reminders (defaults to stub)
        """
        self.reminder_sender = reminder_sender or StubReminderNotificationSender()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(task_type="scheduling.send_reminder")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute reminder notification sending.

        Args:
            task_variables: Task variables from CIB7 process

        Returns:
            Dictionary with reminder status

        Raises:
            PatientAccessException: If reminder fails
        """
        tenant_id = get_required_tenant()

        try:
            # Parse and validate input
            input_data = SendReminderNotificationInput(**task_variables)

            self.logger.info(
                "sending_reminder_notification",
                tenant_id=tenant_id,
                appointment_id=input_data.appointment_id,
                patient_id=input_data.patient_id,
                reminder_type=input_data.reminder_type,
            )

            # Prepare reminder details for template
            reminder_details = {
                "appointment_date": input_data.appointment_date,
                "appointment_time": input_data.appointment_time,
                "location_name": input_data.location_name,
                "doctor_name": input_data.doctor_name,
                "reminder_message": self._get_reminder_message(input_data.reminder_type),
            }

            # Send reminder
            result = await self.reminder_sender.send_reminder(
                appointment_id=input_data.appointment_id,
                patient_id=input_data.patient_id,
                phone_number=input_data.phone_number,
                reminder_details=reminder_details,
                reminder_type=input_data.reminder_type,
                enable_interactive=input_data.enable_interactive_buttons,
            )

            # Validate output
            output = SendReminderNotificationOutput(**result)

            self.logger.info(
                "reminder_notification_sent",
                tenant_id=tenant_id,
                appointment_id=input_data.appointment_id,
                message_id=output.message_id,
                reminder_type=output.reminder_type,
                delivery_status=output.delivery_status,
                interactive_enabled=output.interactive_enabled,
            )

            return output.model_dump()

        except Exception as e:
            self.logger.error(
                "reminder_notification_failed",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PatientAccessException(
                message=_("Falha ao enviar lembrete de agendamento: {error}").format(
                    error=str(e)
                ),
                details={
                    "appointment_id": task_variables.get("appointment_id"),
                    "patient_id": task_variables.get("patient_id"),
                    "reminder_type": task_variables.get("reminder_type"),
                    "error_type": type(e).__name__,
                },
            ) from e

    def _get_reminder_message(self, reminder_type: str) -> str:
        """Get appropriate reminder message based on type."""
        messages = {
            "24h_before": _(
                "Lembrete: Sua consulta está agendada para amanhã. "
                "Confirme sua presença ou cancele se necessário."
            ),
            "1h_before": _(
                "Lembrete: Sua consulta está agendada para daqui a 1 hora. "
                "Não se esqueça de trazer seus documentos e exames."
            ),
        }

        return messages.get(
            reminder_type,
            _("Lembrete: Você tem uma consulta agendada em breve."),
        )
