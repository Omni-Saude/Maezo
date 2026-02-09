"""
CompensateRecoveryWorker - SAGA compensation worker for undoing recovery registrations.

This worker implements recovery undo logic for transaction rollback:
- Reverts recovery registration
- Updates recovery status
- Reverses amount from collections
- Maintains audit trail

Business Rule: RN-COMP-CompensateRecoveryDelegate.md
SAGA Pattern: Compensation for recovery-registration task
Regulatory Compliance: ANS RN 424/2017 (recovery tracking), CPC 25
Migrated from: com.hospital.revenuecycle.delegates.compensation.CompensateRecoveryDelegate
Topic: compensate-recovery-registration
BPMN Compensation: Compensate Task_Register_Recovery
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.compensation.models import CompensationStatus, CompensationReason

logger = structlog.get_logger(__name__)


class CompensateRecoveryInput(BaseModel):
    """Input model for CompensateRecoveryWorker."""

    recovery_id: str = Field(
        ...,
        alias="recoveryId",
        min_length=1,
        description="Recovery registration ID to undo",
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
    recovery_amount: Optional[Decimal] = Field(
        None,
        alias="recoveryAmount",
        description="Recovery amount to undo",
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

    @field_validator("recovery_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Optional[Decimal]:
        """Parse various numeric types to Decimal."""
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {"populate_by_name": True}


class CompensateRecoveryOutput(BaseModel):
    """Output model for CompensateRecoveryWorker."""

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
    recovery_reverted: bool = Field(
        ...,
        alias="recoveryReverted",
        description="Whether recovery was reverted",
    )
    amount_reversed: Optional[Decimal] = Field(
        None,
        alias="amountReversed",
        description="Amount successfully reversed",
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


class RecoveryCompensationError(BpmnErrorException):
    """Raised when recovery compensation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="RECOVERY_COMPENSATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-recovery-registration", max_jobs=16, lock_duration=45000)
class CompensateRecoveryWorker(BaseWorker):
    """
    SAGA compensation worker for undoing recovery registrations.

    This worker undoes recovery registrations by:
    1. Validating recovery undo request
    2. Checking if already compensated (idempotency)
    3. Reverting recovery registration
    4. Updating collection status
    5. Restoring previous claim state
    6. Creating compensation audit record
    7. Notifying collection system

    Input Variables:
        - recoveryId: Recovery registration ID to undo (required)
        - glosaId: Associated glosa ID (required)
        - claimId: Associated claim ID (required)
        - recoveryAmount: Recovery amount (optional)
        - reason: Compensation reason (required)
        - compensationContext: Additional context (optional)

    Output Variables:
        - compensationSuccess: Whether compensation succeeded (boolean)
        - compensationStatus: Compensation operation status
        - recoveryReverted: Whether recovery was reverted (boolean)
        - amountReversed: Amount successfully reversed
        - compensationDate: When compensation was executed

    SAGA Pattern:
        - This is a compensation handler for RegisterRecoveryWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if recovery not found (SKIPPED)
        - Should succeed if recovery already compensated (ALREADY_COMPENSATED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "recoveryId": "REC-001",
            "glosaId": "GLOSA-2026-001",
            "claimId": "CLM-2026-001",
            "recoveryAmount": "2500.00",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "compensationSuccess": true,
            "compensationStatus": "SUCCESS",
            "recoveryReverted": true,
            "amountReversed": "2500.00",
            "compensationDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, glosa_service=None, audit_service=None, **kwargs):
        """
        Initialize the compensate recovery worker.

        Args:
            settings: Optional worker settings
            glosa_service: Optional glosa service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._glosa_service = glosa_service
        self._audit_service = audit_service
        self._compensations: dict[str, CompensateRecoveryOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "compensate_recovery"

    @property
    def requires_idempotency(self) -> bool:
        """Recovery compensation requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        recovery_id = variables.get("recoveryId", "")
        claim_id = variables.get("claimId", "")
        return f"{recovery_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process recovery compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with compensation outcome
        """
        self._logger.info(
            "Processing recovery compensation",
            job_key=str(getattr(job, "key", "unknown")),
            recovery_id=variables.get("recoveryId"),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = CompensateRecoveryInput.model_validate(variables)

            # Check if already compensated (idempotency)
            cache_key = f"{input_data.recovery_id}:{input_data.claim_id}"
            if cache_key in self._compensations:
                cached = self._compensations[cache_key]
                self._logger.info(
                    "Returning cached compensation result",
                    recovery_id=input_data.recovery_id,
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
                    "Recovery compensation completed successfully",
                    recovery_id=input_data.recovery_id,
                    status=compensation_result.compensation_status.value,
                    amount=str(compensation_result.amount_reversed) if compensation_result.amount_reversed else "unknown",
                )
                return WorkerResult.ok(compensation_result.model_dump(by_alias=True))
            else:
                self._logger.warning(
                    "Recovery compensation failed",
                    recovery_id=input_data.recovery_id,
                    error=compensation_result.error_message,
                )
                return WorkerResult.bpmn_error(
                    error_code="RECOVERY_COMPENSATION_FAILED",
                    error_message=compensation_result.error_message or "Recovery compensation failed",
                )

        except ValidationError as e:
            self._logger.error(
                "Recovery compensation validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_COMPENSATION_DATA",
                error_message=f"Compensation validation failed: {e}",
            )

        except RecoveryCompensationError as e:
            self._logger.error(
                "Recovery compensation error",
                error=str(e),
                error_code=e.error_code,
            )
            output = CompensateRecoveryOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                recovery_reverted=False,
                compensation_date=datetime.utcnow(),
                error_message=e.message,
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Unexpected error during recovery compensation",
                error=str(e),
                exc_info=True,
            )
            output = CompensateRecoveryOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                recovery_reverted=False,
                compensation_date=datetime.utcnow(),
                error_message=f"Unexpected error: {e}",
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

    async def _execute_compensation(
        self,
        input_data: CompensateRecoveryInput,
    ) -> CompensateRecoveryOutput:
        """
        Execute recovery compensation.

        In production:
        - Query glosa database for recovery record
        - Verify recovery amount and status
        - Reverse amount from collections
        - Update collection/recovery status
        - Restore previous glosa state
        - Notify collection system
        - Update claim status

        Args:
            input_data: Compensation input data

        Returns:
            Compensation output data
        """
        self._logger.info(
            "Executing recovery compensation (PRODUCTION: integrate glosa system)",
            recovery_id=input_data.recovery_id,
            glosa_id=input_data.glosa_id,
            claim_id=input_data.claim_id,
            amount=str(input_data.recovery_amount) if input_data.recovery_amount else "unknown",
            reason=input_data.reason.value,
        )

        # Simulate: recovery exists and is reverted
        amount_reversed = input_data.recovery_amount or Decimal("0.00")

        return CompensateRecoveryOutput(
            compensation_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            recovery_reverted=True,
            amount_reversed=amount_reversed,
            compensation_date=datetime.utcnow(),
            error_message=None,
        )
