"""Manual authorization review by billing team.

TOPIC: revenue_cycle.manual-review

Handles cases where authorization was denied or requires audit.
In production, creates a task in the billing team's queue.
"""
from __future__ import annotations
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class ManualReviewWorker(BaseExternalTaskWorker):
    """Processes manual review of denied/audited authorizations."""

    TOPIC = "revenue_cycle.manual-review"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        auth_number = variables.get("authorizationNumber", "")
        auth_status = variables.get("authorizationStatus", "")
        payer_id = variables.get("payerId", "")

        self.logger.info(
            f"Manual review: auth={auth_number}, status={auth_status}, payer={payer_id}",
            extra={"tenant_id": context.tenant_id},
        )

        # Stub: log and complete
        # In production: create task in billing queue, notify team
        return TaskResult.success({
            "reviewCompleted": True,
            "reviewOutcome": "MANUAL_REVIEW_DONE",
            "reviewNotes": f"Revisao manual concluida para auth {auth_number}",
        })
