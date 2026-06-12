"""
Clinical Decision Support Worker V2 - DMN-based clinical decision support

TOPIC: clinical.decision_support | BPMN Error: CLINICAL_ALERT
DMN: decision_rule_001, decision_recommendation_001, decision_alert_001
ADR: 002, 003, 007, 013 | Refactored 864 -> ~120 LOC

Archetype: CLINICAL_ALERT
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class ClinicalDecisionSupportWorker(BaseExternalTaskWorker):
    """
    V2 clinical decision support worker (thin worker pattern).

    Responsibilities:
    1. Parse clinical context and patient data
    2. Evaluate DMN for decision rules and recommendations
    3. Generate clinical alerts and guidance
    4. Return structured output for BPMN routing

    All business rules (decision criteria, thresholds) handled by DMN.
    All orchestration (notifications, escalation) handled by BPMN.
    """

    TOPIC = "clinical.decision_support"
    DMN_DECISION_KEY = "decision_rule_001"
    DMN_CATEGORY = "clinical_safety"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute clinical decision support via DMN evaluation."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            decision_context = variables.get("decision_context", {})
            patient_data = variables.get("patient_data", {})
            clinical_scenario = variables.get("clinical_scenario", "general")

            self.logger.info("Processing decision support: scenario=%s", clinical_scenario,
                             extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id})

            # Evaluate decision rule DMN
            rule_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DECISION_KEY,
                variables={
                    "clinicalScenario": clinical_scenario,
                    "patientAge": patient_data.get("age", 0),
                    "patientConditions": patient_data.get("conditions", []),
                    "labValues": decision_context.get("lab_values", {}),
                },
                category=self.DMN_CATEGORY,
            )

            # Evaluate recommendation DMN
            recommendation_result = self.evaluate_dmn(
                context=context,
                decision_key="decision_recommendation_001",
                variables={
                    "clinicalScenario": clinical_scenario,
                    "ruleOutput": rule_result.get("ruleType", ""),
                    "severity": rule_result.get("severity", "low"),
                },
                category=self.DMN_CATEGORY,
            )

            # Evaluate alert DMN
            alert_result = self.evaluate_dmn(
                context=context,
                decision_key="decision_alert_001",
                variables={
                    "severity": rule_result.get("severity", "low"),
                    "recommendationType": recommendation_result.get("recommendationType", ""),
                },
                category=self.DMN_CATEGORY,
            )

            action = rule_result.get("action", "REVISAR")
            recommendations: List[Dict[str, Any]] = recommendation_result.get("recommendations", [])
            alerts: List[Dict[str, Any]] = alert_result.get("alerts", [])

            return TaskResult.success({
                "action": action,
                "nivelAlerta": rule_result.get("nivelAlerta", "OK"),
                "acaoRequerida": rule_result.get("acaoRequerida", ""),
                "justificativa": rule_result.get("justificativa", ""),
                "ruleType": rule_result.get("ruleType", ""),
                "severity": rule_result.get("severity", "low"),
                "recommendations": recommendations,
                "alerts": alerts,
                "recommendationCount": len(recommendations),
                "alertCount": len(alerts),
                "requiresPhysicianReview": alert_result.get("requiresPhysicianReview", False),
                "escalationRequired": alert_result.get("escalationRequired", False),
                "clinicalScenario": clinical_scenario,
                "processedAt": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Clinical decision support failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="CLINICAL_ALERT", error_message=str(e), variables={"errorType": type(e).__name__})
