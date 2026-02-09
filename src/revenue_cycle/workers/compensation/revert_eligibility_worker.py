"""
RevertEligibilityWorker - SAGA compensation worker for reverting eligibility verification.

This worker implements eligibility revert logic for transaction rollback:
- Reverts eligibility check status
- Clears cached eligibility data
- Maintains audit trail
- Supports idempotency for safe retry

Business Rule: RN-COMP-EligibilityRevert.md
SAGA Pattern: Compensation for eligibility-verification task
Regulatory Compliance: ANS RN 424/2017 (eligibility control)
Migrated from: com.hospital.revenuecycle.delegates.compensation.RevertEligibilityDelegate
Topic: compensate-revert-eligibility
BPMN Compensation: Compensate Task_Verify_Eligibility
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import structlog
from pydantic import ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.compensation.models import (
    RevertEligibilityInput,
    RevertEligibilityOutput,
    CompensationStatus,
)

logger = structlog.get_logger(__name__)


class EligibilityRevertError(BpmnErrorException):
    """Raised when eligibility revert fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="ELIGIBILITY_REVERT_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-revert-eligibility", max_jobs=16, lock_duration=30000)
class RevertEligibilityWorker(BaseWorker):
    """
    SAGA compensation worker for reverting eligibility verification.

    This worker reverts eligibility verification by:
    1. Validating revert request
    2. Checking if already reverted (idempotency)
    3. Clearing eligibility check status
    4. Removing cached eligibility data
    5. Creating revert audit record
    6. Notifying eligibility system

    Input Variables:
        - eligibilityCheckId: Eligibility check ID to revert (required)
        - patientId: Patient identifier (required)
        - insuranceId: Insurance identifier (required)
        - reason: Compensation reason (required)

    Output Variables:
        - revertSuccess: Whether revert succeeded (boolean)
        - compensationStatus: Compensation operation status
        - revertDate: When revert was executed
        - errorMessage: Error message if failed (optional)

    SAGA Pattern:
        - This is a compensation handler for ValidateEligibilityWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if eligibility check not found (SKIPPED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "eligibilityCheckId": "ELIG-001",
            "patientId": "PAT-12345",
            "insuranceId": "INS-789",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "revertSuccess": true,
            "compensationStatus": "SUCCESS",
            "revertDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, eligibility_service=None, audit_service=None, **kwargs):
        """
        Initialize the revert eligibility worker.

        Args:
            settings: Optional worker settings
            eligibility_service: Optional eligibility service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._eligibility_service = eligibility_service
        self._audit_service = audit_service
        self._reverts: dict[str, RevertEligibilityOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "revert_eligibility"

    @property
    def requires_idempotency(self) -> bool:
        """Eligibility revert requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        eligibility_check_id = variables.get("eligibilityCheckId", "")
        patient_id = variables.get("patientId", "")
        return f"{eligibility_check_id}:{patient_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process eligibility revert compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with revert outcome
        """
        self._logger.info(
            "Processing eligibility revert",
            job_key=str(getattr(job, "key", "unknown")),
            eligibility_check_id=variables.get("eligibilityCheckId"),
            patient_id=variables.get("patientId"),
        )

        try:
            # Parse and validate input
            input_data = RevertEligibilityInput.model_validate(variables)

            # Check if already reverted (idempotency)
            cache_key = f"{input_data.eligibility_check_id}:{input_data.patient_id}"
            if cache_key in self._reverts:
                cached = self._reverts[cache_key]
                self._logger.info(
                    "Returning cached revert result",
                    eligibility_check_id=input_data.eligibility_check_id,
                )
                output_dict = cached.model_dump(by_alias=True)
                output_dict["eligibilityCheckId"] = input_data.eligibility_check_id
                return WorkerResult.ok(output_dict)

            # Execute revert
            revert_result = await self._execute_revert(input_data)

            # Create audit trail entry
            if self._audit_service and hasattr(self._audit_service, "log_compensation"):
                await self._audit_service.log_compensation(input_data, revert_result)

            # Cache result for idempotency
            self._reverts[cache_key] = revert_result

            if revert_result.reversion_success:
                self._logger.info(
                    "Eligibility revert completed successfully",
                    eligibility_check_id=input_data.eligibility_check_id,
                    status=revert_result.compensation_status.value,
                )
                output_dict = revert_result.model_dump(by_alias=True)
                output_dict["eligibilityCheckId"] = input_data.eligibility_check_id
                return WorkerResult.ok(output_dict)
            else:
                self._logger.warning(
                    "Eligibility revert failed",
                    eligibility_check_id=input_data.eligibility_check_id,
                    error=revert_result.error_message,
                )
                output_dict = revert_result.model_dump(by_alias=True)
                output_dict["eligibilityCheckId"] = input_data.eligibility_check_id
                return WorkerResult.bpmn_error(
                    error_code="ELIGIBILITY_REVERT_FAILED",
                    error_message=revert_result.error_message or "Eligibility revert failed",
                )

        except ValidationError as e:
            self._logger.error(
                "Eligibility revert validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_REVERT_DATA",
                error_message=f"Revert validation failed: {e}",
            )

        except EligibilityRevertError as e:
            self._logger.error(
                "Eligibility revert error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code="ELIGIBILITY_REVERT_ERROR",
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during eligibility revert",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.bpmn_error(
                error_code="UNEXPECTED_ERROR",
                error_message=str(e),
            )

    async def _execute_revert(
        self,
        input_data: RevertEligibilityInput,
    ) -> RevertEligibilityOutput:
        """
        Execute eligibility revert.

        In production:
        - Query eligibility database for check record
        - Clear eligibility check status
        - Remove cached eligibility data
        - Update check status to REVERTED
        - Invalidate any authorization codes obtained

        Args:
            input_data: Revert input data

        Returns:
            Revert output data
        """
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        # 1. Query eligibility database for check record
        # 2. Validate check exists and is revertible
        # 3. Clear eligibility check status
        # 4. Remove from eligibility cache
        # 5. Update check status to REVERTED
        # 6. If authorization codes were generated, invalidate them
        # 7. Notify insurance eligibility system if needed

        # STUB: Simulate successful revert
        self._logger.info(
            "Executing eligibility revert (PRODUCTION: integrate eligibility system)",
            eligibility_check_id=input_data.eligibility_check_id,
            patient_id=input_data.patient_id,
            insurance_id=input_data.insurance_id,
            reason=input_data.reason.value,
        )

        # Call eligibility service if available
        if self._eligibility_service and hasattr(self._eligibility_service, "revert_eligibility"):
            await self._eligibility_service.revert_eligibility(input_data.eligibility_check_id)

        return RevertEligibilityOutput(
            reversion_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            reversion_date=datetime.utcnow(),
            error_message=None,
            eligibility_id=input_data.eligibility_check_id,
        )

    async def _create_audit_trail(
        self,
        input_data: RevertEligibilityInput,
        result: RevertEligibilityOutput,
    ) -> None:
        """Create audit trail entry for revert operation."""
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        self._logger.info(
            "Eligibility revert audit trail created",
            eligibility_check_id=input_data.eligibility_check_id,
            patient_id=input_data.patient_id,
            insurance_id=input_data.insurance_id,
            reason=input_data.reason.value,
            success=result.reversion_success,
        )
