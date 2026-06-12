"""Surgery Scheduling Worker V2 - DMN-based surgery scheduling.

TOPIC: surgical.scheduling | BPMN Error: CLINICAL_OPERATIONS_ERROR
DMN: surgical/or_availability_001, surgical/scheduling_priority_001
ADR: 002, 003, 007, 013 | Refactored 237 -> ~120 LOC
Archetype: OPERATIONAL_ROUTING
"""

from __future__ import annotations

from datetime import datetime

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class SurgerySchedulingWorker(BaseExternalTaskWorker):
    """V2 surgery scheduling worker (thin worker pattern).

    Responsibilities:
    1. Parse scheduling request
    2. Check OR availability via DMN
    3. Evaluate scheduling priority via DMN
    4. Assign OR and create schedule
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.scheduling"
    DMN_AVAILABILITY_KEY = "or_availability_check_001"
    DMN_PRIORITY_KEY = "scheduling_priority_determination_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute surgery scheduling with DMN-based OR assignment."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            patient_id = variables.get("patient_id", "")
            surgeon_id = variables.get("surgeon_id", "")
            procedure_code = variables.get("procedure_code", "")
            procedure_name = variables.get("procedure_name", "")
            preferred_date = variables.get("preferred_date", "")
            preferred_time = variables.get("preferred_time", "")
            estimated_duration_minutes = variables.get("estimated_duration_minutes", 60)
            urgency_level = variables.get("urgency_level", "elective")  # elective, urgent, emergency

            self.logger.info(
                "Processing surgery scheduling",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "patient_id": patient_id, "urgency": urgency_level},
            )

            # 1. Check OR availability via DMN
            availability_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_AVAILABILITY_KEY,
                variables={
                    "preferredDate": preferred_date,
                    "preferredTime": preferred_time,
                    "estimatedDuration": estimated_duration_minutes,
                    "urgencyLevel": urgency_level,
                },
                category=self.DMN_CATEGORY,
            )

            # TODO: or_available sera usado na validacao de disponibilidade da sala cirurgica
            # or_available = availability_result.get("available", False)
            assigned_or = availability_result.get("assignedOR", "OR-1")

            # 2. Evaluate priority via DMN
            priority_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_PRIORITY_KEY,
                variables={
                    "urgencyLevel": urgency_level,
                    "procedureCode": procedure_code,
                },
                category=self.DMN_CATEGORY,
            )

            scheduling_status = "scheduled" if urgency_level != "emergency" else "confirmed"

            # Generate surgery ID
            surgery_id = f"SURG-{patient_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            return TaskResult.success({
                "surgery_id": surgery_id,
                "patient_id": patient_id,
                "surgeon_id": surgeon_id,
                "procedure_code": procedure_code,
                "procedure_name": procedure_name,
                "scheduled_date": preferred_date,
                "scheduled_time": preferred_time,
                "operating_room": assigned_or,
                "status": scheduling_status,
                "urgency_level": urgency_level,
                "estimated_duration_minutes": estimated_duration_minutes,
                "priority_score": priority_result.get("priorityScore", 0),
                "created_at": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Surgery scheduling failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="CLINICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
