"""
AgingAnalysisWorker - Zeebe worker for accounts receivable aging analysis.

This worker implements aging analysis logic for the Brazilian healthcare
revenue cycle, including:
- Calculation of receivable aging
- Classification by age bucket
- Aging trend analysis
- Collection priority assessment

Business Rule: HFMA Days in AR Analysis & Collections Management
Industry Standard: Revenue Cycle Management Best Practices (HFMA, MGMA)
KPI Reference:
  - Days in AR Target: <45 days (industry benchmark)
  - <30 Day AR: 40%+ of total receivables
  - 31-60 Day AR: 35%+ of total receivables
  - 60+ Day AR: <25% of total receivables
  - Collection Priority Accuracy: 98%+
  - Aging Trend Analysis: Monthly trending

Migrated from Java AgingAnalysisDelegate.

Topic: aging-analysis
BPMN Task: Task_Aging_Analysis
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ConfigDict, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class ReceivableItem(BaseModel):
    """Model for a receivable item."""
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(..., alias="claimId")
    amount: Decimal = Field(..., ge=0)
    service_date: datetime = Field(..., alias="serviceDate")
    bill_date: datetime = Field(..., alias="billDate")


class AgingBucket(BaseModel):
    """Model for an aging bucket."""
    model_config = ConfigDict(populate_by_name=True)

    bucket_name: str = Field(..., alias="bucketName")
    min_days: int = Field(..., alias="minDays")
    max_days: int = Field(..., alias="maxDays")
    item_count: int = Field(..., alias="itemCount")
    total_amount: Decimal = Field(..., alias="totalAmount", ge=0)
    percentage_of_total: Decimal = Field(..., alias="percentageOfTotal")


class AgingAnalysisInput(BaseModel):
    """Input model for aging analysis operation."""
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(..., alias="claimId")
    receivables: list[ReceivableItem] = Field(default_factory=list)
    analysis_date: datetime = Field(..., alias="analysisDate")


class AgingAnalysisOutput(BaseModel):
    """Output model for aging analysis operation."""
    model_config = ConfigDict(populate_by_name=True)

    analysis_complete: bool = Field(..., alias="analysisComplete")
    analysis_date: datetime = Field(..., alias="analysisDate")
    aging_buckets: list[AgingBucket] = Field(
        default_factory=list,
        alias="agingBuckets"
    )
    total_receivables: Decimal = Field(..., alias="totalReceivables", ge=0)
    average_age_days: int = Field(..., alias="averageAgeDays")
    high_priority_amount: Decimal = Field(..., alias="highPriorityAmount", ge=0)


class AgingAnalysisError(BpmnErrorException):
    """Raised when aging analysis fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="AGING_ANALYSIS_ERROR",
            message=message,
            details=details,
        )


@worker(topic="aging-analysis", max_jobs=8, lock_duration=60000)
class AgingAnalysisWorker(BaseWorker):
    """
    Zeebe worker for accounts receivable aging analysis.

    This worker:
    1. Validates input receivables
    2. Calculates age of each receivable
    3. Groups into age buckets (0-30, 31-60, 61-90, 90+)
    4. Calculates aging statistics
    5. Identifies high-priority items for collection

    Input Variables:
        - claimId: Claim identifier (required)
        - receivables: List of receivable items (required)
        - analysisDate: Date for aging calculation (required)

    Output Variables:
        - analysisComplete: Whether analysis completed
        - analysisDate: Date used for analysis
        - agingBuckets: List of aging buckets with amounts
        - totalReceivables: Total receivable amount
        - averageAgeDays: Average age in days
        - highPriorityAmount: Amount over 60 days old
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
        return "aging_analysis"

    @property
    def requires_idempotency(self) -> bool:
        """This worker benefits from idempotency."""
        return False

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the aging analysis task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with aging analysis results
        """
        self._logger.info(
            "Processing aging analysis",
            job_key=str(getattr(job, "key", "unknown")),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = AgingAnalysisInput.model_validate(variables)

            # Validate input
            await self._validate_input(input_data)

            # Perform aging analysis
            aging_buckets, total_amount = await self._perform_aging_analysis(input_data)

            # Calculate statistics
            avg_age, high_priority_amount = self._calculate_statistics(
                input_data.receivables,
                input_data.analysis_date,
            )

            # Create output
            output = AgingAnalysisOutput(
                analysisComplete=True,
                analysisDate=input_data.analysis_date,
                agingBuckets=aging_buckets,
                totalReceivables=total_amount,
                averageAgeDays=avg_age,
                highPriorityAmount=high_priority_amount,
            )

            self._logger.info(
                "Aging analysis completed",
                claim_id=input_data.claim_id,
                total_receivables=str(total_amount),
                average_age_days=avg_age,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Input validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_AGING_INPUT",
                error_message=f"Input validation failed: {e}",
            )

        except AgingAnalysisError as e:
            self._logger.error(
                "Aging analysis error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during aging analysis",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Failed to perform aging analysis: {e}",
                retry=True,
            )

    async def _validate_input(self, input_data: AgingAnalysisInput) -> None:
        """Validate input data and business rules."""
        if not input_data.receivables:
            raise AgingAnalysisError(
                "Receivables list cannot be empty",
                details={"claim_id": input_data.claim_id},
            )

    async def _perform_aging_analysis(
        self,
        input_data: AgingAnalysisInput,
    ) -> tuple[list[AgingBucket], Decimal]:
        """
        Perform aging analysis on receivables.

        Args:
            input_data: Input data with receivables

        Returns:
            Tuple of (aging_buckets, total_amount)
        """
        # Define aging buckets
        buckets_config = [
            ("0-30 days", 0, 30),
            ("31-60 days", 31, 60),
            ("61-90 days", 61, 90),
            ("90+ days", 91, 999999),
        ]

        # Initialize bucket counters
        bucket_data: dict[str, dict] = {}
        for bucket_name, min_days, max_days in buckets_config:
            bucket_data[bucket_name] = {
                "min_days": min_days,
                "max_days": max_days,
                "item_count": 0,
                "total_amount": Decimal("0"),
            }

        total_amount = Decimal("0")

        # Classify each receivable
        for receivable in input_data.receivables:
            days_old = (input_data.analysis_date - receivable.bill_date).days

            # Find appropriate bucket
            for bucket_name, min_days, max_days in buckets_config:
                if min_days <= days_old <= max_days:
                    bucket_data[bucket_name]["item_count"] += 1
                    bucket_data[bucket_name]["total_amount"] += receivable.amount
                    total_amount += receivable.amount
                    break

        # Convert to AgingBucket objects
        aging_buckets: list[AgingBucket] = []
        for bucket_name, min_days, max_days in buckets_config:
            data = bucket_data[bucket_name]
            pct = Decimal("0")
            if total_amount > 0:
                pct = (data["total_amount"] / total_amount) * Decimal("100")

            aging_buckets.append(
                AgingBucket(
                    bucketName=bucket_name,
                    minDays=min_days,
                    maxDays=max_days,
                    itemCount=data["item_count"],
                    totalAmount=data["total_amount"],
                    percentageOfTotal=pct,
                )
            )

        return aging_buckets, total_amount

    def _calculate_statistics(
        self,
        receivables: list[ReceivableItem],
        analysis_date: datetime,
    ) -> tuple[int, Decimal]:
        """
        Calculate aging statistics.

        Args:
            receivables: List of receivables
            analysis_date: Date for analysis

        Returns:
            Tuple of (average_age_days, high_priority_amount)
        """
        if not receivables:
            return 0, Decimal("0")

        total_days = 0
        high_priority_amount = Decimal("0")

        for receivable in receivables:
            days_old = (analysis_date - receivable.bill_date).days
            total_days += days_old

            # High priority = over 60 days old
            if days_old > 60:
                high_priority_amount += receivable.amount

        average_age = total_days // len(receivables) if receivables else 0

        return average_age, high_priority_amount
