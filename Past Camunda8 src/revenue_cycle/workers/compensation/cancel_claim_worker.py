"""
CancelClaimWorker - SAGA compensation worker for canceling submitted claims.

This worker implements claim cancellation logic for transaction rollback:
- Cancels claim submission with payer
- Updates claim status to CANCELLED
- Creates cancellation record
- Maintains audit trail
- Supports idempotency for safe retry

Business Rule: RN-COMP-003-CompensateSubmitDelegate.md
SAGA Pattern: Compensation for submit-claim task
Regulatory Compliance: ANS RN 395/2016 (claim submission tracking)
Migrated from: com.hospital.revenuecycle.delegates.compensation.CancelClaimDelegate
Topic: compensate-cancel-claim
BPMN Compensation: Compensate Task_Generate_Claim / Task_Submit_Claim
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
    CancelClaimInput,
    CancelClaimOutput,
    CompensationStatus,
)

logger = structlog.get_logger(__name__)


class ClaimCancellationError(BpmnErrorException):
    """Raised when claim cancellation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="CLAIM_CANCELLATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-cancel-claim", max_jobs=16, lock_duration=45000)
class CancelClaimWorker(BaseWorker):
    """
    SAGA compensation worker for canceling submitted claims.

    This worker cancels a previously submitted claim by:
    1. Validating cancellation request
    2. Checking if already cancelled (idempotency)
    3. Submitting cancellation to payer system (if needed)
    4. Updating claim status to CANCELLED
    5. Creating cancellation audit record
    6. Notifying relevant parties

    Input Variables:
        - claimId: Claim identifier to cancel (required)
        - encounterId: Associated encounter ID (required)
        - patientId: Patient identifier (required)
        - reason: Compensation reason (required)
        - cancelNote: Cancellation notes (optional)

    Output Variables:
        - cancellationSuccess: Whether cancellation succeeded (boolean)
        - compensationStatus: Compensation operation status
        - cancellationId: Cancellation record ID
        - cancellationDate: When cancellation was executed
        - errorMessage: Error message if failed (optional)

    SAGA Pattern:
        - This is a compensation handler for GenerateClaimWorker/SubmitClaimWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if claim not found (SKIPPED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "claimId": "CLM-2026-001",
            "encounterId": "ENC-12345",
            "patientId": "PAT-12345",
            "reason": "TRANSACTION_FAILED",
            "cancelNote": "Compensating failed transaction"
        }

        Output (Success):
        {
            "cancellationSuccess": true,
            "compensationStatus": "SUCCESS",
            "cancellationId": "CXL-20260204-ABC123",
            "cancellationDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, claim_service=None, audit_service=None, **kwargs):
        """
        Initialize the cancellation worker.

        Args:
            settings: Optional worker settings
            claim_service: Optional claim service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._claim_service = claim_service
        self._audit_service = audit_service
        self._cancellations: dict[str, CancelClaimOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "cancel_claim"

    @property
    def requires_idempotency(self) -> bool:
        """Claim cancellation requires idempotency to prevent duplicate cancellations."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Uses claim_id to detect duplicate cancellation attempts.
        """
        claim_id = variables.get("claimId", "")
        encounter_id = variables.get("encounterId", "")
        return f"{claim_id}:{encounter_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process claim cancellation compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with cancellation outcome
        """
        self._logger.info(
            "Processing claim cancellation",
            job_key=str(getattr(job, "key", "unknown")),
            claim_id=variables.get("claimId"),
            encounter_id=variables.get("encounterId"),
        )

        try:
            # Parse and validate input
            input_data = CancelClaimInput.model_validate(variables)

            # Check if already cancelled (idempotency)
            cache_key = f"{input_data.claim_id}:{input_data.encounter_id}"
            if cache_key in self._cancellations:
                cached = self._cancellations[cache_key]
                self._logger.info(
                    "Returning cached cancellation result",
                    claim_id=input_data.claim_id,
                    cancellation_id=cached.cancellation_id,
                )
                output_dict = cached.model_dump(by_alias=True)
                output_dict["claimId"] = input_data.claim_id
                return WorkerResult.ok(output_dict)

            # Execute cancellation
            cancellation_result = await self._execute_cancellation(input_data)

            # Create audit trail entry
            if self._audit_service and hasattr(self._audit_service, "log_compensation"):
                await self._audit_service.log_compensation(input_data, cancellation_result)

            # Cache result for idempotency
            self._cancellations[cache_key] = cancellation_result

            if cancellation_result.cancellation_success:
                self._logger.info(
                    "Claim cancellation completed successfully",
                    claim_id=input_data.claim_id,
                    cancellation_id=cancellation_result.cancellation_id,
                    status=cancellation_result.compensation_status.value,
                )
                output_dict = cancellation_result.model_dump(by_alias=True)
                output_dict["claimId"] = input_data.claim_id
                return WorkerResult.ok(output_dict)
            else:
                self._logger.warning(
                    "Claim cancellation failed",
                    claim_id=input_data.claim_id,
                    error=cancellation_result.error_message,
                )
                output_dict = cancellation_result.model_dump(by_alias=True)
                output_dict["claimId"] = input_data.claim_id
                return WorkerResult.ok(output_dict)

        except ValidationError as e:
            self._logger.error(
                "Claim cancellation validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_CANCELLATION_DATA",
                error_message=f"Cancellation validation failed: {e}",
            )

        except ClaimCancellationError as e:
            self._logger.error(
                "Claim cancellation error",
                error=str(e),
                error_code=e.error_code,
            )
            output = CancelClaimOutput(
                cancellation_success=False,
                compensation_status=CompensationStatus.FAILED,
                cancellation_id=f"FAILED-{uuid4().hex[:8].upper()}",
                cancellation_date=datetime.utcnow(),
                error_message=e.message,
            )
            output_dict = output.model_dump(by_alias=True)
            output_dict["claimId"] = variables.get("claimId", "")
            return WorkerResult.bpmn_error(
                error_code="CLAIM_CANCELLATION_ERROR",
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during claim cancellation",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.bpmn_error(
                error_code="UNEXPECTED_ERROR",
                error_message=str(e),
            )

    async def _execute_cancellation(
        self,
        input_data: CancelClaimInput,
    ) -> CancelClaimOutput:
        """
        Execute claim cancellation.

        In production:
        - Query claim database to verify claim exists
        - Submit cancellation to payer system (ANS, TISS)
        - Update claim status to CANCELLED
        - Generate cancellation XML (TISS standard)
        - Notify billing system

        Args:
            input_data: Cancellation input data

        Returns:
            Cancellation output data
        """
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        # 1. Query claim database for original claim
        # 2. Validate claim is in cancellable state
        # 3. Submit cancellation to payer (ANS system, TISS protocol)
        # 4. Update claim status to CANCELLED
        # 5. Create cancellation record in database
        # 6. Notify billing and accounting systems

        cancellation_id = f"CXL-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"

        # Call claim service if available
        if self._claim_service and hasattr(self._claim_service, "cancel_claim"):
            await self._claim_service.cancel_claim(input_data.claim_id)

        # STUB: Simulate successful cancellation
        self._logger.info(
            "Executing claim cancellation (PRODUCTION: integrate claim system)",
            claim_id=input_data.claim_id,
            cancellation_id=cancellation_id,
            encounter_id=input_data.encounter_id,
            reason=input_data.reason.value,
        )

        return CancelClaimOutput(
            cancellation_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            cancellation_id=cancellation_id,
            cancellation_date=datetime.utcnow(),
            error_message=None,
        )

    async def _create_audit_trail(
        self,
        input_data: CancelClaimInput,
        result: CancelClaimOutput,
    ) -> None:
        """
        Create audit trail entry for cancellation operation.

        Args:
            input_data: Original cancellation input
            result: Cancellation result
        """
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        self._logger.info(
            "Claim cancellation audit trail created",
            claim_id=input_data.claim_id,
            cancellation_id=result.cancellation_id,
            encounter_id=input_data.encounter_id,
            patient_id=input_data.patient_id,
            reason=input_data.reason.value,
            success=result.cancellation_success,
        )
