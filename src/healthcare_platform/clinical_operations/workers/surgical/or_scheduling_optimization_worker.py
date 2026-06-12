"""OR Scheduling Optimization Worker V2 - DMN-based utilization optimization.

TOPIC: surgical.or_optimization | BPMN Error: SURGICAL_OPERATIONS_ERROR
DMN: surgical/or_utilization_001, surgical/procedure_priority_001, surgical/or_capacity_001
ADR: 002, 003, 007, 013 | Refactored 368 -> ~140 LOC
Archetype: OPERATIONAL_ROUTING
"""

from __future__ import annotations

from datetime import datetime

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class ORSchedulingOptimizationWorker(BaseExternalTaskWorker):
    """V2 OR scheduling optimization worker (thin worker pattern).

    Responsibilities:
    1. Parse OR scheduling parameters
    2. Evaluate DMN for procedure prioritization
    3. Determine OR capacity via DMN
    4. Calculate utilization metrics via DMN
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.or_optimization"
    DMN_PRIORITY_KEY = "procedure_priority_001"
    DMN_CAPACITY_KEY = "or_capacity_calculation_001"
    DMN_UTILIZATION_KEY = "or_utilization_metrics_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute OR scheduling optimization with DMN-based routing."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            operating_room_id = variables.get("operating_room_id", "")
            date = variables.get("date", "")
            available_minutes = variables.get("available_minutes", 480)  # 8 hours default
            procedures = variables.get("procedures", [])
            turnover_time_minutes = variables.get("turnover_time_minutes", 30)

            self.logger.info(
                "Processing OR scheduling optimization",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "or_id": operating_room_id, "procedure_count": len(procedures)},
            )

            scheduled_slots = []
            unscheduled = []
            used_minutes = 0

            # 1. Prioritize procedures via DMN
            for procedure in procedures:
                priority_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_PRIORITY_KEY,
                    variables={
                        "procedureType": procedure.get("procedure_code", ""),
                        "priority": procedure.get("priority", "elective"),
                        "estimatedDuration": procedure.get("estimated_duration_minutes", 60),
                    },
                    category=self.DMN_CATEGORY,
                )
                procedure["priority_score"] = priority_result.get("priorityScore", 0)

            # Sort by priority score (descending)
            procedures.sort(key=lambda p: p.get("priority_score", 0), reverse=True)

            # 2. Check capacity for each procedure via DMN
            for procedure in procedures:
                duration = procedure.get("estimated_duration_minutes", 60)
                capacity_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_CAPACITY_KEY,
                    variables={
                        "usedMinutes": used_minutes,
                        "availableMinutes": available_minutes,
                        "procedureDuration": duration,
                        "turnoverTime": turnover_time_minutes,
                    },
                    category=self.DMN_CATEGORY,
                )

                if capacity_result.get("canSchedule", False):
                    # Schedule the procedure
                    scheduled_slots.append({
                        "procedure_id": procedure.get("procedure_id", ""),
                        "procedure_code": procedure.get("procedure_code", ""),
                        "duration_minutes": duration,
                        "priority": procedure.get("priority", "elective"),
                        "turnover_after": turnover_time_minutes,
                    })
                    used_minutes += duration + turnover_time_minutes
                else:
                    unscheduled.append(procedure.get("procedure_id", ""))

            # 3. Calculate utilization metrics via DMN
            utilization_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_UTILIZATION_KEY,
                variables={
                    "totalMinutes": available_minutes,
                    "usedMinutes": used_minutes,
                    "scheduledCount": len(scheduled_slots),
                    "unscheduledCount": len(unscheduled),
                },
                category=self.DMN_CATEGORY,
            )

            utilization_percentage = utilization_result.get("utilizationPercentage", 0.0)
            idle_minutes = available_minutes - used_minutes

            return TaskResult.success({
                "optimization_id": f"OPT-{operating_room_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "operating_room_id": operating_room_id,
                "date": date,
                "scheduled_slots": scheduled_slots,
                "utilization_percentage": round(utilization_percentage, 2),
                "unscheduled_procedures": unscheduled,
                "total_or_minutes": available_minutes,
                "idle_minutes": idle_minutes,
                "optimization_timestamp": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"OR scheduling optimization failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="SURGICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
