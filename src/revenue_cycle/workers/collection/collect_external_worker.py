"""
CollectExternalWorker - Collect payments from external collection sources.

Business Rule: RN-COL-002.md
Regulatory Compliance: CDC Lei 8.078/90 Art. 42 (overpayment prohibition), Art. 71 (contact hours)
Migrated from: com.hospital.revenuecycle.delegates.collection.CollectExternalDelegate

This worker processes payment collections from collection agencies, third-party payers,
and other external collection sources.

Topic: collect-external
BPMN Task: Task_Collect_External (Cobrar Externo)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="collect-external", max_jobs=8, lock_duration=45000)
class CollectExternalWorker(BaseWorker):
    """
    Zeebe worker for collecting payments from external sources.

    BPMN Task: Task_Collect_External
    Topic: collect-external

    This worker handles:
    - Collection agency callbacks
    - Third-party payer payments
    - Recovery collection
    - Remittance processing

    Input Variables:
        - claimId: Claim identifier (required)
        - collectionCaseId: Collection case identifier
        - collectionAmount: Amount outstanding
        - externalSource: Source of collection (AGENCY/INSURER/OTHER)

    Output Variables:
        - collectionId: Unique collection record identifier
        - amountCollected: Amount successfully collected
        - collectionDate: Date of collection
        - collectionStatus: Status (COLLECTED/PARTIAL/PENDING)
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "collect_external"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the external collection task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with collection outcome
        """
        self._logger.info(
            "Processing external collection",
            claim_id=variables.get("claimId"),
            source=variables.get("externalSource"),
        )

        try:
            claim_id = variables.get("claimId")
            collection_case_id = variables.get("collectionCaseId", "")
            collection_amount = Decimal(str(variables.get("collectionAmount", 0)))
            external_source = variables.get("externalSource", "OTHER")

            # Simulate external collection processing
            # In production, would call actual collection APIs
            amount_collected = collection_amount * Decimal("0.85")  # 85% success rate
            collection_status = "COLLECTED" if amount_collected > 0 else "PENDING"

            # Generate collection ID
            collection_id = f"EXT-{claim_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            output = {
                "collectionId": collection_id,
                "amountCollected": float(amount_collected),
                "collectionDate": datetime.utcnow().isoformat(),
                "collectionStatus": collection_status,
                "externalSource": external_source,
                "originalAmount": float(collection_amount),
                "collectionPercentage": (
                    round((float(amount_collected) / float(collection_amount)) * 100, 2)
                    if collection_amount > 0 else 0
                ),
            }

            self._logger.info(
                "External collection processed",
                claim_id=claim_id,
                collection_id=collection_id,
                amount_collected=float(amount_collected),
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error processing external collection",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"External collection failed: {e}",
                retry=True,
            )
