"""
CompensateAppealWorker - SAGA compensation worker for undoing glosa appeals.

This worker implements glosa appeal undo logic for transaction rollback:
- Reverts glosa appeal submission
- Updates appeal status
- Restores previous glosa state
- Maintains audit trail

Business Rule: RN-COMP-CompensateAppealDelegate.md
SAGA Pattern: Compensation for glosa-appeal task
Regulatory Compliance: ANS RN 424/2017 (appeal reversal)
Migrated from: com.hospital.revenuecycle.delegates.compensation.CompensateAppealDelegate
Topic: compensate-appeal-submission
BPMN Compensation: Compensate Task_Submit_Glosa_Appeal
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


class CompensateAppealInput(BaseModel):
    """Input model for CompensateAppealWorker."""

    appeal_id: str = Field(
        ...,
        alias="appealId",
        min_length=1,
        description="Glosa appeal ID to undo",
    )
    glosa_id: str = Field(
        ...,
        alias="glosaId",
        min_length=1,
        description="Associated glosa identifier",
    )
    claim_id: str = Field(
        ...,
        alias="claimId",
        min_length=1,
        description="Associated claim identifier",
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


class CompensateAppealOutput(BaseModel):
    """Output model for CompensateAppealWorker."""

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
    appeal_reverted: bool = Field(
        ...,
        alias="appealReverted",
        description="Whether appeal was reverted",
    )
    reverted_actions: list[str] = Field(
        default_factory=list,
        alias="revertedActions",
        description="List of actions reverted",
    )
    audit_trail_id: Optional[str] = Field(
        None,
        alias="auditTrailId",
        description="Audit trail record ID",
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


class AppealCompensationError(BpmnErrorException):
    """Raised when appeal compensation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="APPEAL_COMPENSATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-appeal-submission", max_jobs=16, lock_duration=45000)
class CompensateAppealWorker(BaseWorker):
    """
    SAGA compensation worker for undoing glosa appeals.

    This worker undoes glosa appeal submissions by:
    1. Validating appeal undo request
    2. Checking if already compensated (idempotency)
    3. Reverting appeal submission state
    4. Restoring previous glosa status
    5. Creating compensation audit record
    6. Notifying glosa system

    Input Variables:
        - appealId: Glosa appeal ID to undo (required)
        - glosaId: Associated glosa ID (required)
        - claimId: Associated claim ID (required)
        - reason: Compensation reason (required)
        - compensationContext: Additional context (optional)

    Output Variables:
        - compensationSuccess: Whether compensation succeeded (boolean)
        - compensationStatus: Compensation operation status
        - appealReverted: Whether appeal was reverted (boolean)
        - revertedActions: List of reverted actions
        - auditTrailId: Audit trail record ID
        - compensationDate: When compensation was executed

    SAGA Pattern:
        - This is a compensation handler for SubmitGlosaAppealWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if appeal not found (SKIPPED)
        - Should succeed if appeal already compensated (ALREADY_COMPENSATED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "appealId": "APP-001",
            "glosaId": "GLOSA-2026-001",
            "claimId": "CLM-2026-001",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "compensationSuccess": true,
            "compensationStatus": "SUCCESS",
            "appealReverted": true,
            "revertedActions": ["APPEAL_WITHDRAWN", "GLOSA_STATUS_RESTORED"],
            "compensationDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, glosa_service=None, audit_service=None, **kwargs):
        """
        Initialize the compensate appeal worker.

        Args:
            settings: Optional worker settings
            glosa_service: Optional glosa service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._glosa_service = glosa_service
        self._audit_service = audit_service
        self._compensations: dict[str, CompensateAppealOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "compensate_appeal"

    @property
    def requires_idempotency(self) -> bool:
        """Appeal compensation requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        appeal_id = variables.get("appealId", "")
        claim_id = variables.get("claimId", "")
        return f"{appeal_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process appeal compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with compensation outcome
        """
        self._logger.info(
            "Processing appeal compensation",
            job_key=str(getattr(job, "key", "unknown")),
            appeal_id=variables.get("appealId"),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = CompensateAppealInput.model_validate(variables)

            # Check if already compensated (idempotency)
            cache_key = f"{input_data.appeal_id}:{input_data.claim_id}"
            if cache_key in self._compensations:
                cached = self._compensations[cache_key]
                self._logger.info(
                    "Returning cached compensation result",
                    appeal_id=input_data.appeal_id,
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
                    "Appeal compensation completed successfully",
                    appeal_id=input_data.appeal_id,
                    status=compensation_result.compensation_status.value,
                    actions_reverted=len(compensation_result.reverted_actions),
                )
                return WorkerResult.ok(compensation_result.model_dump(by_alias=True))
            else:
                self._logger.warning(
                    "Appeal compensation failed",
                    appeal_id=input_data.appeal_id,
                    error=compensation_result.error_message,
                )
                return WorkerResult.bpmn_error(
                    error_code="APPEAL_COMPENSATION_FAILED",
                    error_message=compensation_result.error_message or "Appeal compensation failed",
                )

        except ValidationError as e:
            self._logger.error(
                "Appeal compensation validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_COMPENSATION_DATA",
                error_message=f"Compensation validation failed: {e}",
            )

        except AppealCompensationError as e:
            self._logger.error(
                "Appeal compensation error",
                error=str(e),
                error_code=e.error_code,
            )
            output = CompensateAppealOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                appeal_reverted=False,
                compensation_date=datetime.utcnow(),
                error_message=e.message,
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Unexpected error during appeal compensation",
                error=str(e),
                exc_info=True,
            )
            output = CompensateAppealOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                appeal_reverted=False,
                compensation_date=datetime.utcnow(),
                error_message=f"Unexpected error: {e}",
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

    async def _execute_compensation(
        self,
        input_data: CompensateAppealInput,
    ) -> CompensateAppealOutput:
        """
        Execute appeal compensation.

        In production:
        - Query glosa database for appeal record
        - Check appeal status (SUBMITTED/ACCEPTED/REJECTED)
        - Withdraw appeal submission
        - Restore previous glosa state
        - Update claim status if needed
        - Notify glosa system

        Args:
            input_data: Compensation input data

        Returns:
            Compensation output data
        """
        self._logger.info(
            "Executing appeal compensation (PRODUCTION: integrate glosa system)",
            appeal_id=input_data.appeal_id,
            glosa_id=input_data.glosa_id,
            claim_id=input_data.claim_id,
            reason=input_data.reason.value,
        )

        # Simulate: appeal exists and is reverted
        reverted_actions = [
            "APPEAL_WITHDRAWN",
            "GLOSA_STATUS_RESTORED",
            "CLAIM_APPEAL_FLAG_CLEARED",
        ]

        return CompensateAppealOutput(
            compensation_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            appeal_reverted=True,
            reverted_actions=reverted_actions,
            audit_trail_id=f"AUDIT-{input_data.appeal_id}-{datetime.utcnow().timestamp()}",
            compensation_date=datetime.utcnow(),
            error_message=None,
        )
