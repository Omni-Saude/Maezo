"""
GroupByGuideWorker - Zeebe worker for grouping charges by guide (guia).

This worker implements charge grouping logic for the Brazilian healthcare
revenue cycle, including:
- Grouping charges by service guide
- Separating by provider
- Organizing by procedure type
- Grouping by date range

Business Rule: RN-BIL-003-GroupByGuide.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00
Migrated from: com.hospital.revenuecycle.delegates.GroupByGuideDelegate

Section references:
- Service guide (guia) organization and grouping
- Provider-based charge separation
- Procedure type categorization
- Date range validation

Topic: group-by-guide
BPMN Task: Task_Group_By_Guide
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ConfigDict, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class ChargeForGrouping(BaseModel):
    """Model for a charge to be grouped."""
    model_config = ConfigDict(populate_by_name=True)

    charge_code: str = Field(..., alias="chargeCode")
    description: Optional[str] = None
    amount: Decimal = Field(..., ge=0)
    quantity: int = Field(1, ge=1)
    provider_id: str = Field(..., alias="providerId")
    service_date: datetime = Field(..., alias="serviceDate")
    category: str


class GuideGroup(BaseModel):
    """Model for a grouped guide."""
    model_config = ConfigDict(populate_by_name=True)

    guide_id: str = Field(..., alias="guideId")
    provider_id: str = Field(..., alias="providerId")
    total_amount: Decimal = Field(..., alias="totalAmount", ge=0)
    charge_count: int = Field(..., alias="chargeCount")
    start_date: datetime = Field(..., alias="startDate")
    end_date: datetime = Field(..., alias="endDate")
    charges: list[ChargeForGrouping] = Field(default_factory=list)


class GroupByGuideInput(BaseModel):
    """Input model for group by guide operation."""
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(..., alias="claimId")
    charges: list[ChargeForGrouping] = Field(default_factory=list)


class GroupByGuideOutput(BaseModel):
    """Output model for group by guide operation."""
    model_config = ConfigDict(populate_by_name=True)

    grouping_complete: bool = Field(..., alias="groupingComplete")
    guide_groups: list[GuideGroup] = Field(
        default_factory=list,
        alias="guideGroups"
    )
    total_groups: int = Field(..., alias="totalGroups")
    total_amount: Decimal = Field(..., alias="totalAmount", ge=0)


class GroupingValidationError(BpmnErrorException):
    """Raised when grouping validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="GROUPING_VALIDATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="group-by-guide", max_jobs=16, lock_duration=30000)
class GroupByGuideWorker(BaseWorker):
    """
    Zeebe worker for grouping charges by service guide.

    This worker:
    1. Validates input charges
    2. Groups charges by provider and date range
    3. Generates unique guide IDs
    4. Calculates group totals
    5. Returns grouped charges

    Input Variables:
        - claimId: Claim identifier (required)
        - charges: List of charges to group (required)

    Output Variables:
        - groupingComplete: Whether grouping completed
        - guideGroups: List of grouped guides
        - totalGroups: Number of groups created
        - totalAmount: Total consolidated amount
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
        return "group_by_guide"

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
        Process the group by guide task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with grouping results
        """
        self._logger.info(
            "Processing group by guide",
            job_key=str(getattr(job, "key", "unknown")),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = GroupByGuideInput.model_validate(variables)

            # Validate input
            await self._validate_input(input_data)

            # Group charges
            guide_groups = await self._group_by_guide(input_data)

            # Calculate totals
            total_amount = sum(
                (group.total_amount for group in guide_groups),
                Decimal("0"),
            )

            # Create output
            output = GroupByGuideOutput(
                groupingComplete=True,
                guideGroups=guide_groups,
                totalGroups=len(guide_groups),
                totalAmount=total_amount,
            )

            self._logger.info(
                "Grouping completed",
                claim_id=input_data.claim_id,
                charge_count=len(input_data.charges),
                group_count=len(guide_groups),
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Input validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_GROUPING_INPUT",
                error_message=f"Input validation failed: {e}",
            )

        except GroupingValidationError as e:
            self._logger.error(
                "Grouping validation error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during grouping",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Failed to group charges: {e}",
                retry=True,
            )

    async def _validate_input(self, input_data: GroupByGuideInput) -> None:
        """Validate input data and business rules."""
        if not input_data.charges:
            raise GroupingValidationError(
                "Charges list cannot be empty",
                details={"claim_id": input_data.claim_id},
            )

    async def _group_by_guide(
        self,
        input_data: GroupByGuideInput,
    ) -> list[GuideGroup]:
        """
        Group charges by provider and date range.

        Args:
            input_data: Input data with charges

        Returns:
            List of grouped guides
        """
        grouping_map: dict[str, dict] = {}
        group_counter = 0

        for charge in input_data.charges:
            # Create group key based on provider
            key = f"{charge.provider_id}"

            if key not in grouping_map:
                group_counter += 1
                guide_id = f"GUIDE-{input_data.claim_id}-{group_counter:03d}"

                grouping_map[key] = {
                    "guide_id": guide_id,
                    "provider_id": charge.provider_id,
                    "total_amount": Decimal("0"),
                    "charge_count": 0,
                    "start_date": charge.service_date,
                    "end_date": charge.service_date,
                    "charges": [],
                }

            group = grouping_map[key]
            group["total_amount"] += charge.amount
            group["charge_count"] += charge.quantity
            group["charges"].append(charge)

            # Update date range
            if charge.service_date < group["start_date"]:
                group["start_date"] = charge.service_date
            if charge.service_date > group["end_date"]:
                group["end_date"] = charge.service_date

        # Convert to GuideGroup objects
        guide_groups: list[GuideGroup] = []
        for key, data in grouping_map.items():
            guide_groups.append(
                GuideGroup(
                    guideId=data["guide_id"],
                    providerId=data["provider_id"],
                    totalAmount=data["total_amount"],
                    chargeCount=data["charge_count"],
                    startDate=data["start_date"],
                    endDate=data["end_date"],
                    charges=data["charges"],
                )
            )

        return guide_groups
