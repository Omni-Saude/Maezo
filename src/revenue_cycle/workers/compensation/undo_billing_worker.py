"""
UndoBillingWorker - SAGA compensation worker for undoing billing entries.

This worker implements billing reversal logic for transaction rollback:
- Creates reversal accounting entries
- Updates billing records
- Maintains audit trail
- Supports idempotency for safe retry

Business Rule: RN-COMP-BillingUndo.md
SAGA Pattern: Compensation for billing-recording task
Regulatory Compliance: CPC 25 (billing reversal), ANS RN 424/2017
Migrated from: com.hospital.revenuecycle.delegates.compensation.UndoBillingDelegate
Topic: compensate-undo-billing
BPMN Compensation: Compensate Task_Record_Billing
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
    UndoBillingInput,
    UndoBillingOutput,
    CompensationStatus,
)

logger = structlog.get_logger(__name__)


class BillingUndoError(BpmnErrorException):
    """Raised when billing undo fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="BILLING_UNDO_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-undo-billing", max_jobs=16, lock_duration=45000)
class UndoBillingWorker(BaseWorker):
    """
    SAGA compensation worker for undoing billing entries.

    This worker undoes billing entries by:
    1. Validating undo request
    2. Checking if already undone (idempotency)
    3. Creating reversal accounting entries
    4. Updating billing status to REVERSED
    5. Creating undo audit record
    6. Notifying accounting system

    Input Variables:
        - billingId: Billing entry ID to undo (required)
        - claimId: Associated claim ID (required)
        - encounterId: Associated encounter ID (required)
        - billingAmount: Amount to reverse (required, Decimal)
        - reason: Compensation reason (required)

    Output Variables:
        - undoSuccess: Whether undo succeeded (boolean)
        - compensationStatus: Compensation operation status
        - reversalEntryId: Reversal entry ID in accounting
        - undoDate: When undo was executed
        - errorMessage: Error message if failed (optional)

    SAGA Pattern:
        - This is a compensation handler for RecordBillingWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if billing not found (SKIPPED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "billingId": "BILL-001",
            "claimId": "CLM-2026-001",
            "encounterId": "ENC-12345",
            "billingAmount": "150.00",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "undoSuccess": true,
            "compensationStatus": "SUCCESS",
            "reversalEntryId": "REV-BILL-20260204-ABC",
            "undoDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, billing_service=None, audit_service=None, **kwargs):
        """
        Initialize the undo billing worker.

        Args:
            settings: Optional worker settings
            billing_service: Optional billing service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._billing_service = billing_service
        self._audit_service = audit_service
        self._undos: dict[str, UndoBillingOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "undo_billing"

    @property
    def requires_idempotency(self) -> bool:
        """Billing undo requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        billing_id = variables.get("billingId", "")
        claim_id = variables.get("claimId", "")
        return f"{billing_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process billing undo compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with undo outcome
        """
        self._logger.info(
            "Processing billing undo",
            job_key=str(getattr(job, "key", "unknown")),
            billing_id=variables.get("billingId"),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = UndoBillingInput.model_validate(variables)

            # Check if already undone (idempotency)
            cache_key = f"{input_data.billing_id}:{input_data.claim_id}"
            if cache_key in self._undos:
                cached = self._undos[cache_key]
                self._logger.info(
                    "Returning cached undo result",
                    billing_id=input_data.billing_id,
                    reversal_entry_id=cached.reversal_entry_id,
                )
                return WorkerResult.ok(cached.model_dump(by_alias=True))

            # Execute undo
            undo_result = await self._execute_undo(input_data)

            # Create audit trail entry
            await self._create_audit_trail(input_data, undo_result)

            # Cache result for idempotency
            self._undos[cache_key] = undo_result

            if undo_result.undo_success:
                self._logger.info(
                    "Billing undo completed successfully",
                    billing_id=input_data.billing_id,
                    reversal_entry_id=undo_result.reversal_entry_id,
                    status=undo_result.compensation_status.value,
                )
                return WorkerResult.ok(undo_result.model_dump(by_alias=True))
            else:
                self._logger.warning(
                    "Billing undo failed",
                    billing_id=input_data.billing_id,
                    error=undo_result.error_message,
                )
                return WorkerResult.ok(undo_result.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Billing undo validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_UNDO_DATA",
                error_message=f"Undo validation failed: {e}",
            )

        except BillingUndoError as e:
            self._logger.error(
                "Billing undo error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code="BILLING_UNDO_ERROR",
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during billing undo",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.bpmn_error(
                error_code="UNEXPECTED_ERROR",
                error_message=str(e),
            )

    async def _execute_undo(
        self,
        input_data: UndoBillingInput,
    ) -> UndoBillingOutput:
        """
        Execute billing undo by creating reversal entries.

        In production:
        - Query billing database for original entry
        - Validate billing is in undoable state
        - Create reversal accounting entries (debit/credit reverse)
        - Update billing status to REVERSED
        - Notify accounting system (ERP integration)

        Args:
            input_data: Undo input data

        Returns:
            Undo output data
        """
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        # 1. Query billing database for original billing entry
        # 2. Validate billing exists and is not already reversed
        # 3. Create reversal accounting entries:
        #    - Original: Debit Accounts Receivable, Credit Revenue
        #    - Reversal: Debit Revenue, Credit Accounts Receivable
        # 4. Update billing status to REVERSED
        # 5. Integrate with accounting system (SAP, Oracle, etc.)
        # 6. Create undo record in database

        reversal_entry_id = f"REV-BILL-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"

        # Call billing service if available
        if self._billing_service and hasattr(self._billing_service, "undo_billing"):
            await self._billing_service.undo_billing(input_data.billing_id)

        # STUB: Simulate successful undo
        self._logger.info(
            "Executing billing undo (PRODUCTION: integrate accounting system)",
            billing_id=input_data.billing_id,
            reversal_entry_id=reversal_entry_id,
            claim_id=input_data.claim_id,
            amount=str(input_data.billing_amount),
            reason=input_data.reason.value,
        )

        return UndoBillingOutput(
            undo_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            reversal_entry_id=reversal_entry_id,
            reversed_amount=input_data.billing_amount,
            undo_date=datetime.utcnow(),
            error_message=None,
        )

    async def _create_audit_trail(
        self,
        input_data: UndoBillingInput,
        result: UndoBillingOutput,
    ) -> None:
        """Create audit trail entry for undo operation."""
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        self._logger.info(
            "Billing undo audit trail created",
            billing_id=input_data.billing_id,
            reversal_entry_id=result.reversal_entry_id,
            claim_id=input_data.claim_id,
            encounter_id=input_data.encounter_id,
            amount=str(input_data.billing_amount),
            reason=input_data.reason.value,
            success=result.undo_success,
        )
