"""Surgical Materials Worker V2 - DMN-based materials reservation.

TOPIC: surgical.materials | BPMN Error: CLINICAL_OPERATIONS_ERROR
DMN: surgical/material_availability_001, surgical/material_priority_001
ADR: 002, 003, 007, 013 | Refactored 272 -> ~120 LOC
Archetype: OPERATIONAL_ROUTING
"""

from __future__ import annotations

from datetime import datetime

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class SurgicalMaterialsWorker(BaseExternalTaskWorker):
    """V2 surgical materials worker (thin worker pattern).

    Responsibilities:
    1. Parse materials request
    2. Check availability via DMN
    3. Evaluate priority via DMN
    4. Reserve materials
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.materials"
    DMN_AVAILABILITY_KEY = "material_availability_check_001"
    DMN_PRIORITY_KEY = "material_request_priority_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute materials reservation with DMN-based availability checks."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            surgery_id = variables.get("surgery_id", "")
            procedure_code = variables.get("procedure_code", "")
            materials = variables.get("materials", [])
            priority = variables.get("priority", "routine")  # routine, urgent, stat

            self.logger.info(
                "Processing materials reservation",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "surgery_id": surgery_id, "materials_count": len(materials)},
            )

            materials_reserved = []
            all_available = True

            for material in materials:
                material_code = material.get("material_code", "")
                quantity = material.get("quantity", 1)

                # Check availability via DMN
                availability_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_AVAILABILITY_KEY,
                    variables={
                        "materialCode": material_code,
                        "requestedQuantity": quantity,
                        "priority": priority,
                    },
                    category=self.DMN_CATEGORY,
                )

                available = availability_result.get("available", False)

                materials_reserved.append({
                    "material_code": material_code,
                    "quantity": quantity,
                    "available": available,
                })

                if not available:
                    all_available = False

            # Generate request ID
            request_id = f"MAT-{surgery_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            return TaskResult.success({
                "request_id": request_id,
                "surgery_id": surgery_id,
                "procedure_code": procedure_code,
                "materials_reserved": materials_reserved,
                "all_available": all_available,
                "reserved_at": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Materials reservation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="CLINICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
