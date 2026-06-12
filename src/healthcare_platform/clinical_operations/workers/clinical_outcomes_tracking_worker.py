"""
Clinical Outcomes Tracking Worker V2 (CLINICAL_SCORE archetype)
TOPIC: clinical.outcomes | 809 LOC -> ~135 LOC | 10 DMN tables in clinical_safety/
ADR: 002, 003, 007, 013 | Author: Claude Flow V3 | License: MIT
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class ClinicalOutcomesTrackingWorker(BaseExternalTaskWorker):
    """V2 outcomes tracking worker - thin pattern with DMN aggregation.

    Archetype: CLINICAL_SCORE
    """

    TOPIC = "clinical.outcomes"
    DMN_DECISION_KEY = "outcome_scoring"
    DMN_CATEGORY = "clinical_safety"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute clinical outcomes tracking via DMN evaluation."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            measures = variables.get("outcome_measures", [])
            assessment_type = variables.get("assessment_type", "interim")
            improvement_trend = variables.get("improvement_trend", "stable")
            clinical_significance = variables.get("clinical_significance", "no_change")

            self.logger.info("Processing outcomes: measures=%d, type=%s", len(measures), assessment_type,
                             extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id})

            # Compute averages
            avg_score = self._avg_score(measures)
            goal_achievement_pct = self._goal_achievement(variables.get("outcome_goals", []))

            # Evaluate 6 DMN tables in parallel
            scoring_result = self.evaluate_dmn(context=context, decision_key=self.DMN_DECISION_KEY,
                                               variables={"assessmentType": assessment_type, "measureCount": len(measures), "avgNormalizedScore": avg_score}, category=self.DMN_CATEGORY)

            trajectory_result = self.evaluate_dmn(context=context, decision_key="recovery_trajectory",
                                                 variables={"improvementTrend": improvement_trend, "statisticallySignificant": variables.get("statistical_significance", False)}, category=self.DMN_CATEGORY)

            los_result = self.evaluate_dmn(context=context, decision_key="length_of_stay_prediction",
                                          variables={"outcomeScore": avg_score, "assessmentType": assessment_type}, category=self.DMN_CATEGORY)

            readmission_result = self.evaluate_dmn(context=context, decision_key="readmission_risk",
                                                  variables={"improvementTrend": improvement_trend, "outcomeScore": avg_score}, category=self.DMN_CATEGORY)

            complication_result = self.evaluate_dmn(context=context, decision_key="complication_classification",
                                                   variables={"clinicalSignificance": clinical_significance, "improvementTrend": improvement_trend}, category=self.DMN_CATEGORY)

            quality_result = self.evaluate_dmn(context=context, decision_key="quality_metrics",
                                              variables={"benchmarkPercentile": variables.get("benchmark_percentile", 50.0), "goalAchievementPct": goal_achievement_pct}, category=self.DMN_CATEGORY)

            # Worst-case action (fail-safe)
            actions = [scoring_result.get("action", "REVISAR"), trajectory_result.get("action", "REVISAR"),
                      readmission_result.get("action", "REVISAR"), complication_result.get("action", "REVISAR")]
            action = min(actions, key=lambda a: {"BLOQUEAR": 0, "REVISAR": 1, "PROSSEGUIR": 2}.get(a, 1))

            return TaskResult.success({
                "action": action,
                "outcomeScore": avg_score,
                "outcomeCategory": scoring_result.get("outcomeCategory", "unclassified"),
                "improvementTrend": improvement_trend,
                "trajectory": trajectory_result.get("trajectory", "unknown"),
                "readmissionRisk": readmission_result.get("riskLevel", "low"),
                "complicationGrade": complication_result.get("complicationGrade", "none"),
                "qualityTier": quality_result.get("qualityTier", "unclassified"),
                "goalAchievementPct": goal_achievement_pct,
                "nextAssessmentDays": los_result.get("nextAssessmentDays", 30),
                "patientReference": variables.get("patient_reference", ""),
                "encounterReference": variables.get("encounter_reference", ""),
                "assessmentType": assessment_type,
                "justificativa": scoring_result.get("justificativa", ""),
                "processedAt": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Outcomes tracking failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="ERR_OUTCOMES_TRACKING", error_message=str(e), variables={"errorType": type(e).__name__})

    @staticmethod
    def _avg_score(measures: List[Dict[str, Any]]) -> float:
        """Compute average normalized score (0-100)."""
        if not measures:
            return 0.0
        scores = [min(100.0, max(0.0, float(m.get("value", 0)))) for m in measures]
        return round(sum(scores) / len(scores), 2)

    @staticmethod
    def _goal_achievement(goals: List[Dict[str, Any]]) -> float:
        """Compute average goal achievement percentage."""
        if not goals:
            return 0.0
        achievements = [min(100.0, (g.get("current_value", 0) / g.get("target_value", 100) * 100)) if g.get("target_value", 100) > 0 else 0.0 for g in goals]
        return round(sum(achievements) / len(achievements), 1)
