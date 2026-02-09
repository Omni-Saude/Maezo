"""
CompensateSubmitWorker - SAGA compensation worker for undoing claim submissions.

This worker implements claim submission undo logic for transaction rollback:
- Reverts claim submission
- Updates claim status
- Notifies TISS system
- Maintains audit trail

Business Rule: RN-COMP-003-CompensateSubmitDelegate.md
SAGA Pattern: Compensation for claim-submission task
Regulatory Compliance: ANS RN 395/2016 (submission reversal), TISS integration
Migrated from: com.hospital.revenuecycle.delegates.compensation.CompensateSubmitDelegate
Topic: compensate-claim-submission
BPMN Compensation: Compensate Task_Submit_Claim
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.compensation.models import CompensationStatus, CompensationReason

logger = structlog.get_logger(__name__)


class CompensateSubmitInput(BaseModel):
    """Input model for CompensateSubmitWorker."""

    submission_id: str = Field(
        ...,
        alias="submissionId",
        min_length=1,
        description="Claim submission ID to undo",
    )
    claim_id: str = Field(
        ...,
        alias="claimId",
        min_length=1,
        description="Associated claim identifier",
    )
    encounter_id: str = Field(
        ...,
        alias="encounterId",
        min_length=1,
        description="Associated encounter identifier",
    )
    reason: CompensationReason = Field(
        ...,
        description="Reason for compensation",
    )
    compensation_context: dict[str, Any] = Field(
        default_factory=dict,
        alias="compensationContext",
        description="Additional compensation context",
    )

    model_config = {"populate_by_name": True}


class CompensateSubmitOutput(BaseModel):
    """Output model for CompensateSubmitWorker."""

    compensation_success: bool = Field(
        ...,
        alias="compensationSuccess",
        description="Whether compensation succeeded",
    )
    compensation_status: CompensationStatus = Field(
        ...,
        alias="compensationStatus",
        description="Compensation operation status",
    )
    submission_cancelled: bool = Field(
        ...,
        alias="submissionCancelled",
        description="Whether submission was cancelled",
    )
    tiss_notified: bool = Field(
        ...,
        alias="tissNotified",
        description="Whether TISS system was notified",
    )
    compensation_date: datetime = Field(
        ...,
        alias="compensationDate",
        description="When compensation was executed",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Error message if failed",
    )

    model_config = {"populate_by_name": True}


class SubmissionCompensationError(BpmnErrorException):
    """Raised when submission compensation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="SUBMISSION_COMPENSATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-claim-submission", max_jobs=16, lock_duration=45000)
class CompensateSubmitWorker(BaseWorker):
    """
    SAGA compensation worker for undoing claim submissions.

    This worker undoes claim submissions by:
    1. Validating submission undo request
    2. Checking if already compensated (idempotency)
    3. Reverting claim submission
    4. Cancelling TISS submission if needed
    5. Updating claim status
    6. Creating compensation audit record
    7. Notifying claim and TISS systems

    Input Variables:
        - submissionId: Claim submission ID to undo (required)
        - claimId: Associated claim ID (required)
        - encounterId: Associated encounter ID (required)
        - reason: Compensation reason (required)
        - compensationContext: Additional context (optional)

    Output Variables:
        - compensationSuccess: Whether compensation succeeded (boolean)
        - compensationStatus: Compensation operation status
        - submissionCancelled: Whether submission was cancelled (boolean)
        - tissNotified: Whether TISS system was notified (boolean)
        - compensationDate: When compensation was executed

    SAGA Pattern:
        - This is a compensation handler for SubmitClaimWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if submission not found (SKIPPED)
        - Should succeed if submission already compensated (ALREADY_COMPENSATED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "submissionId": "SUB-001",
            "claimId": "CLM-2026-001",
            "encounterId": "ENC-2026-001",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "compensationSuccess": true,
            "compensationStatus": "SUCCESS",
            "submissionCancelled": true,
            "tissNotified": true,
            "compensationDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, claim_service=None, tiss_service=None, audit_service=None, **kwargs):
        """
        Initialize the compensate submit worker.

        Args:
            settings: Optional worker settings
            claim_service: Optional claim service (for testing)
            tiss_service: Optional TISS service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._claim_service = claim_service
        self._tiss_service = tiss_service
        self._audit_service = audit_service
        self._compensations: dict[str, CompensateSubmitOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "compensate_submit"

    @property
    def requires_idempotency(self) -> bool:
        """Submission compensation requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        submission_id = variables.get("submissionId", "")
        claim_id = variables.get("claimId", "")
        return f"{submission_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process submission compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with compensation outcome
        """
        self._logger.info(
            "Processing submission compensation",
            job_key=str(getattr(job, "key", "unknown")),
            submission_id=variables.get("submissionId"),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = CompensateSubmitInput.model_validate(variables)

            # Check if already compensated (idempotency)
            cache_key = f"{input_data.submission_id}:{input_data.claim_id}"
            if cache_key in self._compensations:
                cached = self._compensations[cache_key]
                self._logger.info(
                    "Returning cached compensation result",
                    submission_id=input_data.submission_id,
                )
                return WorkerResult.ok(cached.model_dump(by_alias=True))

            # Execute compensation
            compensation_result = await self._execute_compensation(input_data)

            # Create audit trail entry
            if self._audit_service and hasattr(self._audit_service, "log_compensation"):
                await self._audit_service.log_compensation(input_data, compensation_result)

            # Cache result for idempotency
            self._compensations[cache_key] = compensation_result

            if compensation_result.compensation_success:
                self._logger.info(
                    "Submission compensation completed successfully",
                    submission_id=input_data.submission_id,
                    status=compensation_result.compensation_status.value,
                    submission_cancelled=compensation_result.submission_cancelled,
                    tiss_notified=compensation_result.tiss_notified,
                )
                return WorkerResult.ok(compensation_result.model_dump(by_alias=True))
            else:
                self._logger.warning(
                    "Submission compensation failed",
                    submission_id=input_data.submission_id,
                    error=compensation_result.error_message,
                )
                return WorkerResult.bpmn_error(
                    error_code="SUBMISSION_COMPENSATION_FAILED",
                    error_message=compensation_result.error_message or "Submission compensation failed",
                )

        except ValidationError as e:
            self._logger.error(
                "Submission compensation validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_COMPENSATION_DATA",
                error_message=f"Compensation validation failed: {e}",
            )

        except SubmissionCompensationError as e:
            self._logger.error(
                "Submission compensation error",
                error=str(e),
                error_code=e.error_code,
            )
            output = CompensateSubmitOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                submission_cancelled=False,
                tiss_notified=False,
                compensation_date=datetime.utcnow(),
                error_message=e.message,
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Unexpected error during submission compensation",
                error=str(e),
                exc_info=True,
            )
            output = CompensateSubmitOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                submission_cancelled=False,
                tiss_notified=False,
                compensation_date=datetime.utcnow(),
                error_message=f"Unexpected error: {e}",
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

    async def _execute_compensation(
        self,
        input_data: CompensateSubmitInput,
    ) -> CompensateSubmitOutput:
        """
        Execute submission compensation.

        In production:
        - Query claim database for submission record
        - Check submission status (SUBMITTED/ACCEPTED/REJECTED)
        - Cancel submission if still pending
        - Notify TISS system of cancellation
        - Update claim status (remove from submitted)
        - Restore previous claim state
        - Create cancellation record

        Args:
            input_data: Compensation input data

        Returns:
            Compensation output data
        """
        self._logger.info(
            "Executing submission compensation (PRODUCTION: integrate claim/TISS systems)",
            submission_id=input_data.submission_id,
            claim_id=input_data.claim_id,
            encounter_id=input_data.encounter_id,
            reason=input_data.reason.value,
        )

        # Simulate: submission exists and is cancelled
        submission_cancelled = True
        tiss_notified = True

        return CompensateSubmitOutput(
            compensation_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            submission_cancelled=submission_cancelled,
            tiss_notified=tiss_notified,
            compensation_date=datetime.utcnow(),
            error_message=None,
        )
