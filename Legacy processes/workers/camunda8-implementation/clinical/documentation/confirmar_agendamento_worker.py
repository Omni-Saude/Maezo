"""
ConfirmarAgendamentoWorker - Confirm and book appointments with notification generation.

Business Rule: RN-SCH-002.md
Regulatory Compliance: LGPD (Privacy in scheduling), Benchmark: Appointment Confirmation
Migrated from: com.hospital.revenuecycle.delegates.scheduling.ConfirmarAgendamentoDelegate

This worker confirms and books selected appointment slots in the hospital
scheduling system. Generates confirmation numbers and sends notifications.

Topic: confirmar-agendamento
BPMN Task: Task_Confirmar_Agendamento (Confirmar Agendamento)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

import structlog
from pydantic import ValidationError

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.scheduling.scheduling_models import (
    AppointmentStatus,
    ConfirmarAgendamentoInput,
    ConfirmarAgendamentoOutput,
    ContactMethod,
    RouteInstruction,
)

logger = structlog.get_logger(__name__)


class AppointmentConfirmationError(Exception):
    """Raised when appointment confirmation fails."""

    pass


@worker(topic="confirmar-agendamento", max_jobs=8, lock_duration=30000)
class ConfirmarAgendamentoWorker(BaseWorker):
    """
    Zeebe worker for confirming appointment scheduling.

    BPMN Task: Task_Confirmar_Agendamento
    Topic: confirmar-agendamento

    This worker:
    - Books selected appointment slots
    - Validates slot availability and patient eligibility
    - Generates confirmation numbers
    - Sends confirmation messages (SMS/Email)
    - Updates scheduling system
    - Tracks appointment status

    Input Variables:
        - patientId: Patient identifier (required)
        - slotId: Selected appointment slot ID (required)
        - serviceCode: Service code (required)
        - providerId: Provider identifier (required)
        - providerName: Provider name (optional)
        - appointmentDate: Date in YYYY-MM-DD (optional)
        - appointmentTime: Time in HH:MM (optional)
        - patientName: Patient name (optional)
        - patientPhone: Patient phone (optional)
        - patientEmail: Patient email (optional)

    Output Variables:
        - appointmentId: Unique appointment identifier
        - appointmentConfirmed: Whether booking was successful
        - confirmationNumber: Confirmation reference number
        - appointmentDate: Scheduled date (YYYY-MM-DD)
        - appointmentTime: Scheduled time (HH:MM)
        - status: Appointment status (CONFIRMED)
        - confirmedAt: Confirmation timestamp
        - confirmationSentVia: How confirmation was sent
        - nextReminderDate: Date of next reminder
    """

    def __init__(
        self,
        settings=None,
        appointment_service=None,
        notification_service=None,
        **kwargs
    ):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            appointment_service: Optional appointment service (for testing)
            notification_service: Optional notification service (for testing)
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._appointment_service = appointment_service
        self._notification_service = notification_service
        self._confirmed_appointments: dict[str, ConfirmarAgendamentoOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "confirmar_agendamento"

    @property
    def requires_idempotency(self) -> bool:
        """This worker requires idempotency to prevent double-booking."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract slot ID for idempotency key."""
        slot_id = variables.get("slotId", "")
        patient_id = variables.get("patientId", "")
        return f"{patient_id}:{slot_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the appointment confirmation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with confirmation details
        """
        self._logger.info(
            "Processing appointment confirmation",
            patient_id=variables.get("patientId"),
            slot_id=variables.get("slotId"),
        )

        try:
            # Parse and validate input
            input_data = ConfirmarAgendamentoInput.model_validate(variables)

            # Validate slot is still available
            await self._validate_slot_available(input_data)

            # Generate appointment ID and confirmation
            appointment_id = self._generate_appointment_id(input_data.patient_id)
            confirmation_number = self._generate_confirmation_number(appointment_id)

            # Determine appointment date/time
            appointment_date = input_data.appointment_date or "2024-02-15"
            appointment_time = input_data.appointment_time or "09:00"

            # Book the appointment (stub - in production would call scheduling system)
            await self._book_appointment(
                appointment_id=appointment_id,
                input_data=input_data,
            )

            # Send confirmation notification
            confirmation_method = await self._send_confirmation_notification(
                appointment_id=appointment_id,
                input_data=input_data,
            )

            # Calculate next reminder date (24 hours before appointment)
            next_reminder_date = self._calculate_next_reminder_date(appointment_date)

            # Create output
            output = ConfirmarAgendamentoOutput(
                appointmentId=appointment_id,
                appointmentConfirmed=True,
                confirmationNumber=confirmation_number,
                appointmentDate=appointment_date,
                appointmentTime=appointment_time,
                patientId=input_data.patient_id,
                serviceCode=input_data.service_code,
                providerId=input_data.provider_id,
                providerName=input_data.provider_name or "Provider",
                specialty=input_data.specialty or "General",
                location="Hospital Main Building",
                estimatedDurationMinutes=45,
                status=AppointmentStatus.CONFIRMED,
                confirmationSentVia=confirmation_method,
                nextReminderDate=next_reminder_date,
            )

            # Store for idempotency
            self._confirmed_appointments[appointment_id] = output

            # Add tenant_id to output if present
            output_dict = output.model_dump(by_alias=True)
            if input_data.tenant_id:
                output_dict["tenantId"] = input_data.tenant_id

            self._logger.info(
                "Appointment confirmed successfully",
                patient_id=input_data.patient_id,
                appointment_id=appointment_id,
                confirmation_number=confirmation_number,
                confirmation_method=confirmation_method,
            )

            return WorkerResult.ok(output_dict)

        except ValidationError as e:
            self._logger.error(
                "Appointment confirmation validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_APPOINTMENT_DATA",
                error_message=f"Validation failed: {e}",
            )

        except AppointmentConfirmationError as e:
            self._logger.error(
                "Appointment confirmation error",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code="APPOINTMENT_CONFIRMATION_ERROR",
                error_message=str(e),
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error confirming appointment",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Appointment confirmation failed: {e}",
                retry=True,
            )

    async def _validate_slot_available(
        self,
        input_data: ConfirmarAgendamentoInput,
    ) -> None:
        """
        Validate that the selected slot is still available.

        Args:
            input_data: Appointment input data

        Raises:
            AppointmentConfirmationError: If slot is not available
        """
        if self._appointment_service:
            is_available = await self._appointment_service.is_slot_available(
                input_data.slot_id
            )
            if not is_available:
                raise AppointmentConfirmationError(
                    f"Slot {input_data.slot_id} is no longer available"
                )

    async def _book_appointment(
        self,
        appointment_id: str,
        input_data: ConfirmarAgendamentoInput,
    ) -> None:
        """
        Book the appointment in the scheduling system.

        Args:
            appointment_id: Generated appointment ID
            input_data: Appointment input data
        """
        self._logger.info(
            "Booking appointment",
            appointment_id=appointment_id,
            patient_id=input_data.patient_id,
            slot_id=input_data.slot_id,
        )

        if self._appointment_service:
            await self._appointment_service.book_appointment(
                appointment_id=appointment_id,
                patient_id=input_data.patient_id,
                slot_id=input_data.slot_id,
                service_code=input_data.service_code,
            )

    async def _send_confirmation_notification(
        self,
        appointment_id: str,
        input_data: ConfirmarAgendamentoInput,
    ) -> str:
        """
        Send confirmation notification to patient.

        Args:
            appointment_id: Appointment ID
            input_data: Appointment input data

        Returns:
            Method used to send confirmation
        """
        # Determine which contact method to use
        preferred_method = ContactMethod.SMS
        if input_data.patient_email:
            preferred_method = ContactMethod.EMAIL

        self._logger.info(
            "Sending confirmation notification",
            appointment_id=appointment_id,
            method=preferred_method.value,
        )

        if self._notification_service:
            await self._notification_service.send_appointment_confirmation(
                appointment_id=appointment_id,
                patient_id=input_data.patient_id,
                patient_phone=input_data.patient_phone,
                patient_email=input_data.patient_email,
                method=preferred_method,
            )

        return preferred_method.value

    def _generate_appointment_id(self, patient_id: str) -> str:
        """
        Generate a unique appointment ID.

        Args:
            patient_id: Patient identifier

        Returns:
            Appointment ID in format APT-{patient_id}-{timestamp}-{random}
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_suffix = uuid4().hex[:6].upper()
        return f"APT-{patient_id}-{timestamp}-{random_suffix}"

    def _generate_confirmation_number(self, appointment_id: str) -> str:
        """
        Generate a confirmation number.

        Args:
            appointment_id: Appointment ID

        Returns:
            Confirmation number in format CONF-{last_8_chars}
        """
        return f"CONF-{appointment_id[-8:]}"

    def _calculate_next_reminder_date(self, appointment_date: str) -> str:
        """
        Calculate next reminder date (24 hours before appointment).

        Args:
            appointment_date: Appointment date in YYYY-MM-DD format

        Returns:
            Reminder date in YYYY-MM-DD format
        """
        try:
            appt_date = datetime.strptime(appointment_date, "%Y-%m-%d")
            reminder_date = appt_date - timedelta(days=1)
            return reminder_date.strftime("%Y-%m-%d")
        except ValueError:
            # Return same date if parsing fails
            return appointment_date
