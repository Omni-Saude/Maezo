"""
Care Team Coordination Worker V2

Coordinates care team communication and handoffs.

TOPIC: clinical.care_team_coordination

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/care_team_coordination.

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides

Author: Claude Flow V3 (Manual Refactoring 2026-02-16)
License: MIT
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class CareTeamCoordinationWorker(BaseExternalTaskWorker):
    """
    Care team coordination and communication worker.

    Responsibilities (thin worker pattern):
    1. Parse coordination request variables
    2. Evaluate DMN for communication routing and escalation
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.

    Archetype: CLINICAL_SCORE
    """

    TOPIC = "clinical.care_team_coordination"
    DMN_DECISION_KEY = "care_team_coordination"
    DMN_CATEGORY = "clinical_safety"

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute care team coordination.

        Args:
            context: Task context with input variables

        Returns:
            TaskResult with DMN outputs
        """
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            message_type = variables.get("message_type", "status_update")
            priority = variables.get("priority", "routine")

            self.logger.info(
                "Processing care team coordination: type=%s, priority=%s",
                message_type, priority,
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id, "task_id": context.task_id},
            )

            # Evaluate DMN for coordination logic
            dmn_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DECISION_KEY,
                variables={
                    "messageType": message_type,
                    "priority": priority,
                    "senderRole": variables.get("sender_role", ""),
                    "recipientRole": variables.get("recipient_role", ""),
                },
                category=self.DMN_CATEGORY,
            )

            # Return success with DMN outputs
            return TaskResult.success({
                # DMN routing outputs
                "action": dmn_result.get("action", "SEND"),
                "nivelAlerta": dmn_result.get("nivelAlerta", "OK"),
                "acaoRequerida": dmn_result.get("acaoRequerida", ""),
                "justificativa": dmn_result.get("justificativa", ""),
                # Coordination outputs
                "coordinationStatus": dmn_result.get("coordinationStatus", "pending"),
                "deliveryMethod": dmn_result.get("deliveryMethod", "standard"),
                "escalationRequired": dmn_result.get("escalationRequired", False),
                # Metadata
                "processedAt": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Care team coordination failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_CARE_TEAM_COORDINATION",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
