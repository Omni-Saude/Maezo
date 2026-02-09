"""
CompensateProvisionWorker - SAGA compensation worker for undoing financial provisions.

This worker implements financial provision undo logic for transaction rollback:
- Reverts financial provision entries
- Reverses accounting entries
- Updates balance sheet impact
- Maintains audit trail

Business Rule: RN-COMP-002-CompensateProvisionDelegate.md
SAGA Pattern: Compensation for provision task (CPC 25)
Regulatory Compliance: CPC 25 (provision reversal), ANS RN 424/2017
Migrated from: com.hospital.revenuecycle.delegates.compensation.CompensateProvisionDelegate
Topic: compensate-financial-provision
BPMN Compensation: Compensate Task_Provide_Financially
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


class CompensateProvisionInput(BaseModel):
    """Input model for CompensateProvisionWorker."""

    provision_id: str = Field(
        ...,
        alias="provisionId",
        min_length=1,
        description="Financial provision ID to undo",
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
    provision_amount: Optional[Decimal] = Field(
        None,
        alias="provisionAmount",
        description="Amount of provision (optional)",
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

    @field_validator("provision_amount", mode="before")
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


class CompensateProvisionOutput(BaseModel):
    """Output model for CompensateProvisionWorker."""

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
    provision_reverted: bool = Field(
        ...,
        alias="provisionReverted",
        description="Whether provision was reverted",
    )
    accounting_reversals: list[str] = Field(
        default_factory=list,
        alias="accountingReversals",
        description="List of accounting reversals performed",
    )
    reversed_amount: Optional[Decimal] = Field(
        None,
        alias="reversedAmount",
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


class ProvisionCompensationError(BpmnErrorException):
    """Raised when provision compensation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="PROVISION_COMPENSATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-financial-provision", max_jobs=16, lock_duration=45000)
class CompensateProvisionWorker(BaseWorker):
    """
    SAGA compensation worker for undoing financial provisions.

    This worker undoes financial provision entries by:
    1. Validating provision undo request
    2. Checking if already compensated (idempotency)
    3. Reverting provision entry
    4. Creating reversal accounting entries
    5. Updating balance sheet impact
    6. Creating compensation audit record
    7. Notifying accounting system

    Input Variables:
        - provisionId: Financial provision ID to undo (required)
        - glosaId: Associated glosa ID (required)
        - claimId: Associated claim ID (required)
        - provisionAmount: Provision amount (optional)
        - reason: Compensation reason (required)
        - compensationContext: Additional context (optional)

    Output Variables:
        - compensationSuccess: Whether compensation succeeded (boolean)
        - compensationStatus: Compensation operation status
        - provisionReverted: Whether provision was reverted (boolean)
        - accountingReversals: List of accounting reversals
        - reversedAmount: Amount successfully reversed
        - compensationDate: When compensation was executed

    SAGA Pattern:
        - This is a compensation handler for ProvideFinanciallyWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if provision not found (SKIPPED)
        - Should succeed if provision already compensated (ALREADY_COMPENSATED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "provisionId": "PROV-001",
            "glosaId": "GLOSA-2026-001",
            "claimId": "CLM-2026-001",
            "provisionAmount": "5000.00",
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "compensationSuccess": true,
            "compensationStatus": "SUCCESS",
            "provisionReverted": true,
            "accountingReversals": ["REVERSAL_ENTRY_CREATED", "BALANCE_UPDATED"],
            "reversedAmount": "5000.00",
            "compensationDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, accounting_service=None, audit_service=None, **kwargs):
        """
        Initialize the compensate provision worker.

        Args:
            settings: Optional worker settings
            accounting_service: Optional accounting service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._accounting_service = accounting_service
        self._audit_service = audit_service
        self._compensations: dict[str, CompensateProvisionOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "compensate_provision"

    @property
    def requires_idempotency(self) -> bool:
        """Provision compensation requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        provision_id = variables.get("provisionId", "")
        claim_id = variables.get("claimId", "")
        return f"{provision_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process provision compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with compensation outcome
        """
        self._logger.info(
            "Processing provision compensation",
            job_key=str(getattr(job, "key", "unknown")),
            provision_id=variables.get("provisionId"),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = CompensateProvisionInput.model_validate(variables)

            # Check if already compensated (idempotency)
            cache_key = f"{input_data.provision_id}:{input_data.claim_id}"
            if cache_key in self._compensations:
                cached = self._compensations[cache_key]
                self._logger.info(
                    "Returning cached compensation result",
                    provision_id=input_data.provision_id,
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
                    "Provision compensation completed successfully",
                    provision_id=input_data.provision_id,
                    status=compensation_result.compensation_status.value,
                    reversals_count=len(compensation_result.accounting_reversals),
                )
                return WorkerResult.ok(compensation_result.model_dump(by_alias=True))
            else:
                self._logger.warning(
                    "Provision compensation failed",
                    provision_id=input_data.provision_id,
                    error=compensation_result.error_message,
                )
                return WorkerResult.bpmn_error(
                    error_code="PROVISION_COMPENSATION_FAILED",
                    error_message=compensation_result.error_message or "Provision compensation failed",
                )

        except ValidationError as e:
            self._logger.error(
                "Provision compensation validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_COMPENSATION_DATA",
                error_message=f"Compensation validation failed: {e}",
            )

        except ProvisionCompensationError as e:
            self._logger.error(
                "Provision compensation error",
                error=str(e),
                error_code=e.error_code,
            )
            output = CompensateProvisionOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                provision_reverted=False,
                compensation_date=datetime.utcnow(),
                error_message=e.message,
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Unexpected error during provision compensation",
                error=str(e),
                exc_info=True,
            )
            output = CompensateProvisionOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                provision_reverted=False,
                compensation_date=datetime.utcnow(),
                error_message=f"Unexpected error: {e}",
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

    async def _execute_compensation(
        self,
        input_data: CompensateProvisionInput,
    ) -> CompensateProvisionOutput:
        """
        Execute provision compensation.

        In production:
        - Query accounting database for provision record
        - Verify provision amount and status
        - Create reversal journal entry
        - Update balance sheet impact accounts
        - Record provision reversal
        - Notify accounting system
        - Update claim financial status

        Args:
            input_data: Compensation input data

        Returns:
            Compensation output data
        """
        self._logger.info(
            "Executing provision compensation (PRODUCTION: integrate accounting system)",
            provision_id=input_data.provision_id,
            glosa_id=input_data.glosa_id,
            claim_id=input_data.claim_id,
            amount=str(input_data.provision_amount) if input_data.provision_amount else "unknown",
            reason=input_data.reason.value,
        )

        # Simulate: provision exists and is reverted
        accounting_reversals = [
            "REVERSAL_JOURNAL_ENTRY_CREATED",
            "BALANCE_SHEET_UPDATED",
            "PROVISION_BALANCE_CLEARED",
        ]
        reversed_amount = input_data.provision_amount or Decimal("0.00")

        return CompensateProvisionOutput(
            compensation_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            provision_reverted=True,
            accounting_reversals=accounting_reversals,
            reversed_amount=reversed_amount,
            compensation_date=datetime.utcnow(),
            error_message=None,
        )
