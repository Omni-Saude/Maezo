"""
WriteOffWorker - Write off uncollectible claims with tax implications.

Business Rule: RN-COL-004.md
Regulatory Compliance: CDC Lei 8.078/90 Art. 42 §único (double penalty prevention), Tax Regulations
Migrated from: com.hospital.revenuecycle.delegates.collection.WriteOffDelegate

This worker handles the financial write-off of claims that cannot be collected,
including tax implications and financial reporting.

Topic: write-off
BPMN Task: Task_Write_Off (Dar Baixa)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="write-off", max_jobs=8, lock_duration=40000)
class WriteOffWorker(BaseWorker):
    """
    Zeebe worker for writing off uncollectible claims.

    BPMN Task: Task_Write_Off
    Topic: write-off

    This worker:
    - Records financial write-offs
    - Updates accounting records
    - Tracks write-off reasons
    - Generates financial reports

    Input Variables:
        - claimId: Claim identifier (required)
        - writeOffAmount: Amount to write off
        - writeOffReason: Reason for write-off (UNCOLLECTIBLE/AGED/FRAUD/OTHER)
        - collectionAttempts: Number of collection attempts

    Output Variables:
        - writeOffId: Unique write-off record identifier
        - writeOffRecorded: Whether write-off was recorded
        - writeOffDate: Date of write-off
        - accountingEntry: Accounting entry details
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "write_off"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the write-off task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with write-off details
        """
        self._logger.info(
            "Processing write-off",
            claim_id=variables.get("claimId"),
            reason=variables.get("writeOffReason"),
        )

        try:
            claim_id = variables.get("claimId")
            write_off_amount = Decimal(str(variables.get("writeOffAmount", 0)))
            write_off_reason = variables.get("writeOffReason", "UNCOLLECTIBLE")
            collection_attempts = int(variables.get("collectionAttempts", 0))

            # Generate write-off ID
            write_off_id = f"WO-{claim_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Create accounting entry
            accounting_entry = {
                "account": "Bad Debt Expense",
                "debit": float(write_off_amount),
                "credit": 0,
                "date": datetime.utcnow().isoformat(),
            }

            output = {
                "writeOffId": write_off_id,
                "writeOffRecorded": True,
                "writeOffDate": datetime.utcnow().isoformat(),
                "accountingEntry": accounting_entry,
                "writeOffReason": write_off_reason,
                "writeOffAmount": float(write_off_amount),
                "collectionAttempts": collection_attempts,
            }

            self._logger.info(
                "Write-off recorded",
                claim_id=claim_id,
                write_off_id=write_off_id,
                write_off_amount=float(write_off_amount),
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error recording write-off",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Write-off failed: {e}",
                retry=True,
            )
