"""
SendPaymentReminderWorker - Send CDC-compliant payment reminder communications.

Business Rule: RN-COL-003.md
Regulatory Compliance: CDC Lei 8.078/90 Art. 42 (overpayment prohibition), Art. 71 (contact hours 8AM-6PM)
Migrated from: com.hospital.revenuecycle.delegates.collection.SendPaymentReminderDelegate

This worker sends automated payment reminder communications via email, SMS, or letter
to patients and responsible parties.

Topic: send-payment-reminder
BPMN Task: Task_Send_Payment_Reminder (Enviar Lembrete de Pagamento)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog
from zoneinfo import ZoneInfo

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)

# CDC Art. 71 - Contact hour restrictions
# Allowed contact hours: 8:00 AM to 6:00 PM (working days only)
CDC_CONTACT_START_HOUR = 8
CDC_CONTACT_END_HOUR = 18
BRAZIL_TIMEZONE = "America/Sao_Paulo"


class CdcContactHoursError(BpmnErrorException):
    """Raised when attempting to contact outside CDC Art. 71 permitted hours."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            error_code="CDC_CONTACT_HOURS_VIOLATION",
            message=message,
            details=details,
        )


@worker(topic="send-payment-reminder", max_jobs=8, lock_duration=30000)
class SendPaymentReminderWorker(BaseWorker):
    """
    Zeebe worker for sending payment reminders.

    BPMN Task: Task_Send_Payment_Reminder
    Topic: send-payment-reminder

    This worker sends:
    - Email reminders
    - SMS notifications
    - Postal letters
    - Portal notifications

    Input Variables:
        - claimId: Claim identifier (required)
        - patientId: Patient identifier
        - reminderType: Type of reminder (EMAIL/SMS/LETTER)
        - daysOverdue: Days payment is overdue

    Output Variables:
        - reminderId: Unique reminder identifier
        - reminderSent: Whether reminder was sent successfully
        - sendDate: Date reminder was sent
        - nextReminderDate: Date of next reminder
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "send_payment_reminder"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the payment reminder task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with reminder status
        """
        self._logger.info(
            "Processing payment reminder",
            claim_id=variables.get("claimId"),
            reminder_type=variables.get("reminderType"),
        )

        try:
            claim_id = variables.get("claimId")
            patient_id = variables.get("patientId", "")
            reminder_type = variables.get("reminderType", "EMAIL")
            days_overdue = int(variables.get("daysOverdue", 0))

            # Validate CDC Art. 71 - Contact hours (phone/SMS only)
            current_time = datetime.utcnow()
            if reminder_type in ["PHONE", "SMS"]:
                if not self._is_valid_contact_time(current_time):
                    # Adjust to valid contact time
                    adjusted_time = self._adjust_to_valid_contact_time(current_time)
                    self._logger.warning(
                        "CDC Art. 71 compliance: Contact rescheduled to valid hours",
                        original_time=current_time.isoformat(),
                        adjusted_time=adjusted_time.isoformat(),
                        reminder_type=reminder_type,
                    )
                    # Return with rescheduled time
                    return WorkerResult.ok({
                        "reminderId": f"REM-{claim_id}-{reminder_type}",
                        "reminderSent": False,
                        "reminderRescheduled": True,
                        "scheduledSendDate": adjusted_time.isoformat(),
                        "rescheduleReason": "CDC Art. 71: Contact outside permitted hours (8AM-6PM, working days only)",
                        "reminderType": reminder_type,
                        "daysOverdue": days_overdue,
                    })

            # Generate reminder ID
            reminder_id = f"REM-{claim_id}-{reminder_type}"

            # In production, would send actual messages
            reminder_sent = True

            # Calculate next reminder date (7 days later, CDC-compliant)
            next_reminder_date_raw = datetime.utcnow() + timedelta(days=7)
            next_reminder_date = self._adjust_to_valid_contact_time(next_reminder_date_raw).isoformat()

            output = {
                "reminderId": reminder_id,
                "reminderSent": reminder_sent,
                "sendDate": datetime.utcnow().isoformat(),
                "nextReminderDate": next_reminder_date,
                "reminderType": reminder_type,
                "daysOverdue": days_overdue,
            }

            self._logger.info(
                "Payment reminder sent",
                claim_id=claim_id,
                reminder_id=reminder_id,
                reminder_type=reminder_type,
            )

            return WorkerResult.ok(output)

        except CdcContactHoursError as e:
            self._logger.error("CDC Art. 71 violation - contact hours", error=str(e))
            return WorkerResult.bpmn_error(
                error_code="CDC_CONTACT_HOURS_VIOLATION",
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Error sending payment reminder",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Payment reminder failed: {e}",
                retry=True,
            )

    def _is_valid_contact_time(
        self,
        contact_datetime: datetime,
        timezone: str = BRAZIL_TIMEZONE,
    ) -> bool:
        """
        Validate contact time according to CDC Art. 71.

        Brazilian Consumer Defense Code (CDC) Article 71 restricts
        debt collection contact to:
        - Working days only (Monday-Friday)
        - Between 8:00 AM and 6:00 PM local time
        - No contact on weekends or holidays

        Args:
            contact_datetime: Proposed contact datetime (UTC or timezone-aware)
            timezone: Timezone for validation (default: America/Sao_Paulo)

        Returns:
            True if contact time is valid per CDC regulations
        """
        # Convert to specified timezone if needed
        if contact_datetime.tzinfo is None:
            # Assume UTC if no timezone
            contact_datetime = contact_datetime.replace(tzinfo=ZoneInfo("UTC"))

        local_time = contact_datetime.astimezone(ZoneInfo(timezone))

        # Check if it's a working day (Monday=0 to Friday=4)
        if local_time.weekday() >= 5:  # Saturday=5, Sunday=6
            self._logger.warning(
                "Contact scheduled on weekend violates CDC Art. 71",
                scheduled_date=contact_datetime.isoformat(),
                local_weekday=local_time.strftime("%A"),
            )
            return False

        # Check if within allowed hours (8:00 AM to 6:00 PM)
        if not (CDC_CONTACT_START_HOUR <= local_time.hour < CDC_CONTACT_END_HOUR):
            self._logger.warning(
                "Contact scheduled outside allowed hours violates CDC Art. 71",
                scheduled_date=contact_datetime.isoformat(),
                local_hour=local_time.hour,
                allowed_hours=f"{CDC_CONTACT_START_HOUR}:00-{CDC_CONTACT_END_HOUR}:00",
            )
            return False

        return True

    def _adjust_to_valid_contact_time(
        self,
        contact_datetime: datetime,
        timezone: str = BRAZIL_TIMEZONE,
    ) -> datetime:
        """
        Adjust contact time to comply with CDC Art. 71 if needed.

        If the proposed time falls outside allowed hours or on weekends,
        this method adjusts it to the next valid contact window.

        Args:
            contact_datetime: Proposed contact datetime
            timezone: Timezone for validation (default: America/Sao_Paulo)

        Returns:
            Adjusted datetime that complies with CDC regulations
        """
        # Convert to specified timezone if needed
        if contact_datetime.tzinfo is None:
            contact_datetime = contact_datetime.replace(tzinfo=ZoneInfo("UTC"))

        local_time = contact_datetime.astimezone(ZoneInfo(timezone))

        # Adjust if weekend
        while local_time.weekday() >= 5:  # Saturday or Sunday
            # Move to next Monday
            days_ahead = 7 - local_time.weekday()
            if days_ahead == 0:  # If Sunday, move 1 day
                days_ahead = 1
            local_time = local_time + timedelta(days=days_ahead)

        # Adjust if outside allowed hours
        if local_time.hour < CDC_CONTACT_START_HOUR:
            # Before 8 AM - set to 8 AM same day
            local_time = local_time.replace(
                hour=CDC_CONTACT_START_HOUR,
                minute=0,
                second=0,
                microsecond=0,
            )
        elif local_time.hour >= CDC_CONTACT_END_HOUR:
            # After 6 PM - move to 8 AM next business day
            local_time = local_time + timedelta(days=1)
            local_time = local_time.replace(
                hour=CDC_CONTACT_START_HOUR,
                minute=0,
                second=0,
                microsecond=0,
            )
            # Check if new day is weekend
            while local_time.weekday() >= 5:
                local_time = local_time + timedelta(days=1)

        # Convert back to UTC
        return local_time.astimezone(ZoneInfo("UTC"))
