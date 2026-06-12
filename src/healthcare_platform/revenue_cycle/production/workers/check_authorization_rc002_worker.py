"""Check authorization requirement for RC-002 Pre-Service.

TOPIC: revenue_cycle.check_authorization

Stub worker: returns default authorization requirement flags.
In production, this will query the payer's authorization rules.
"""
from __future__ import annotations
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class CheckAuthorizationRC002Worker(BaseExternalTaskWorker):
    """Determines if prior authorization is required for the procedure."""

    TOPIC = "revenue_cycle.check_authorization"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        procedure_code = variables.get("procedureCode", "")
        payer_id = variables.get("payerId", "")

        self.logger.info(
            f"Checking auth requirement: procedure={procedure_code}, payer={payer_id}",
            extra={"tenant_id": context.tenant_id},
        )

        # BPMN outputParameter names: ${requiresAuth}, ${authType}
        return TaskResult.success({
            "requiresAuth": True,
            "authType": "PRIOR_AUTHORIZATION",
        })
