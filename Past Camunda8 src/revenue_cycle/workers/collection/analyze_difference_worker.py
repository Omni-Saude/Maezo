"""
AnalyzeDifferenceWorker - Analyze payment discrepancies and resolution paths.

Business Rule: RN-COL-005.md
Regulatory Compliance: CDC Lei 8.078/90 Art. 42 (overpayment/underpayment handling), Benchmark: CDC Collection Compliance
Migrated from: com.hospital.revenuecycle.delegates.collection.AnalyzeDifferenceDelegate

This worker analyzes discrepancies between expected payment amounts and actual
received amounts, determining causes and resolution paths.

Topic: analyze-difference
BPMN Task: Task_Analyze_Difference (Analisar Diferenca)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="analyze-difference", max_jobs=8, lock_duration=30000)
class AnalyzeDifferenceWorker(BaseWorker):
    """
    Zeebe worker for analyzing payment differences.

    BPMN Task: Task_Analyze_Difference
    Topic: analyze-difference

    This worker analyzes:
    - Partial payments
    - Overpayments
    - Underpayments
    - Missing payments

    Input Variables:
        - claimId: Claim identifier (required)
        - expectedAmount: Expected payment amount
        - receivedAmount: Actually received amount

    Output Variables:
        - differenceId: Unique difference record identifier
        - differenceAmount: Difference amount (positive=underpaid, negative=overpaid)
        - differenceReason: Identified reason for difference
        - resolutionPath: Recommended resolution path
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "analyze_difference"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the payment difference analysis task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with difference analysis
        """
        self._logger.info(
            "Processing payment difference analysis",
            claim_id=variables.get("claimId"),
        )

        try:
            claim_id = variables.get("claimId")
            expected_amount = Decimal(str(variables.get("expectedAmount", 0)))
            received_amount = Decimal(str(variables.get("receivedAmount", 0)))

            # Calculate difference
            difference_amount = expected_amount - received_amount

            # Determine difference reason and resolution
            if difference_amount > 0:
                # Underpayment
                difference_reason = "UNDERPAYMENT"
                resolution_path = "COLLECT_REMAINING" if difference_amount > Decimal("100") else "WRITE_OFF"
            elif difference_amount < 0:
                # Overpayment
                difference_reason = "OVERPAYMENT"
                resolution_path = "CREDIT_PATIENT" if abs(difference_amount) > Decimal("100") else "RETAIN"
            else:
                # Exact payment
                difference_reason = "EXACT_MATCH"
                resolution_path = "CLOSE_CLAIM"

            # Generate difference ID
            difference_id = f"DIFF-{claim_id}"

            output = {
                "differenceId": difference_id,
                "differenceAmount": float(difference_amount),
                "differenceReason": difference_reason,
                "resolutionPath": resolution_path,
                "expectedAmount": float(expected_amount),
                "receivedAmount": float(received_amount),
                "differencePercentage": (
                    round((float(abs(difference_amount)) / float(expected_amount)) * 100, 2)
                    if expected_amount > 0 else 0
                ),
            }

            self._logger.info(
                "Payment difference analyzed",
                claim_id=claim_id,
                difference_amount=float(difference_amount),
                difference_reason=difference_reason,
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error analyzing payment difference",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Difference analysis failed: {e}",
                retry=True,
            )
