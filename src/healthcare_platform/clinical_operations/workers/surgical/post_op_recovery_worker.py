"""Post-Operative Recovery Worker V2 - DMN-based PACU recovery monitoring.

TOPIC: surgical.post_op_recovery | BPMN Error: SURGICAL_OPERATIONS_ERROR
DMN: surgical/aldrete_scoring_001, surgical/recovery_status_001, surgical/discharge_criteria_001
ADR: 002, 003, 007, 013 | Refactored 374 -> ~145 LOC
Archetype: CLINICAL_SCORE
"""

from __future__ import annotations

from datetime import datetime

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class PostOpRecoveryWorker(BaseExternalTaskWorker):
    """V2 post-operative recovery worker (thin worker pattern).

    Responsibilities:
    1. Parse Aldrete score components
    2. Evaluate DMN for total Aldrete scoring
    3. Determine recovery status via DMN
    4. Check discharge readiness via DMN
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.post_op_recovery"
    DMN_ALDRETE_KEY = "aldrete_total_score_001"
    DMN_RECOVERY_KEY = "recovery_status_determination_001"
    DMN_DISCHARGE_KEY = "discharge_criteria_check_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute post-op recovery assessment with DMN-based scoring."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            surgery_id = variables.get("surgery_id", "")
            patient_id = variables.get("patient_id", "")
            pacu_bed_id = variables.get("pacu_bed_id", "")

            # Aldrete score components (0-2 each)
            aldrete_activity = variables.get("aldrete_activity", 0)
            aldrete_respiration = variables.get("aldrete_respiration", 0)
            aldrete_circulation = variables.get("aldrete_circulation", 0)
            aldrete_consciousness = variables.get("aldrete_consciousness", 0)
            aldrete_oxygen_saturation = variables.get("aldrete_oxygen_saturation", 0)

            pain_score = variables.get("pain_score", 0)
            temperature = variables.get("temperature", 36.5)
            complications = variables.get("complications", [])

            self.logger.info(
                "Processing post-op recovery assessment",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "surgery_id": surgery_id, "pacu_bed": pacu_bed_id},
            )

            # 1. Calculate Total Aldrete Score via DMN
            aldrete_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_ALDRETE_KEY,
                variables={
                    "activity": aldrete_activity,
                    "respiration": aldrete_respiration,
                    "circulation": aldrete_circulation,
                    "consciousness": aldrete_consciousness,
                    "oxygenSaturation": aldrete_oxygen_saturation,
                },
                category=self.DMN_CATEGORY,
            )
            aldrete_total = aldrete_result.get("totalScore", 0)

            # 2. Determine Recovery Status via DMN
            recovery_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_RECOVERY_KEY,
                variables={"aldreteScore": aldrete_total, "complications": len(complications)},
                category=self.DMN_CATEGORY,
            )
            recovery_status = recovery_result.get("status", "monitoring")

            # 3. Check Discharge Readiness via DMN
            discharge_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DISCHARGE_KEY,
                variables={
                    "aldreteScore": aldrete_total,
                    "painScore": pain_score,
                    "temperature": temperature,
                    "hasComplications": len(complications) > 0,
                },
                category=self.DMN_CATEGORY,
            )
            discharge_ready = discharge_result.get("dischargeReady", False)

            # Generate assessment ID
            assessment_id = f"PACU-{surgery_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Build recommendations from DMN outputs
            recommendations = []
            recommendations.extend(recovery_result.get("recommendations", []))
            recommendations.extend(discharge_result.get("recommendations", []))

            return TaskResult.success({
                "assessment_id": assessment_id,
                "surgery_id": surgery_id,
                "patient_id": patient_id,
                "pacu_bed_id": pacu_bed_id,
                "aldrete_total_score": aldrete_total,
                "recovery_status": recovery_status,
                "discharge_ready": discharge_ready,
                "who_sign_out_completed": variables.get("who_checklist_phase") == "sign_out",
                "recommendations": recommendations,
                "assessment_timestamp": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Post-op recovery assessment failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="SURGICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
