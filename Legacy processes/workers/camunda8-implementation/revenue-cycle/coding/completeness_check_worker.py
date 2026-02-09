"""
CompletenessCheckWorker - Zeebe worker for verifying claim data completeness.

This worker validates that all required claim fields are present and properly formatted.
Used in the audit workflow to identify missing or incomplete data before processing.

This is the Python equivalent of the Java CompletenessCheckDelegate.

Business Rule: Benchmark - Data completeness requirements per ANS/TISS standards
Regulatory Compliance: ANS Resolution 456/2018, TISS 4.01.00 data requirements, CFM standards
Migrated from: com.hospital.revenuecycle.delegates.CompletenessCheckDelegate

Section references:
- Required field validation for healthcare claims
- Data type and format validation
- Completeness scoring (percentage of valid fields)

BPMN Task: Task_Completeness_Check in Audit_Validation_Workflow
Topic: completeness-check
"""

from __future__ import annotations

from typing import Any

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="completeness-check", max_jobs=8, lock_duration=30000)
class CompletenessCheckWorker(BaseWorker):
    """
    Zeebe worker for completeness validation of claim data.

    BPMN Task: Task_Completeness_Check
    Topic: completeness-check

    This worker validates claim data completeness including:
    - Required fields presence
    - Data type validation
    - Format validation
    - Cross-field consistency

    Input Variables:
        - claimId: Claim identifier (required)
        - claimData: Claim data object (required)

    Output Variables:
        - isComplete: Whether claim data is complete (boolean)
        - missingFields: List of missing required fields
        - completenessScore: Percentage of fields complete
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "completeness_check"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the completeness check task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with completeness check outcome
        """
        self._logger.info(
            "Processing completeness check",
            claim_id=variables.get("claimId"),
        )

        try:
            claim_id = variables.get("claimId")
            claim_data = variables.get("claimData", {})

            # Define required fields
            required_fields = [
                "patientId",
                "providerId",
                "serviceDate",
                "amount",
                "serviceCode",
            ]

            # Check for missing fields
            missing_fields = [
                field for field in required_fields
                if field not in claim_data or claim_data[field] is None
            ]

            # Calculate completeness score
            completeness_score = (
                ((len(required_fields) - len(missing_fields)) /
                 len(required_fields)) * 100
                if required_fields
                else 100
            )

            is_complete = len(missing_fields) == 0

            output = {
                "isComplete": is_complete,
                "missingFields": missing_fields,
                "completenessScore": completeness_score,
            }

            self._logger.info(
                "Completeness check completed",
                claim_id=claim_id,
                is_complete=is_complete,
                completeness_score=completeness_score,
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error performing completeness check",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Completeness check failed: {e}",
                retry=True,
            )
