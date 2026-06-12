"""Anesthesia Evaluation Worker V2 - DMN-based risk assessment.

TOPIC: surgical.anesthesia_eval | BPMN Error: CLINICAL_OPERATIONS_ERROR
DMN: surgical/asa_risk_001, surgical/fasting_001, surgical/airway_risk_001
ADR: 002, 003, 007, 013 | Refactored 438 -> ~145 LOC
Archetype: CLINICAL_SCORE
"""

from __future__ import annotations

from datetime import datetime

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class AnesthesiaEvaluationWorker(BaseExternalTaskWorker):
    """V2 anesthesia evaluation worker (thin worker pattern).

    Responsibilities:
    1. Parse anesthesia evaluation inputs
    2. Evaluate DMN for ASA risk classification
    3. Validate fasting compliance via DMN
    4. Assess airway risk (BMI-based) via DMN
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.anesthesia_eval"
    DMN_ASA_RISK_KEY = "asa_risk_classification_001"
    DMN_FASTING_KEY = "fasting_compliance_001"
    DMN_AIRWAY_RISK_KEY = "airway_risk_assessment_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute anesthesia evaluation with DMN-based risk assessment."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            surgery_id = variables.get("surgery_id", "")
            patient_id = variables.get("patient_id", "")
            asa_classification = variables.get("asa_classification", 1)
            anesthesia_type = variables.get("anesthesia_type", "general")
            weight_kg = variables.get("weight_kg", 70.0)
            height_cm = variables.get("height_cm", 170.0)
            fasting_hours = variables.get("fasting_hours", 0.0)
            comorbidities = variables.get("comorbidities", [])
            allergies = variables.get("allergies", [])

            self.logger.info(
                "Processing anesthesia evaluation",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "surgery_id": surgery_id, "asa": asa_classification},
            )

            # Calculate BMI
            height_m = height_cm / 100.0
            bmi = weight_kg / (height_m * height_m)

            # 1. ASA Risk Classification DMN
            asa_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_ASA_RISK_KEY,
                variables={"asaClassification": asa_classification},
                category=self.DMN_CATEGORY,
            )
            risk_level = asa_result.get("riskLevel", "moderate")

            # 2. Fasting Compliance DMN
            fasting_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_FASTING_KEY,
                variables={"fastingHours": fasting_hours, "anesthesiaType": anesthesia_type},
                category=self.DMN_CATEGORY,
            )
            fasting_compliant = fasting_result.get("compliant", False)

            # 3. Airway Risk Assessment DMN
            airway_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_AIRWAY_RISK_KEY,
                variables={"bmi": bmi, "comorbidities": ",".join(comorbidities)},
                category=self.DMN_CATEGORY,
            )
            airway_risk = airway_result.get("airwayRisk", "low")

            # Determine clearance
            cleared_for_surgery = (
                fasting_compliant
                and asa_classification < 5
                and risk_level != "critical"
            )

            # Generate evaluation ID
            evaluation_id = f"ANES-{surgery_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            return TaskResult.success({
                "evaluation_id": evaluation_id,
                "surgery_id": surgery_id,
                "patient_id": patient_id,
                "asa_classification": asa_classification,
                "anesthesia_type": anesthesia_type,
                "risk_level": risk_level,
                "airway_risk": airway_risk,
                "fasting_compliant": fasting_compliant,
                "cleared_for_surgery": cleared_for_surgery,
                "bmi": round(bmi, 2),
                "allergies": allergies,
                "evaluated_at": datetime.utcnow().isoformat(),
                "notes": asa_result.get("recommendation", ""),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Anesthesia evaluation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="CLINICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
