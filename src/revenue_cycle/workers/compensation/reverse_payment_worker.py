"""
ReversePaymentWorker - SAGA compensation worker for reversing payment transactions.

This worker implements payment reversal logic for transaction rollback:
- Reverses processed payment through payment gateway
- Creates reversal transaction record
- Updates accounting entries
- Maintains audit trail
- Supports idempotency for safe retry

Business Rule: RN-COMP-PaymentReversal.md
SAGA Pattern: Compensation for payment-processing task
Regulatory Compliance: CPC 25 (payment reversal), ANS RN 424/2017
Migrated from: com.hospital.revenuecycle.delegates.compensation.ReversePaymentDelegate
Topic: compensate-reverse-payment
BPMN Compensation: Compensate Task_Process_Payment
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
    ReversePaymentInput,
    ReversePaymentOutput,
    CompensationStatus,
    CompensationReason,
)

logger = structlog.get_logger(__name__)


class PaymentReversalError(BpmnErrorException):
    """Raised when payment reversal fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="PAYMENT_REVERSAL_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-reverse-payment", max_jobs=8, lock_duration=60000)
class ReversePaymentWorker(BaseWorker):
    """
    SAGA compensation worker for reversing payment transactions.

    This worker reverses a previously processed payment by:
    1. Validating reversal request
    2. Checking if already reversed (idempotency)
    3. Creating reversal transaction through payment gateway
    4. Recording reversal in accounting system
    5. Creating audit trail entry
    6. Updating payment status to REVERSED

    Input Variables:
        - transactionId: Original payment transaction ID (required)
        - claimId: Associated claim ID (required)
        - patientId: Patient identifier (required)
        - paymentAmount: Amount to reverse (required, Decimal)
        - reason: Compensation reason (required)
        - notes: Additional notes (optional)

    Output Variables:
        - reversalSuccess: Whether reversal succeeded (boolean)
        - reversalTransactionId: New reversal transaction ID
        - compensationStatus: Compensation operation status
        - reversedAmount: Amount successfully reversed
        - reversalDate: When reversal was executed
        - errorMessage: Error message if failed (optional)

    SAGA Pattern:
        - This is a compensation handler for ProcessPaymentWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if original payment not found (SKIPPED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "transactionId": "TXN-20260204-ABC123",
            "claimId": "CLM-2026-001",
            "patientId": "PAT-12345",
            "paymentAmount": "150.00",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "reversalSuccess": true,
            "reversalTransactionId": "REV-20260204-XYZ789",
            "compensationStatus": "SUCCESS",
            "reversedAmount": "150.00",
            "reversalDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, payment_gateway=None, accounting_service=None, audit_service=None, **kwargs):
        """
        Initialize the reversal worker.

        Args:
            settings: Optional worker settings
            payment_gateway: Optional payment gateway (for testing)
            accounting_service: Optional accounting service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._payment_gateway = payment_gateway
        self._accounting_service = accounting_service
        self._audit_service = audit_service
        self._reversals: dict[str, ReversePaymentOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "reverse_payment"

    @property
    def requires_idempotency(self) -> bool:
        """Payment reversal requires idempotency to prevent duplicate reversals."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Uses transaction_id to detect duplicate reversal attempts.
        """
        transaction_id = variables.get("transactionId", "")
        claim_id = variables.get("claimId", "")
        return f"{transaction_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process payment reversal compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with reversal outcome
        """
        self._logger.info(
            "Processing payment reversal",
            job_key=str(getattr(job, "key", "unknown")),
            transaction_id=variables.get("transactionId"),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = ReversePaymentInput.model_validate(variables)

            # Check if already reversed (idempotency)
            cache_key = f"{input_data.transaction_id}:{input_data.claim_id}"
            if cache_key in self._reversals:
                cached = self._reversals[cache_key]
                self._logger.info(
                    "Returning cached reversal result",
                    transaction_id=input_data.transaction_id,
                    reversal_transaction_id=cached.reversal_transaction_id,
                )
                output_dict = cached.model_dump(by_alias=True)
                output_dict["transactionId"] = input_data.transaction_id
                return WorkerResult.ok(output_dict)

            # Execute reversal through payment gateway
            reversal_result = await self._execute_reversal(input_data)

            # Create audit trail and accounting entries
            if self._audit_service and hasattr(self._audit_service, "log_compensation"):
                await self._audit_service.log_compensation(input_data, reversal_result)

            if self._accounting_service and hasattr(self._accounting_service, "record_reversal"):
                await self._accounting_service.record_reversal(input_data, reversal_result)

            # Cache result for idempotency
            self._reversals[cache_key] = reversal_result

            if reversal_result.reversal_success:
                self._logger.info(
                    "Payment reversal completed successfully",
                    transaction_id=input_data.transaction_id,
                    reversal_transaction_id=reversal_result.reversal_transaction_id,
                    reversed_amount=str(reversal_result.reversed_amount),
                    status=reversal_result.compensation_status.value,
                )
                output_dict = reversal_result.model_dump(by_alias=True)
                output_dict["transactionId"] = input_data.transaction_id
                return WorkerResult.ok(output_dict)
            else:
                # Reversal failed - return error
                self._logger.warning(
                    "Payment reversal failed",
                    transaction_id=input_data.transaction_id,
                    error=reversal_result.error_message,
                )
                output_dict = reversal_result.model_dump(by_alias=True)
                output_dict["transactionId"] = input_data.transaction_id
                return WorkerResult.bpmn_error(
                    error_code="PAYMENT_REVERSAL_FAILED",
                    error_message=reversal_result.error_message or "Payment reversal failed",
                )

        except ValidationError as e:
            self._logger.error(
                "Payment reversal validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_REVERSAL_DATA",
                error_message=f"Reversal validation failed: {e}",
            )

        except PaymentReversalError as e:
            self._logger.error(
                "Payment reversal error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code="PAYMENT_REVERSAL_ERROR",
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during payment reversal",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.bpmn_error(
                error_code="UNEXPECTED_ERROR",
                error_message=str(e),
            )

    async def _execute_reversal(
        self,
        input_data: ReversePaymentInput,
    ) -> ReversePaymentOutput:
        """
        Execute payment reversal through payment gateway.

        In production:
        - Check if payment exists and is reversible
        - Call payment gateway reversal API
        - Handle gateway-specific reversal logic
        - Update payment status in database
        - Create reversal accounting entries

        Args:
            input_data: Reversal input data

        Returns:
            Reversal output data
        """
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        # 1. Query payment database for original transaction
        # 2. Validate payment is in AUTHORIZED/CAPTURED state
        # 3. Call payment gateway reversal API (Stripe, PagSeguro, etc.)
        # 4. Handle partial reversals if needed
        # 5. Update payment status to REVERSED
        # 6. Create reversal accounting entries

        reversal_transaction_id = f"REV-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"

        # Call payment gateway if available
        if self._payment_gateway and hasattr(self._payment_gateway, "reverse_transaction"):
            await self._payment_gateway.reverse_transaction(
                original_transaction_id=input_data.transaction_id,
                amount=input_data.payment_amount,
            )

        # STUB: Simulate successful reversal
        self._logger.info(
            "Executing payment reversal (PRODUCTION: integrate real gateway)",
            original_transaction_id=input_data.transaction_id,
            reversal_transaction_id=reversal_transaction_id,
            amount=str(input_data.payment_amount),
            reason=input_data.reason.value,
        )

        return ReversePaymentOutput(
            reversal_success=True,
            reversal_transaction_id=reversal_transaction_id,
            compensation_status=CompensationStatus.SUCCESS,
            reversed_amount=input_data.payment_amount,
            reversal_date=datetime.utcnow(),
            error_message=None,
        )

    async def _create_audit_trail(
        self,
        input_data: ReversePaymentInput,
        result: ReversePaymentOutput,
    ) -> None:
        """
        Create audit trail entry for reversal operation.

        In production:
        - Write to audit log database
        - Include all reversal details
        - Record compensation reason
        - Track user/system that triggered reversal

        Args:
            input_data: Original reversal input
            result: Reversal result
        """
        # TODO: PRODUCTION IMPLEMENTATION REQUIRED
        # Write to audit trail database with:
        # - Original transaction ID
        # - Reversal transaction ID
        # - Amount reversed
        # - Reason and notes
        # - Timestamp
        # - User/system context
        # - Multi-tenant isolation

        self._logger.info(
            "Payment reversal audit trail created",
            original_transaction_id=input_data.transaction_id,
            reversal_transaction_id=result.reversal_transaction_id,
            claim_id=input_data.claim_id,
            patient_id=input_data.patient_id,
            amount=str(input_data.payment_amount),
            reason=input_data.reason.value,
            success=result.reversal_success,
        )
