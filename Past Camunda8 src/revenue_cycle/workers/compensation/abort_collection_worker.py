"""
AbortCollectionWorker - SAGA compensation worker for aborting collection processes.

This worker implements collection abort logic for transaction rollback:
- Aborts active collection process
- Updates collection status
- Maintains audit trail
- Supports idempotency for safe retry

Business Rule: RN-COMP-CollectionAbort.md
SAGA Pattern: Compensation for initiate-collection task
Regulatory Compliance: ANS RN 424/2017 (collection process control)
Migrated from: com.hospital.revenuecycle.delegates.compensation.AbortCollectionDelegate
Topic: compensate-abort-collection
BPMN Compensation: Compensate Task_Initiate_Collection
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import structlog
from pydantic import ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.compensation.models import (
    AbortCollectionInput,
    AbortCollectionOutput,
    CompensationStatus,
)

logger = structlog.get_logger(__name__)


class CollectionAbortError(BpmnErrorException):
    """Raised when collection abort fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="COLLECTION_ABORT_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-abort-collection", max_jobs=16, lock_duration=45000)
class AbortCollectionWorker(BaseWorker):
    """
    SAGA compensation worker for aborting collection processes.

    This worker aborts collection processes by:
    1. Validating abort request
    2. Checking if already aborted (idempotency)
    3. Stopping active collection activities
    4. Updating collection status to ABORTED
    5. Creating abort audit record
    6. Notifying collection system

    Input Variables:
        - collectionId: Collection process ID to abort (required)
        - claimId: Associated claim ID (required)
        - patientId: Patient identifier (required)
        - outstandingAmount: Outstanding collection amount (required, Decimal)
        - reason: Compensation reason (required)

    Output Variables:
        - abortSuccess: Whether abort succeeded (boolean)
        - compensationStatus: Compensation operation status
        - abortDate: When abort was executed
        - collectionWasActive: Whether collection was still active (boolean)
        - errorMessage: Error message if failed (optional)

    SAGA Pattern:
        - This is a compensation handler for InitiateCollectionWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if collection not found (SKIPPED)
        - Should succeed if collection already completed (ALREADY_COMPENSATED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "collectionId": "COLL-001",
            "claimId": "CLM-2026-001",
            "patientId": "PAT-12345",
            "outstandingAmount": "150.00",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "abortSuccess": true,
            "compensationStatus": "SUCCESS",
            "abortDate": "2026-02-04T14:30:00Z",
            "collectionWasActive": true
        }
    """

    def __init__(self, settings=None, collection_service=None, audit_service=None, **kwargs):
        """
        Initialize the abort collection worker.

        Args:
            settings: Optional worker settings
            collection_service: Optional collection service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._collection_service = collection_service
        self._audit_service = audit_service
        self._aborts: dict[str, AbortCollectionOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "abort_collection"

    @property
    def requires_idempotency(self) -> bool:
        """Collection abort requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        collection_id = variables.get("collectionId", "")
        claim_id = variables.get("claimId", "")
        return f"{collection_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process collection abort compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with abort outcome
        """
        self._logger.info(
            "Processing collection abort",
            job_key=str(getattr(job, "key", "unknown")),
            collection_id=variables.get("collectionId"),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = AbortCollectionInput.model_validate(variables)

            # Check if already aborted (idempotency)
            cache_key = f"{input_data.collection_id}:{input_data.claim_id}"
            if cache_key in self._aborts:
                cached = self._aborts[cache_key]
                self._logger.info(
                    "Returning cached abort result",
                    collection_id=input_data.collection_id,
                )
                output_dict = cached.model_dump(by_alias=True)
                output_dict["collectionId"] = input_data.collection_id
                return WorkerResult.ok(output_dict)

            # Execute abort
            abort_result = await self._execute_abort(input_data)

            # Create audit trail entry
            if self._audit_service and hasattr(self._audit_service, "log_compensation"):
                await self._audit_service.log_compensation(input_data, abort_result)

            # Cache result for idempotency
            self._aborts[cache_key] = abort_result

            if abort_result.abort_success:
                self._logger.info(
                    "Collection abort completed successfully",
                    collection_id=input_data.collection_id,
                    status=abort_result.compensation_status.value,
                    was_active=abort_result.collection_was_active,
                )
                output_dict = abort_result.model_dump(by_alias=True)
                output_dict["collectionId"] = input_data.collection_id
                return WorkerResult.ok(output_dict)
            else:
                self._logger.warning(
                    "Collection abort failed",
                    collection_id=input_data.collection_id,
                    error=abort_result.error_message,
                )
                output_dict = abort_result.model_dump(by_alias=True)
                output_dict["collectionId"] = input_data.collection_id
                return WorkerResult.bpmn_error(
                    error_code="COLLECTION_ABORT_FAILED",
                    error_message=abort_result.error_message or "Collection abort failed",
                )

        except ValidationError as e:
            self._logger.error(
                "Collection abort validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_ABORT_DATA",
                error_message=f"Abort validation failed: {e}",
            )

        except CollectionAbortError as e:
            self._logger.error(
                "Collection abort error",
                error=str(e),
                error_code=e.error_code,
            )
            output = AbortCollectionOutput(
                abort_success=False,
                compensation_status=CompensationStatus.FAILED,
                abort_date=datetime.utcnow(),
                collection_was_active=False,
                error_message=e.message,
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Unexpected error during collection abort",
                error=str(e),
                exc_info=True,
            )
            output = AbortCollectionOutput(
                abort_success=False,
                compensation_status=CompensationStatus.FAILED,
                abort_date=datetime.utcnow(),
                collection_was_active=False,
                error_message=f"Unexpected error: {e}",
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

    async def _execute_abort(
        self,
        input_data: AbortCollectionInput,
    ) -> AbortCollectionOutput:
        """
        Execute collection abort.

        In production:
        - Query collection database for process record
        - Check collection status (ACTIVE/PENDING/COMPLETED)
        - If ACTIVE: Stop all collection activities
        - Cancel scheduled collection actions
        - Update collection status to ABORTED
        - Notify collection agency if external collection

        Args:
            input_data: Abort input data

        Returns:
            Abort output data
        """
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        # 1. Query collection database for collection process
        # 2. Check collection status:
        #    - ACTIVE: Stop collection activities
        #    - PENDING: Cancel scheduled actions
        #    - COMPLETED: Return success (nothing to abort)
        # 3. Cancel any scheduled collection reminders/letters
        # 4. If using external collection agency, notify them
        # 5. Update collection status to ABORTED
        # 6. Update claim status (remove from collections)
        # 7. Create abort record in database

        # STUB: Simulate successful abort (assume active)
        self._logger.info(
            "Executing collection abort (PRODUCTION: integrate collection system)",
            collection_id=input_data.collection_id,
            claim_id=input_data.claim_id,
            patient_id=input_data.patient_id,
            outstanding_amount=str(input_data.outstanding_amount),
            reason=input_data.reason.value,
        )

        # Simulate: collection was active and aborted
        collection_was_active = True
        aborted_items = 0

        return AbortCollectionOutput(
            abort_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            abort_date=datetime.utcnow(),
            collection_was_active=collection_was_active,
            error_message=None,
            collection_id=input_data.collection_id,
            aborted_items_count=aborted_items,
        )

    async def _create_audit_trail(
        self,
        input_data: AbortCollectionInput,
        result: AbortCollectionOutput,
    ) -> None:
        """Create audit trail entry for abort operation."""
        self._logger.info(
            "Collection abort audit trail created",
            collection_id=input_data.collection_id,
            claim_id=input_data.claim_id,
            patient_id=input_data.patient_id,
            outstanding_amount=str(input_data.outstanding_amount),
            reason=input_data.reason.value,
            success=result.abort_success,
            was_active=result.collection_was_active,
        )

        # Call audit service if available
        if self._audit_service:
            try:
                await self._audit_service.log_compensation(
                    operation="abort_collection",
                    collection_id=input_data.collection_id,
                    claim_id=input_data.claim_id,
                    patient_id=input_data.patient_id,
                    outstanding_amount=str(input_data.outstanding_amount),
                    reason=input_data.reason.value,
                    success=result.abort_success,
                )
            except Exception as e:
                self._logger.warning(
                    "Audit service error, continuing with operation",
                    error=str(e),
                )
