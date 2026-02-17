"""Pre-Surgical Checklist Worker V2 - DMN-based WHO checklist validation.

TOPIC: surgical.checklist | BPMN Error: CLINICAL_OPERATIONS_ERROR
DMN: surgical/who_checklist_validation_001, surgical/critical_items_check_001
ADR: 002, 003, 007, 013 | Refactored 312 -> ~125 LOC
Archetype: COMPLIANCE_VALIDATION
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class PreSurgicalChecklistWorker(BaseExternalTaskWorker):
    """V2 pre-surgical checklist worker (thin worker pattern).

    Responsibilities:
    1. Parse checklist items and phase
    2. Validate WHO critical items via DMN
    3. Determine completion status via DMN
    4. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.checklist"
    DMN_VALIDATION_KEY = "who_checklist_validation_001"
    DMN_CRITICAL_KEY = "critical_items_verification_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute WHO checklist validation with DMN-based compliance checks."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            surgery_id = variables.get("surgery_id", "")
            patient_id = variables.get("patient_id", "")
            phase = variables.get("phase", "sign_in")  # sign_in, time_out, sign_out
            checklist_items = variables.get("checklist_items", [])

            self.logger.info(
                "Processing WHO checklist validation",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "surgery_id": surgery_id, "phase": phase, "items": len(checklist_items)},
            )

            # Count checked items
            items_checked = sum(1 for item in checklist_items if item.get("checked", False))

            # Extract checked item IDs
            checked_item_ids = [item.get("item_id", "") for item in checklist_items if item.get("checked", False)]

            # 1. Validate checklist phase via DMN
            validation_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_VALIDATION_KEY,
                variables={
                    "phase": phase,
                    "itemsTotal": len(checklist_items),
                    "itemsChecked": items_checked,
                    "checkedItemIds": ",".join(checked_item_ids),
                },
                category=self.DMN_CATEGORY,
            )

            # 2. Check critical items via DMN
            critical_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_CRITICAL_KEY,
                variables={
                    "phase": phase,
                    "checkedItemIds": ",".join(checked_item_ids),
                },
                category=self.DMN_CATEGORY,
            )

            all_complete = critical_result.get("allCriticalComplete", False)
            missing_critical = critical_result.get("missingCritical", [])

            # Generate checklist ID
            checklist_id = f"CHK-{surgery_id}-{phase}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            completed_at = datetime.utcnow().isoformat() if all_complete else None

            # Get verifier from first checked item
            verified_by = next(
                (item.get("checked_by") for item in checklist_items if item.get("checked_by")),
                None,
            )

            return TaskResult.success({
                "checklist_id": checklist_id,
                "surgery_id": surgery_id,
                "patient_id": patient_id,
                "phase": phase,
                "items_total": len(checklist_items),
                "items_checked": items_checked,
                "all_complete": all_complete,
                "completed_at": completed_at,
                "verified_by": verified_by,
                "missing_critical": missing_critical,
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"WHO checklist validation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="CLINICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
