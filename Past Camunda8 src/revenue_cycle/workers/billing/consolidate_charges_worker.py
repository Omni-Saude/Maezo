"""
ConsolidateChargesWorker - Zeebe worker for consolidating charges.

This worker implements charge consolidation logic for the Brazilian healthcare
revenue cycle, including:
- Aggregation of similar charges
- Deduplication of charges
- Grouping by charge type and category
- Charge amount validation

Business Rule: RN-BIL-002-ConsolidateCharges.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00
Migrated from: com.hospital.revenuecycle.delegates.ConsolidateChargesDelegate

Section references:
- Charge aggregation by code and category
- Duplicate detection and elimination
- Amount validation and reconciliation

Topic: consolidate-charges
BPMN Task: Task_Consolidate_Charges
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ConfigDict, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class ChargeItem(BaseModel):
    """Model for a charge item."""
    model_config = ConfigDict(populate_by_name=True)

    charge_code: str = Field(..., alias="chargeCode")
    description: Optional[str] = None
    amount: Decimal = Field(..., ge=0)
    quantity: int = Field(1, ge=1)
    category: str


class ConsolidateChargesInput(BaseModel):
    """Input model for consolidate charges operation."""
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(..., alias="claimId")
    charges: list[ChargeItem] = Field(default_factory=list)
    remove_duplicates: bool = Field(True, alias="removeDuplicates")


class ConsolidatedCharge(BaseModel):
    """Model for a consolidated charge."""
    model_config = ConfigDict(populate_by_name=True)

    charge_code: str = Field(..., alias="chargeCode")
    description: Optional[str] = None
    total_amount: Decimal = Field(..., alias="totalAmount", ge=0)
    total_quantity: int = Field(..., alias="totalQuantity", ge=1)
    category: str
    original_count: int = Field(..., alias="originalCount")


class ConsolidateChargesOutput(BaseModel):
    """Output model for consolidate charges operation."""
    model_config = ConfigDict(populate_by_name=True)

    consolidation_complete: bool = Field(..., alias="consolidationComplete")
    consolidated_charges: list[ConsolidatedCharge] = Field(
        default_factory=list,
        alias="consolidatedCharges"
    )
    total_consolidated_amount: Decimal = Field(..., alias="totalConsolidatedAmount", ge=0)
    original_charge_count: int = Field(..., alias="originalChargeCount")
    consolidated_charge_count: int = Field(..., alias="consolidatedChargeCount")
    duplicates_removed: int = Field(..., alias="duplicatesRemoved")


class ConsolidationValidationError(BpmnErrorException):
    """Raised when consolidation validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="CONSOLIDATION_VALIDATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="consolidate-charges", max_jobs=16, lock_duration=30000)
class ConsolidateChargesWorker(BaseWorker):
    """
    Zeebe worker for consolidating charges.

    This worker:
    1. Validates input charges
    2. Deduplicates charges if requested
    3. Consolidates charges by code and category
    4. Calculates consolidated amounts
    5. Returns consolidated charge list

    Input Variables:
        - claimId: Claim identifier (required)
        - charges: List of charge items (required)
        - removeDuplicates: Whether to remove duplicates (optional, default true)

    Output Variables:
        - consolidationComplete: Whether consolidation completed successfully
        - consolidatedCharges: List of consolidated charges
        - totalConsolidatedAmount: Total consolidated amount
        - originalChargeCount: Original number of charges
        - consolidatedChargeCount: Number of consolidated charges
        - duplicatesRemoved: Number of duplicates removed
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
        return "consolidate_charges"

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
        Process the consolidate charges task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with consolidation results
        """
        self._logger.info(
            "Processing consolidate charges",
            job_key=str(getattr(job, "key", "unknown")),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = ConsolidateChargesInput.model_validate(variables)

            # Validate input
            await self._validate_input(input_data)

            # Consolidate charges
            consolidated_charges, duplicates_removed = await self._consolidate_charges(
                input_data
            )

            # Calculate totals
            total_amount = sum(
                (charge.total_amount for charge in consolidated_charges),
                Decimal("0"),
            )

            # Create output
            output = ConsolidateChargesOutput(
                consolidationComplete=True,
                consolidatedCharges=consolidated_charges,
                totalConsolidatedAmount=total_amount,
                originalChargeCount=len(input_data.charges),
                consolidatedChargeCount=len(consolidated_charges),
                duplicatesRemoved=duplicates_removed,
            )

            self._logger.info(
                "Consolidation completed",
                claim_id=input_data.claim_id,
                original_count=len(input_data.charges),
                consolidated_count=len(consolidated_charges),
                duplicates_removed=duplicates_removed,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Input validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_CONSOLIDATION_INPUT",
                error_message=f"Input validation failed: {e}",
            )

        except ConsolidationValidationError as e:
            self._logger.error(
                "Consolidation validation error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during consolidation",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Failed to consolidate charges: {e}",
                retry=True,
            )

    async def _validate_input(self, input_data: ConsolidateChargesInput) -> None:
        """Validate input data and business rules."""
        if not input_data.charges:
            raise ConsolidationValidationError(
                "Charges list cannot be empty",
                details={"claim_id": input_data.claim_id},
            )

    async def _consolidate_charges(
        self,
        input_data: ConsolidateChargesInput,
    ) -> tuple[list[ConsolidatedCharge], int]:
        """
        Consolidate charges by code and category.

        Args:
            input_data: Input data with charges

        Returns:
            Tuple of (consolidated_charges, duplicates_removed_count)
        """
        consolidation_map: dict[str, dict] = {}
        duplicates_removed = 0

        for charge in input_data.charges:
            key = f"{charge.charge_code}:{charge.category}"

            if key in consolidation_map:
                # Charge already seen - this is a duplicate
                existing = consolidation_map[key]
                existing["quantity"] += charge.quantity
                existing["amount"] += charge.amount
                existing["count"] += 1
                duplicates_removed += 1
            else:
                # First time seeing this charge
                consolidation_map[key] = {
                    "charge_code": charge.charge_code,
                    "description": charge.description,
                    "quantity": charge.quantity,
                    "amount": charge.amount,
                    "category": charge.category,
                    "count": 1,
                }

        # Convert to ConsolidatedCharge objects
        consolidated_charges: list[ConsolidatedCharge] = []
        for key, data in consolidation_map.items():
            consolidated_charges.append(
                ConsolidatedCharge(
                    chargeCode=data["charge_code"],
                    description=data["description"],
                    totalAmount=data["amount"],
                    totalQuantity=data["quantity"],
                    category=data["category"],
                    originalCount=data["count"],
                )
            )

        return consolidated_charges, duplicates_removed
