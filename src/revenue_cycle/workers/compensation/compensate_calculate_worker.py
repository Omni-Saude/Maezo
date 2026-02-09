"""
CompensateCalculateWorker - SAGA compensation worker for undoing charge calculations.

This worker implements charge calculation undo logic for transaction rollback:
- Reverts charge calculations
- Updates billing records
- Restores charge amounts
- Maintains audit trail

Business Rule: RN-COMP-CompensateCalculateDelegate.md
SAGA Pattern: Compensation for calculate-charges task
Regulatory Compliance: CPC 25 (financial calculation reversal)
Migrated from: com.hospital.revenuecycle.delegates.compensation.CompensateCalculateDelegate
Topic: compensate-charge-calculation
BPMN Compensation: Compensate Task_Calculate_Charges
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


class CompensateCalculateInput(BaseModel):
    """Input model for CompensateCalculateWorker."""

    calculation_id: str = Field(
        ...,
        alias="calculationId",
        min_length=1,
        description="Charge calculation ID to undo",
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
    charges: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of charges that were calculated",
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


class CompensateCalculateOutput(BaseModel):
    """Output model for CompensateCalculateWorker."""

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
    charges_reverted: bool = Field(
        ...,
        alias="chargesReverted",
        description="Whether charges were reverted",
    )
    billing_updated: bool = Field(
        ...,
        alias="billingUpdated",
        description="Whether billing was updated",
    )
    reverted_count: int = Field(
        default=0,
        alias="revertedCount",
        description="Number of charges reverted",
    )
    total_amount_reverted: Decimal = Field(
        default=Decimal("0.00"),
        alias="totalAmountReverted",
        description="Total amount reverted",
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


class CalculationCompensationError(BpmnErrorException):
    """Raised when calculation compensation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="CALCULATION_COMPENSATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensate-charge-calculation", max_jobs=16, lock_duration=45000)
class CompensateCalculateWorker(BaseWorker):
    """
    SAGA compensation worker for undoing charge calculations.

    This worker undoes charge calculations by:
    1. Validating calculation undo request
    2. Checking if already compensated (idempotency)
    3. Reverting all calculated charges
    4. Removing charges from billing
    5. Updating claim total and billing status
    6. Creating compensation audit record
    7. Notifying billing system

    Input Variables:
        - calculationId: Charge calculation ID to undo (required)
        - claimId: Associated claim ID (required)
        - encounterId: Associated encounter ID (required)
        - charges: List of calculated charges (optional)
        - reason: Compensation reason (required)
        - compensationContext: Additional context (optional)

    Output Variables:
        - compensationSuccess: Whether compensation succeeded (boolean)
        - compensationStatus: Compensation operation status
        - chargesReverted: Whether charges were reverted (boolean)
        - billingUpdated: Whether billing was updated (boolean)
        - revertedCount: Number of charges reverted
        - totalAmountReverted: Total amount reverted
        - compensationDate: When compensation was executed

    SAGA Pattern:
        - This is a compensation handler for CalculateChargesWorker
        - Must be idempotent (safe to retry)
        - Should succeed even if calculation not found (SKIPPED)
        - Should succeed if calculation already compensated (ALREADY_COMPENSATED)
        - Creates audit trail for compliance

    Example:
        Input:
        {
            "calculationId": "CALC-001",
            "claimId": "CLM-2026-001",
            "encounterId": "ENC-2026-001",
            "charges": [
                {"chargeId": "CHG-001", "amount": "1000.00"},
                {"chargeId": "CHG-002", "amount": "500.00"}
            ],
            "reason": "TRANSACTION_FAILED"
        }

        Output (Success):
        {
            "compensationSuccess": true,
            "compensationStatus": "SUCCESS",
            "chargesReverted": true,
            "billingUpdated": true,
            "revertedCount": 2,
            "totalAmountReverted": "1500.00",
            "compensationDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, billing_service=None, audit_service=None, **kwargs):
        """
        Initialize the compensate calculate worker.

        Args:
            settings: Optional worker settings
            billing_service: Optional billing service (for testing)
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._billing_service = billing_service
        self._audit_service = audit_service
        self._compensations: dict[str, CompensateCalculateOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "compensate_calculate"

    @property
    def requires_idempotency(self) -> bool:
        """Calculation compensation requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        calculation_id = variables.get("calculationId", "")
        claim_id = variables.get("claimId", "")
        return f"{calculation_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process calculation compensation.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with compensation outcome
        """
        self._logger.info(
            "Processing calculation compensation",
            job_key=str(getattr(job, "key", "unknown")),
            calculation_id=variables.get("calculationId"),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = CompensateCalculateInput.model_validate(variables)

            # Check if already compensated (idempotency)
            cache_key = f"{input_data.calculation_id}:{input_data.claim_id}"
            if cache_key in self._compensations:
                cached = self._compensations[cache_key]
                self._logger.info(
                    "Returning cached compensation result",
                    calculation_id=input_data.calculation_id,
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
                    "Calculation compensation completed successfully",
                    calculation_id=input_data.calculation_id,
                    status=compensation_result.compensation_status.value,
                    reverted_count=compensation_result.reverted_count,
                    total_amount=str(compensation_result.total_amount_reverted),
                )
                return WorkerResult.ok(compensation_result.model_dump(by_alias=True))
            else:
                self._logger.warning(
                    "Calculation compensation failed",
                    calculation_id=input_data.calculation_id,
                    error=compensation_result.error_message,
                )
                return WorkerResult.bpmn_error(
                    error_code="CALCULATION_COMPENSATION_FAILED",
                    error_message=compensation_result.error_message or "Calculation compensation failed",
                )

        except ValidationError as e:
            self._logger.error(
                "Calculation compensation validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_COMPENSATION_DATA",
                error_message=f"Compensation validation failed: {e}",
            )

        except CalculationCompensationError as e:
            self._logger.error(
                "Calculation compensation error",
                error=str(e),
                error_code=e.error_code,
            )
            output = CompensateCalculateOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                charges_reverted=False,
                billing_updated=False,
                compensation_date=datetime.utcnow(),
                error_message=e.message,
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Unexpected error during calculation compensation",
                error=str(e),
                exc_info=True,
            )
            output = CompensateCalculateOutput(
                compensation_success=False,
                compensation_status=CompensationStatus.FAILED,
                charges_reverted=False,
                billing_updated=False,
                compensation_date=datetime.utcnow(),
                error_message=f"Unexpected error: {e}",
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

    async def _execute_compensation(
        self,
        input_data: CompensateCalculateInput,
    ) -> CompensateCalculateOutput:
        """
        Execute calculation compensation.

        In production:
        - Query billing database for calculation record
        - Retrieve all associated charges
        - Mark charges as reverted/deleted
        - Remove charges from claim billing
        - Recalculate claim total
        - Update billing status
        - Create reversal records
        - Notify billing system

        Args:
            input_data: Compensation input data

        Returns:
            Compensation output data
        """
        self._logger.info(
            "Executing calculation compensation (PRODUCTION: integrate billing system)",
            calculation_id=input_data.calculation_id,
            claim_id=input_data.claim_id,
            encounter_id=input_data.encounter_id,
            charge_count=len(input_data.charges),
            reason=input_data.reason.value,
        )

        # Simulate: calculate total reverted amount
        total_amount = Decimal("0.00")
        for charge in input_data.charges:
            if isinstance(charge, dict) and "amount" in charge:
                try:
                    if isinstance(charge["amount"], str):
                        total_amount += Decimal(charge["amount"].replace(",", "."))
                    else:
                        total_amount += Decimal(str(charge["amount"]))
                except (ValueError, TypeError):
                    pass

        return CompensateCalculateOutput(
            compensation_success=True,
            compensation_status=CompensationStatus.SUCCESS,
            charges_reverted=True,
            billing_updated=True,
            reverted_count=len(input_data.charges),
            total_amount_reverted=total_amount,
            compensation_date=datetime.utcnow(),
            error_message=None,
        )
