"""
ApplyCorrectionsWorker - Zeebe worker for applying claim corrections.

This worker implements correction logic for the Brazilian healthcare
revenue cycle, including:
- Applying glosa corrections
- Adjusting charges for denied items
- Processing insurance carrier feedback
- Updating claim amounts based on corrections

Business Rule: RN-GLOSA-002-ApplyCorrections.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00
Migrated from: com.hospital.revenuecycle.delegates.ApplyCorrectionsDelegate

Section references:
- Glosa (claim denial) correction application
- Claim amount adjustment logic
- Insurance carrier feedback processing
- Audit trail for all corrections

Topic: apply-corrections
BPMN Task: Task_Apply_Corrections
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ConfigDict, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class Correction(BaseModel):
    """Model for a claim correction."""
    model_config = ConfigDict(populate_by_name=True)

    correction_id: str = Field(..., alias="correctionId")
    correction_type: str = Field(..., alias="correctionType")
    amount: Decimal = Field(..., ge=0)
    reason: Optional[str] = None
    applied_to_charge_code: str = Field(..., alias="appliedToChargeCode")


class CorrectedCharge(BaseModel):
    """Model for a charge after corrections."""
    model_config = ConfigDict(populate_by_name=True)

    charge_code: str = Field(..., alias="chargeCode")
    original_amount: Decimal = Field(..., alias="originalAmount", ge=0)
    corrected_amount: Decimal = Field(..., alias="correctedAmount", ge=0)
    total_corrections: Decimal = Field(..., alias="totalCorrections")
    correction_count: int = Field(..., alias="correctionCount")


class ApplyCorrectionsInput(BaseModel):
    """Input model for applying corrections."""
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(..., alias="claimId")
    original_claim_amount: Decimal = Field(..., alias="originalClaimAmount", ge=0)
    corrections: list[Correction] = Field(default_factory=list)


class ApplyCorrectionsOutput(BaseModel):
    """Output model for applying corrections."""
    model_config = ConfigDict(populate_by_name=True)

    corrections_applied: bool = Field(..., alias="correctionsApplied")
    original_claim_amount: Decimal = Field(..., alias="originalClaimAmount", ge=0)
    corrected_claim_amount: Decimal = Field(..., alias="correctedClaimAmount", ge=0)
    total_adjustments: Decimal = Field(..., alias="totalAdjustments")
    corrected_charges: list[CorrectedCharge] = Field(
        default_factory=list,
        alias="correctedCharges"
    )
    correction_count: int = Field(..., alias="correctionCount")


class CorrectionsValidationError(BpmnErrorException):
    """Raised when corrections validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="CORRECTIONS_VALIDATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="apply-corrections", max_jobs=16, lock_duration=30000)
class ApplyCorrectionsWorker(BaseWorker):
    """
    Zeebe worker for applying corrections to claims.

    This worker:
    1. Validates corrections data
    2. Applies each correction to appropriate charges
    3. Recalculates claim amounts
    4. Tracks all corrections applied
    5. Returns updated claim with corrections

    Input Variables:
        - claimId: Claim identifier (required)
        - originalClaimAmount: Original claim amount (required)
        - corrections: List of corrections to apply (required)

    Output Variables:
        - correctionsApplied: Whether corrections were applied
        - originalClaimAmount: Original claim amount
        - correctedClaimAmount: Claim amount after corrections
        - totalAdjustments: Total amount of adjustments
        - correctedCharges: List of charges with corrections
        - correctionCount: Number of corrections applied
    """

    def __init__(self, settings=None, service=None, **kwargs):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            service: Optional service (for testing)
        """
        super().__init__(settings=settings)
        self._service = service

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "apply_corrections"

    @property
    def requires_idempotency(self) -> bool:
        """This worker benefits from idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract claim ID for idempotency key generation."""
        claim_id = variables.get("claimId", "")
        return f"{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the apply corrections task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with correction results
        """
        self._logger.info(
            "Processing apply corrections",
            job_key=str(getattr(job, "key", "unknown")),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = ApplyCorrectionsInput.model_validate(variables)

            # Validate input
            await self._validate_input(input_data)

            # Apply corrections
            corrected_charges, total_adjustments = await self._apply_corrections(
                input_data
            )

            # Calculate new claim amount
            corrected_claim_amount = input_data.original_claim_amount - total_adjustments

            # Create output
            output = ApplyCorrectionsOutput(
                correctionsApplied=len(input_data.corrections) > 0,
                originalClaimAmount=input_data.original_claim_amount,
                correctedClaimAmount=max(Decimal("0"), corrected_claim_amount),
                totalAdjustments=total_adjustments,
                correctedCharges=corrected_charges,
                correctionCount=len(input_data.corrections),
            )

            self._logger.info(
                "Corrections applied",
                claim_id=input_data.claim_id,
                original_amount=str(input_data.original_claim_amount),
                corrected_amount=str(output.corrected_claim_amount),
                total_adjustments=str(total_adjustments),
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Input validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_CORRECTIONS_INPUT",
                error_message=f"Input validation failed: {e}",
            )

        except CorrectionsValidationError as e:
            self._logger.error(
                "Corrections validation error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during corrections application",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Failed to apply corrections: {e}",
                retry=True,
            )

    async def _validate_input(self, input_data: ApplyCorrectionsInput) -> None:
        """Validate input data and business rules."""
        if input_data.original_claim_amount < 0:
            raise CorrectionsValidationError(
                "Original claim amount must be non-negative",
                details={"claim_id": input_data.claim_id},
            )

    async def _apply_corrections(
        self,
        input_data: ApplyCorrectionsInput,
    ) -> tuple[list[CorrectedCharge], Decimal]:
        """
        Apply corrections to charges.

        Args:
            input_data: Input data with corrections

        Returns:
            Tuple of (corrected_charges, total_adjustments)
        """
        # Group corrections by charge code
        corrections_by_code: dict[str, list[Correction]] = {}

        for correction in input_data.corrections:
            code = correction.applied_to_charge_code
            if code not in corrections_by_code:
                corrections_by_code[code] = []
            corrections_by_code[code].append(correction)

        # Generate corrected charges
        corrected_charges: list[CorrectedCharge] = []
        total_adjustments = Decimal("0")

        for charge_code, charge_corrections in corrections_by_code.items():
            # Calculate total corrections for this charge
            correction_total = sum(
                (c.amount for c in charge_corrections),
                Decimal("0"),
            )

            total_adjustments += correction_total

            # Create corrected charge record
            # Note: original_amount would normally come from the claim data
            # For this worker, we estimate based on proportional distribution
            original_proportion = input_data.original_claim_amount / Decimal(
                max(1, len(corrections_by_code))
            )

            corrected_charges.append(
                CorrectedCharge(
                    chargeCode=charge_code,
                    originalAmount=original_proportion,
                    correctedAmount=max(Decimal("0"), original_proportion - correction_total),
                    totalCorrections=correction_total,
                    correctionCount=len(charge_corrections),
                )
            )

        return corrected_charges, total_adjustments
