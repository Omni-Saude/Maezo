"""OR Turnover Worker V2 - DMN-based turnover management.

TOPIC: surgical.or_turnover | BPMN Error: CLINICAL_OPERATIONS_ERROR
DMN: surgical/turnover_duration_001, surgical/turnover_priority_001
ADR: 002, 003, 007, 013 | Refactored 252 -> ~115 LOC
Archetype: OPERATIONAL_ROUTING
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class ORTurnoverWorker(BaseExternalTaskWorker):
    """V2 OR turnover worker (thin worker pattern).

    Responsibilities:
    1. Parse turnover request
    2. Determine duration via DMN
    3. Evaluate priority via DMN
    4. Initiate turnover tracking
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.or_turnover"
    DMN_DURATION_KEY = "turnover_duration_estimation_001"
    DMN_PRIORITY_KEY = "turnover_priority_determination_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute OR turnover with DMN-based duration estimation."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            operating_room_id = variables.get("operating_room_id", "")
            previous_surgery_id = variables.get("previous_surgery_id", "")
            next_surgery_id = variables.get("next_surgery_id", "")
            turnover_type = variables.get("turnover_type", "standard")  # standard, deep_clean, terminal

            self.logger.info(
                "Processing OR turnover",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "or_id": operating_room_id, "turnover_type": turnover_type},
            )

            # 1. Determine duration via DMN
            duration_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DURATION_KEY,
                variables={
                    "turnoverType": turnover_type,
                    "hasNextSurgery": bool(next_surgery_id),
                },
                category=self.DMN_CATEGORY,
            )

            estimated_minutes = duration_result.get("estimatedMinutes", 20)

            # 2. Evaluate priority via DMN
            priority_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_PRIORITY_KEY,
                variables={
                    "turnoverType": turnover_type,
                    "hasNextSurgery": bool(next_surgery_id),
                },
                category=self.DMN_CATEGORY,
            )

            priority_level = priority_result.get("priority", "normal")

            # Calculate estimated completion
            started_at = datetime.utcnow()
            estimated_completion = started_at + timedelta(minutes=estimated_minutes)

            # Generate turnover ID
            turnover_id = f"TURN-{operating_room_id}-{started_at.strftime('%Y%m%d%H%M%S')}"

            return TaskResult.success({
                "turnover_id": turnover_id,
                "operating_room_id": operating_room_id,
                "previous_surgery_id": previous_surgery_id,
                "next_surgery_id": next_surgery_id or "",
                "turnover_type": turnover_type,
                "status": "cleaning",
                "priority": priority_level,
                "estimated_minutes": estimated_minutes,
                "estimated_completion": estimated_completion.isoformat(),
                "started_at": started_at.isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"OR turnover failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="CLINICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
