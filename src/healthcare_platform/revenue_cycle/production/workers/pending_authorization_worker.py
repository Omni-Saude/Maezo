"""Check pending authorization status from payer portal.

TOPIC: revenue_cycle.pending-authorization

Queries the payer's authorization system to get current status.
In production, integrates with payer APIs or RPA results.
"""
from __future__ import annotations
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class PendingAuthorizationWorker(BaseExternalTaskWorker):
    """Checks authorization status after RPA/portal interaction."""

    TOPIC = "revenue_cycle.pending-authorization"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        auth_number = variables.get("authorizationNumber", "")
        payer_id = variables.get("payerId", "")

        self.logger.info(
            f"Checking authorization status: auth={auth_number}, payer={payer_id}",
            extra={"tenant_id": context.tenant_id},
        )

        # Stub: assume APPROVED for dev/test
        # In production: query payer API with auth_number
        return TaskResult.success({
            "authorizationStatus": "APPROVED",
            "authorizationNumber": auth_number,
            "authorizationDetails": f"Autorizado pela operadora {payer_id}",
        })
