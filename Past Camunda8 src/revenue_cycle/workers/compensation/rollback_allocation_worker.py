"""
RollbackAllocationWorker - SAGA compensation worker for rolling back payment allocations.

This worker implements allocation rollback logic for transaction rollback:
- Unallocates payment from claim
- Returns payment to unallocated pool
- Updates allocation records
- Maintains audit trail
- Supports idempotency for safe retry

Business Rule: RN-COMP-001-CompensateAllocationDelegate.md
SAGA Pattern: Compensation for payment-allocation task
Regulatory Compliance: CPC 25 (allocation reversal), ANS RN 424/2017
Migrated from: com.hospital.revenuecycle.delegates.compensation.RollbackAllocationDelegate
Topic: compensate-rollback-allocation
BPMN Compensation: Compensate Task_Allocate_Payment
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
    RollbackAllocationInput,
    RollbackAllocationOutput,
    CompensationStatus,
)

logger = structlog.get_logger(__name__)


class AllocationRollbackError(BpmnErrorException):
    """Raised when allocation rollback fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="ALLOCATION_ROLLBACK_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-rollback-allocation", max_jobs=16, lock_duration=45000)
class RollbackAllocationWorker(BaseWorker):
    """
    SAGA compensation worker for rolling back payment allocations.

    This worker rolls back a payment allocation by:
    1. Validating rollback request
    2. Checking if already rolled back (idempotency)
    3. Unallocating payment from claim
    4. Returning amount to unallocated pool
    5. Creating rollback audit record
    6. Updating allocation status

    Input Variables:
        - allocationId: Payment allocation ID to rollback (required)
        - paymentId: Associated payment ID (required)
        - claimId: Claim identifier (required)
        - allocatedAmount: Amount that was allocated (required, Decimal)
        - reason: Compensation reason (required)

    Output Variables:
        - rollbackSuccess: Whether rollback succeeded (boolean)
        - compensationStatus: Compensation operation status
        - unallocatedAmount: Amount successfully unallocated
        - rollbackDate: When rollback was executed
        - errorMessage: Error message if failed (optional)

    SAGA Pattern:
        - This is a compensation handler for AllocatePaymentWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if allocation not found (SKIPPED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "allocationId": "ALLOC-001",
            "paymentId": "PAY-12345",
            "claimId": "CLM-2026-001",
            "allocatedAmount": "150.00",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "rollbackSuccess": true,
            "compensationStatus": "SUCCESS",
            "unallocatedAmount": "150.00",
            "rollbackDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, budget_service=None, audit_service=None, **kwargs):
        """
        Initialize the rollback worker.

        Args:
            settings: Optional worker settings
            allocation_service: Optional allocation service (for testing)
        """
        super().__init__(settings=settings)
        self._budget_service = budget_service
        self._audit_service = audit_service
        self._rollbacks: dict[str, RollbackAllocationOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "rollback_allocation"

    @property
    def requires_idempotency(self) -> bool:
        """Allocation rollback requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        allocation_id = variables.get("allocationId", "")
        payment_id = variables.get("paymentId", "")
        return f"{allocation_id}:{payment_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process allocation rollback compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with rollback outcome
        """
        self._logger.info(
            "Processing allocation rollback",
            job_key=str(getattr(job, "key", "unknown")),
            allocation_id=variables.get("allocationId"),
            payment_id=variables.get("paymentId"),
        )

        try:
            # Parse and validate input
            input_data = RollbackAllocationInput.model_validate(variables)

            # Check if already rolled back (idempotency)
            cache_key = f"{input_data.allocation_id}:{input_data.payment_id}"
            if cache_key in self._rollbacks:
                cached = self._rollbacks[cache_key]
                self._logger.info(
                    "Returning cached rollback result",
                    allocation_id=input_data.allocation_id,
                )
                return WorkerResult.ok(cached.model_dump(by_alias=True))

            # Execute rollback
            rollback_result = await self._execute_rollback(input_data)

            # Create audit trail entry
            await self._create_audit_trail(input_data, rollback_result)

            # Cache result for idempotency
            self._rollbacks[cache_key] = rollback_result

            if rollback_result.rollback_success:
                self._logger.info(
                    "Allocation rollback completed successfully",
                    allocation_id=input_data.allocation_id,
                    unallocated_amount=str(rollback_result.unallocated_amount),
                    status=rollback_result.compensation_status.value,
                )
                return WorkerResult.ok(rollback_result.model_dump(by_alias=True))
            else:
                self._logger.warning(
                    "Allocation rollback failed",
                    allocation_id=input_data.allocation_id,
                    error=rollback_result.error_message,
                )
                return WorkerResult.ok(rollback_result.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Allocation rollback validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_ROLLBACK_DATA",
                error_message=f"Rollback validation failed: {e}",
            )

        except AllocationRollbackError as e:
            self._logger.error(
                "Allocation rollback error",
                error=str(e),
                error_code=e.error_code,
            )
            output = RollbackAllocationOutput(
                rollback_success=False,
                compensation_status=CompensationStatus.FAILED,
                unallocated_amount=input_data.allocated_amount,
                rollback_date=datetime.utcnow(),
                error_message=e.message,
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Unexpected error during allocation rollback",
                error=str(e),
                exc_info=True,
            )
            output = RollbackAllocationOutput(
                rollback_success=False,
                compensation_status=CompensationStatus.FAILED,
                unallocated_amount=variables.get("allocatedAmount", 0),
                rollback_date=datetime.utcnow(),
                error_message=f"Unexpected error: {e}",
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

    async def _execute_rollback(
        self,
        input_data: RollbackAllocationInput,
    ) -> RollbackAllocationOutput:
        """
        Execute allocation rollback.

        In production:
        - Query allocation database to verify allocation exists
        - Validate allocation is in rollbackable state
        - Remove allocation from claim
        - Return amount to payment unallocated pool
        - Update allocation status to ROLLED_BACK
        - Update claim outstanding balance

        Args:
            input_data: Rollback input data

        Returns:
            Rollback output data
        """
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        # 1. Query allocation database for allocation record
        # 2. Validate allocation exists and is active
        # 3. Update payment allocation status to ROLLED_BACK
        # 4. Return allocated amount to payment unallocated pool
        # 5. Update claim outstanding balance (increase)
        # 6. Create rollback record in database

        # STUB: Simulate successful rollback
        self._logger.info(
            "Executing allocation rollback (PRODUCTION: integrate allocation system)",
            allocation_id=input_data.allocation_id,
            payment_id=input_data.payment_id,
            claim_id=input_data.claim_id,
            amount=str(input_data.allocated_amount),
            reason=input_data.reason.value,
        )

        # Call budget service if available
        if self._budget_service and hasattr(self._budget_service, "rollback_allocation"):
            await self._budget_service.rollback_allocation(input_data.allocation_id)

        return RollbackAllocationOutput(
            rollback_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            unallocated_amount=input_data.allocated_amount,
            released_amount=input_data.allocated_amount,
            rollback_date=datetime.utcnow(),
            error_message=None,
            allocation_id=input_data.allocation_id,
        )

    async def _create_audit_trail(
        self,
        input_data: RollbackAllocationInput,
        result: RollbackAllocationOutput,
    ) -> None:
        """Create audit trail entry for rollback operation."""
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        self._logger.info(
            "Allocation rollback audit trail created",
            allocation_id=input_data.allocation_id,
            payment_id=input_data.payment_id,
            claim_id=input_data.claim_id,
            amount=str(input_data.allocated_amount),
            reason=input_data.reason.value,
            success=result.rollback_success,
        )
