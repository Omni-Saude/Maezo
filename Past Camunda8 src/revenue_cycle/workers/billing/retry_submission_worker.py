"""
RetrySubmissionWorker - Camunda 8 External Task Worker.

Retries failed TISS claim submissions with exponential backoff:
- Exponential backoff strategy (1s, 2s, 4s)
- Configurable max retry attempts (default 3)
- Compensation event creation when max retries exceeded
- Comprehensive error logging and state tracking

This worker handles transient failures in TISS claim submission.

Business Rule: RN-BIL-005-RetrySubmission.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00
Migrated from: com.hospital.revenuecycle.delegates.RetrySubmissionDelegate

Section references:
- Transient failure handling and retry logic
- Exponential backoff configuration
- Compensation event triggers
- Error state management

BPMN Task: Task_Retry_Submission in SUB_06_Billing_Submission
Zeebe Topic: retry-submission
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from revenue_cycle.domain.exceptions import (
    BpmnErrorException,
    BusinessRuleException,
)
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.billing.models import (
    RetrySubmissionInput,
    RetrySubmissionOutput,
)

logger = structlog.get_logger(__name__)


# Custom exceptions for retry submission
class MaxRetriesExceededError(BusinessRuleException):
    """Raised when maximum retry attempts exceeded."""

    def __init__(self, claim_id: str, retry_count: int, max_retries: int):
        super().__init__(
            message=(
                f"Maximum retry attempts exceeded for claim {claim_id}: "
                f"attempted {retry_count} times, max allowed {max_retries}"
            ),
            rule_name="MAX_RETRIES",
            code="MAX_RETRIES_EXCEEDED",
            details={
                "claim_id": claim_id,
                "retry_count": retry_count,
                "max_retries": max_retries,
            },
        )


class InvalidRetryStateError(BusinessRuleException):
    """Raised when retry state is invalid."""

    def __init__(self, claim_id: str, message: str):
        super().__init__(
            message=f"Invalid retry state for claim {claim_id}: {message}",
            rule_name="INVALID_RETRY_STATE",
            code="INVALID_RETRY_STATE",
            details={"claim_id": claim_id},
        )


@worker(
    topic="retry-submission",
    lock_duration=60000,  # 60 seconds
    max_jobs=16,
)
class RetrySubmissionWorker(BaseWorker):
    """
    Zeebe worker for retrying failed TISS claim submissions.

    Implements exponential backoff strategy with configurable retry limits.
    When max retries exceeded, creates compensation event for error handling.

    Input Variables:
        claimId: Identifier of claim to retry
        previousError: Error from previous submission attempt
        retryCount: Current retry attempt number (0-based)
        maxRetries: Maximum retry attempts allowed (default 3)

    Output Variables:
        retryStatus: Status of retry (PENDING|SUCCESS|FAILED|MAX_RETRIES)
        nextRetryAt: ISO timestamp for next retry attempt
        finalStatus: Final status after all retries (only if final)
        retryAttempt: Current retry attempt number
        backoffSeconds: Seconds waited for this retry

    BPMN Errors:
        MAX_RETRIES_EXCEEDED: All retry attempts exhausted
        INVALID_RETRY_STATE: Invalid input data
    """

    # Exponential backoff delays (seconds): 1, 2, 4, 8, 16...
    BACKOFF_BASE = 1  # Start with 1 second
    BACKOFF_MULTIPLIER = 2  # Double each time

    def __init__(self, settings: Any = None, **kwargs: Any):
        """
        Initialize the worker.

        Args:
            settings: Application settings
            **kwargs: Additional arguments for BaseWorker
        """
        super().__init__(settings=settings)
        self._logger = logger.bind(worker=self.worker_name)

    @property
    def operation_name(self) -> str:
        """Get the operation name for idempotency and logging."""
        return "retry_submission"

    @property
    def requires_idempotency(self) -> bool:
        """
        Retry submission requires idempotency checking.

        Same claim + same retry count = same result.
        """
        return True

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the retry-submission task.

        Main processing flow:
        1. Parse and validate input variables
        2. Validate retry state and attempt count
        3. Calculate next retry delay (exponential backoff)
        4. Determine if this is final attempt
        5. Build output with retry status and timing
        6. Return compensation event if max retries exceeded

        Args:
            job: Camunda external task
            variables: Job variables from the process

        Returns:
            WorkerResult with retry timing and status

        Raises:
            MaxRetriesExceededError: If max retries exceeded
            InvalidRetryStateError: If input is invalid
        """
        job_key = str(getattr(job, "key", "unknown"))

        self._logger.info(
            "Starting submission retry",
            job_key=job_key,
        )

        try:
            # 1. Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Processing retry",
                claim_id=input_data.claim_id,
                retry_count=input_data.retry_count,
                max_retries=input_data.max_retries,
                previous_error=input_data.previous_error,
            )

            # 2. Validate retry state
            self._validate_retry_state(input_data)

            # 3. Calculate backoff delay
            backoff_seconds = self._calculate_backoff(input_data.retry_count)

            # 4. Calculate next retry time
            now = datetime.utcnow()
            next_retry_at = now + timedelta(seconds=backoff_seconds)

            # 5. Determine if this is final attempt
            is_final_attempt = input_data.retry_count >= (
                input_data.max_retries - 1
            )

            # 6. Determine retry status
            if is_final_attempt:
                retry_status = "PENDING_FINAL"
            else:
                retry_status = "PENDING"

            # 7. Build output
            output = RetrySubmissionOutput(
                retry_status=retry_status,
                next_retry_at=next_retry_at,
                retry_attempt=input_data.retry_count + 1,
                backoff_seconds=backoff_seconds,
                is_final_attempt=is_final_attempt,
                claim_id=input_data.claim_id,
                max_retries=input_data.max_retries,
            )

            self._logger.info(
                "Retry scheduled successfully",
                claim_id=input_data.claim_id,
                retry_attempt=output.retry_attempt,
                backoff_seconds=backoff_seconds,
                next_retry_at=str(next_retry_at),
                is_final=is_final_attempt,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except MaxRetriesExceededError as e:
            self._logger.warning(
                "Maximum retries exceeded",
                claim_id=variables.get("claimId"),
                details=e.details,
            )
            # Return compensation event to trigger error handling
            return WorkerResult.bpmn_error(
                error_code="MAX_RETRIES_EXCEEDED",
                error_message=str(e),
                variables=e.details,
            )

        except InvalidRetryStateError as e:
            self._logger.warning(
                "Invalid retry state",
                claim_id=variables.get("claimId"),
                details=e.details,
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_RETRY_STATE",
                error_message=str(e),
                variables=e.details,
            )

        except Exception as e:
            self._logger.exception(
                "Retry submission failed",
                error=str(e),
            )
            raise

    def _parse_input(self, variables: dict[str, Any]) -> RetrySubmissionInput:
        """
        Parse and validate input variables.

        Args:
            variables: Job variables

        Returns:
            Validated input model

        Raises:
            BpmnErrorException: If validation fails
        """
        try:
            return RetrySubmissionInput.model_validate(variables)
        except Exception as e:
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid input data: {e}",
            )

    def _validate_retry_state(self, input_data: RetrySubmissionInput) -> None:
        """
        Validate retry state and constraints.

        Args:
            input_data: Parsed input

        Raises:
            MaxRetriesExceededError: If retries exhausted
            InvalidRetryStateError: If state is invalid
        """
        # Validate retry count is within bounds
        if input_data.retry_count < 0:
            raise InvalidRetryStateError(
                input_data.claim_id,
                f"Retry count cannot be negative: {input_data.retry_count}",
            )

        # Validate max retries is positive
        if input_data.max_retries <= 0:
            raise InvalidRetryStateError(
                input_data.claim_id,
                f"Max retries must be positive: {input_data.max_retries}",
            )

        # Check if max retries already exceeded
        if input_data.retry_count >= input_data.max_retries:
            raise MaxRetriesExceededError(
                input_data.claim_id,
                input_data.retry_count,
                input_data.max_retries,
            )

        self._logger.debug(
            "Retry state validated",
            claim_id=input_data.claim_id,
            retry_count=input_data.retry_count,
            max_retries=input_data.max_retries,
        )

    def _calculate_backoff(self, retry_count: int) -> int:
        """
        Calculate exponential backoff delay in seconds.

        Uses formula: base * (multiplier ^ retry_count)
        Examples:
        - retry 0: 1 second
        - retry 1: 2 seconds
        - retry 2: 4 seconds
        - retry 3: 8 seconds

        Args:
            retry_count: Current retry attempt (0-based)

        Returns:
            Backoff delay in seconds
        """
        delay = self.BACKOFF_BASE * (
            self.BACKOFF_MULTIPLIER ** retry_count
        )

        self._logger.debug(
            "Backoff calculated",
            retry_count=retry_count,
            backoff_seconds=delay,
        )

        return delay

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Uses claim_id and retry_count for deterministic key.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        claim_id = variables.get("claimId", "")
        retry_count = variables.get("retryCount", 0)
        process_instance = variables.get("processInstanceKey", "")
        return f"{process_instance}:{claim_id}:{retry_count}"


# Worker registration function for use with Zeebe client
def create_retry_submission_worker(
    settings: Any = None,
) -> RetrySubmissionWorker:
    """
    Factory function to create RetrySubmissionWorker.

    Args:
        settings: Optional application settings

    Returns:
        Configured worker instance
    """
    return RetrySubmissionWorker(settings=settings)
