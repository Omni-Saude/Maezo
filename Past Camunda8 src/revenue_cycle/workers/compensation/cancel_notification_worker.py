"""
CancelNotificationWorker - SAGA compensation worker for canceling pending notifications.

This worker implements notification cancellation logic for transaction rollback:
- Cancels pending email/SMS/push notifications
- Marks notifications as cancelled
- Maintains audit trail
- Supports idempotency for safe retry

Business Rule: RN-COMP-NotificationCancel.md
SAGA Pattern: Compensation for notification task
Regulatory Compliance: GDPR (notification audit trail)
Migrated from: com.hospital.revenuecycle.delegates.compensation.CancelNotificationDelegate
Topic: compensate-cancel-notification
BPMN Compensation: Compensate Task_Send_Notification
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import structlog
from pydantic import ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.compensation.models import (
    CancelNotificationInput,
    CancelNotificationOutput,
    CompensationStatus,
)

logger = structlog.get_logger(__name__)


class NotificationCancellationError(BpmnErrorException):
    """Raised when notification cancellation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="NOTIFICATION_CANCELLATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-cancel-notification", max_jobs=32, lock_duration=30000)
class CancelNotificationWorker(BaseWorker):
    """
    SAGA compensation worker for canceling pending notifications.

    This worker cancels notifications by:
    1. Validating cancellation request
    2. Checking if already cancelled (idempotency)
    3. Attempting to cancel pending notification
    4. Marking notification as cancelled
    5. Creating cancellation audit record
    6. Handling already-sent notifications gracefully

    Input Variables:
        - notificationId: Notification ID to cancel (required)
        - recipient: Notification recipient (required)
        - notificationType: Type of notification (EMAIL/SMS/PUSH) (required)
        - reason: Compensation reason (required)

    Output Variables:
        - cancellationSuccess: Whether cancellation succeeded (boolean)
        - compensationStatus: Compensation operation status
        - cancellationDate: When cancellation was executed
        - wasAlreadySent: Whether notification was already sent (boolean)
        - errorMessage: Error message if failed (optional)

    SAGA Pattern:
        - This is a compensation handler for SendNotificationWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if notification not found (SKIPPED)
        - Should succeed if notification already sent (ALREADY_COMPENSATED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "notificationId": "NOTIF-001",
            "recipient": "patient@example.com",
            "notificationType": "EMAIL",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "cancellationSuccess": true,
            "compensationStatus": "SUCCESS",
            "cancellationDate": "2026-02-04T14:30:00Z",
            "wasAlreadySent": false
        }
    """

    def __init__(self, settings=None, notification_service=None, **kwargs):
        """
        Initialize the cancel notification worker.

        Args:
            settings: Optional worker settings
            notification_service: Optional notification service (for testing)
        """
        super().__init__(settings=settings)
        self._notification_service = notification_service
        self._cancellations: dict[str, CancelNotificationOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "cancel_notification"

    @property
    def requires_idempotency(self) -> bool:
        """Notification cancellation requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        notification_id = variables.get("notificationId", "")
        recipient = variables.get("recipient", "")
        return f"{notification_id}:{recipient}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process notification cancellation compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with cancellation outcome
        """
        self._logger.info(
            "Processing notification cancellation",
            job_key=str(getattr(job, "key", "unknown")),
            notification_id=variables.get("notificationId"),
            notification_type=variables.get("notificationType"),
        )

        try:
            # Parse and validate input
            input_data = CancelNotificationInput.model_validate(variables)

            # Check if already cancelled (idempotency)
            cache_key = f"{input_data.notification_id}:{input_data.recipient}"
            if cache_key in self._cancellations:
                cached = self._cancellations[cache_key]
                self._logger.info(
                    "Returning cached cancellation result",
                    notification_id=input_data.notification_id,
                )
                return WorkerResult.ok(cached.model_dump(by_alias=True))

            # Execute cancellation
            cancellation_result = await self._execute_cancellation(input_data)

            # Create audit trail entry
            await self._create_audit_trail(input_data, cancellation_result)

            # Cache result for idempotency
            self._cancellations[cache_key] = cancellation_result

            if cancellation_result.cancellation_success:
                self._logger.info(
                    "Notification cancellation completed successfully",
                    notification_id=input_data.notification_id,
                    status=cancellation_result.compensation_status.value,
                    was_already_sent=cancellation_result.was_already_sent,
                )
                return WorkerResult.ok(cancellation_result.model_dump(by_alias=True))
            else:
                self._logger.warning(
                    "Notification cancellation failed",
                    notification_id=input_data.notification_id,
                    error=cancellation_result.error_message,
                )
                return WorkerResult.ok(cancellation_result.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Notification cancellation validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_CANCELLATION_DATA",
                error_message=f"Cancellation validation failed: {e}",
            )

        except NotificationCancellationError as e:
            self._logger.error(
                "Notification cancellation error",
                error=str(e),
                error_code=e.error_code,
            )
            output = CancelNotificationOutput(
                cancellation_success=False,
                compensation_status=CompensationStatus.FAILED,
                cancellation_date=datetime.utcnow(),
                was_already_sent=False,
                error_message=e.message,
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Unexpected error during notification cancellation",
                error=str(e),
                exc_info=True,
            )
            output = CancelNotificationOutput(
                cancellation_success=False,
                compensation_status=CompensationStatus.FAILED,
                cancellation_date=datetime.utcnow(),
                was_already_sent=False,
                error_message=f"Unexpected error: {e}",
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

    async def _execute_cancellation(
        self,
        input_data: CancelNotificationInput,
    ) -> CancelNotificationOutput:
        """
        Execute notification cancellation.

        In production:
        - Query notification database for notification record
        - Check notification status (PENDING/SENT/FAILED)
        - If PENDING: Cancel in notification queue/service
        - If SENT: Mark as ALREADY_SENT (cannot cancel)
        - Update notification status to CANCELLED

        Args:
            input_data: Cancellation input data

        Returns:
            Cancellation output data
        """
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        # 1. Query notification database for notification record
        # 2. Check notification status:
        #    - PENDING: Attempt to cancel in queue (SQS, RabbitMQ, etc.)
        #    - SENT: Return success with wasAlreadySent=true
        #    - FAILED: Return success (nothing to cancel)
        # 3. For EMAIL: Cancel via email service (SendGrid, SES, etc.)
        # 4. For SMS: Cancel via SMS service (Twilio, SNS, etc.)
        # 5. For PUSH: Cancel via push notification service
        # 6. Update notification status to CANCELLED
        # 7. Create cancellation record

        # STUB: Simulate successful cancellation (assume pending)
        self._logger.info(
            "Executing notification cancellation (PRODUCTION: integrate notification service)",
            notification_id=input_data.notification_id,
            recipient=self._mask_recipient(input_data.recipient),
            notification_type=input_data.notification_type,
            reason=input_data.reason.value,
        )

        # Simulate: notification was still pending and cancelled
        was_already_sent = False

        return CancelNotificationOutput(
            cancellation_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            cancellation_date=datetime.utcnow(),
            was_already_sent=was_already_sent,
            error_message=None,
        )

    def _mask_recipient(self, recipient: str) -> str:
        """
        Mask recipient for logging (privacy protection).

        Args:
            recipient: Email, phone, or device ID

        Returns:
            Masked recipient
        """
        if "@" in recipient:
            # Email: show first 2 chars and domain
            parts = recipient.split("@")
            return f"{parts[0][:2]}***@{parts[1]}"
        elif len(recipient) > 4:
            # Phone/other: show first 2 and last 2
            return f"{recipient[:2]}***{recipient[-2:]}"
        return "***"

    async def _create_audit_trail(
        self,
        input_data: CancelNotificationInput,
        result: CancelNotificationOutput,
    ) -> None:
        """Create audit trail entry for cancellation operation."""
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        self._logger.info(
            "Notification cancellation audit trail created",
            notification_id=input_data.notification_id,
            recipient=self._mask_recipient(input_data.recipient),
            notification_type=input_data.notification_type,
            reason=input_data.reason.value,
            success=result.cancellation_success,
            was_already_sent=result.was_already_sent,
        )
