"""Surgical Count Verification Worker V2 - DMN-based count compliance.

TOPIC: surgical.count_verification | BPMN Error: SURGICAL_OPERATIONS_ERROR
DMN: surgical/count_validation_001, surgical/discrepancy_action_001, surgical/xray_requirement_001
ADR: 002, 003, 007, 013 | Refactored 314 -> ~145 LOC
Archetype: COMPLIANCE_VALIDATION (SAFETY-CRITICAL)
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class SurgicalCountVerificationWorker(BaseExternalTaskWorker):
    """V2 surgical count verification worker (thin worker pattern).

    SAFETY-CRITICAL: Verifies surgical sponge, instrument, and needle counts.
    Requires dual-count confirmation. Records all discrepancies.

    Responsibilities:
    1. Parse count items and dual-count confirmations
    2. Validate counts via DMN
    3. Identify discrepancies via DMN
    4. Determine X-ray requirement via DMN
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.count_verification"
    DMN_COUNT_KEY = "count_validation_001"
    DMN_DISCREPANCY_KEY = "discrepancy_action_determination_001"
    DMN_XRAY_KEY = "xray_requirement_evaluation_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute surgical count verification with DMN-based safety checks."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            surgery_id = variables.get("surgery_id", "")
            patient_id = variables.get("patient_id", "")
            count_phase = variables.get("count_phase", "final")  # initial, closing, final
            items = variables.get("items", [])

            self.logger.info(
                "SAFETY: Processing surgical count verification",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "surgery_id": surgery_id, "count_phase": count_phase, "item_count": len(items)},
            )

            all_counts_correct = True
            dual_count_confirmed = True
            discrepancies: List[dict] = []
            requires_xray = False
            counted_by_pairs: List[dict] = []

            # Process each count item
            for item in items:
                item_type = item.get("item_type", "")
                item_name = item.get("item_name", "")
                initial_count = item.get("initial_count", 0)
                final_count = item.get("final_count", 0)
                counted_by_primary = item.get("counted_by_primary", "")
                counted_by_secondary = item.get("counted_by_secondary", "")
                count_confirmed = item.get("count_confirmed", True)

                # Track counter pairs
                pair = {
                    "primary": counted_by_primary,
                    "secondary": counted_by_secondary,
                    "item": item_name,
                }
                if pair not in counted_by_pairs:
                    counted_by_pairs.append(pair)

                # 1. Validate count via DMN
                count_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_COUNT_KEY,
                    variables={
                        "itemType": item_type,
                        "initialCount": initial_count,
                        "finalCount": final_count,
                        "dualCountConfirmed": count_confirmed,
                    },
                    category=self.DMN_CATEGORY,
                )

                if not count_result.get("countsMatch", True):
                    all_counts_correct = False
                    difference = initial_count - final_count

                    # 2. Determine discrepancy action via DMN
                    discrepancy_result = self.evaluate_dmn(
                        context=context,
                        decision_key=self.DMN_DISCREPANCY_KEY,
                        variables={
                            "itemType": item_type,
                            "difference": difference,
                            "countPhase": count_phase,
                        },
                        category=self.DMN_CATEGORY,
                    )

                    discrepancies.append({
                        "item_type": item_type,
                        "item_name": item_name,
                        "initial_count": initial_count,
                        "final_count": final_count,
                        "difference": difference,
                        "action": discrepancy_result.get("action", "RECOUNT"),
                        "severity": discrepancy_result.get("severity", "HIGH"),
                    })

                    # CRITICAL: Log discrepancy
                    self.logger.critical(
                        "SURGICAL COUNT DISCREPANCY DETECTED",
                        extra={
                            "surgery_id": surgery_id,
                            "item_type": item_type,
                            "item_name": item_name,
                            "difference": difference,
                        },
                    )

                    # 3. Determine X-ray requirement via DMN
                    xray_result = self.evaluate_dmn(
                        context=context,
                        decision_key=self.DMN_XRAY_KEY,
                        variables={
                            "itemType": item_type,
                            "hasDiscrepancy": True,
                            "countPhase": count_phase,
                        },
                        category=self.DMN_CATEGORY,
                    )

                    if xray_result.get("xrayRequired", False):
                        requires_xray = True
                        self.logger.critical(
                            "X-RAY REQUIRED: Count discrepancy",
                            extra={"surgery_id": surgery_id, "item_type": item_type},
                        )

                # Check dual count confirmation
                if not count_confirmed:
                    dual_count_confirmed = False

            # Generate verification ID
            verification_id = f"CNT-{surgery_id}-{count_phase}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            verification_status = "PASSED" if all_counts_correct and dual_count_confirmed else "FAILED"

            return TaskResult.success({
                "verification_id": verification_id,
                "surgery_id": surgery_id,
                "patient_id": patient_id,
                "count_phase": count_phase,
                "all_counts_correct": all_counts_correct,
                "dual_count_confirmed": dual_count_confirmed,
                "discrepancies": discrepancies,
                "requires_xray": requires_xray,
                "verification_status": verification_status,
                "verification_timestamp": datetime.utcnow().isoformat(),
                "counted_by_pairs": counted_by_pairs,
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"SAFETY: Count verification failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="SURGICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__, "safetyImpact": "HIGH"},
            )
