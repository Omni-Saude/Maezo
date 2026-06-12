"""Medication Management Worker V2 - DMN-based medication safety checks.

TOPIC: clinical.medication | BPMN Error: CLINICAL_ALERT
DMN: med_dose_001, med_interaction_001, med_allergy_cross_001, med_timing_001, med_highrisk_001, med_route_001
ADR: 002, 003, 007, 013 | Refactored 602 -> ~145 LOC
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class MedicationManagementWorker(BaseExternalTaskWorker):
    """V2 medication management worker (thin worker pattern).

    Archetype: CLINICAL_SCORE
    """

    TOPIC = "clinical.medication"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute medication management with DMN-based validation."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            medications: List[Dict[str, Any]] = variables.get("medication_orders", [])
            allergies: List[str] = variables.get("allergies", [])

            if not medications:
                return TaskResult.bpmn_error(error_code="CLINICAL_ALERT", error_message="Prescricoes de medicamentos obrigatorias")

            self.logger.info("Processing %d medications, %d allergies", len(medications), len(allergies),
                             extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id})

            warnings: List[Dict[str, Any]] = []
            schedule: List[Dict[str, Any]] = []
            overall_action = "PROSSEGUIR"

            for med in medications:
                med_name = med.get("medication_name", "")
                med_class = med.get("medication_class", "GENERAL")

                # Dose validation
                dose_result = self.evaluate_dmn(context=context, decision_key="med_dose_001",
                    variables={"medicationClass": med_class, "doseValue": float(med.get("dose_value", 0)), "doseUnit": med.get("dose_unit", "mg")})
                if dose_result.get("action") != "PROSSEGUIR":
                    warnings.append({"type": "DOSE", "medication": med_name, "action": dose_result.get("action", "REVISAR"), "reason": dose_result.get("reason", "")})
                    overall_action = self._escalate(overall_action, dose_result.get("action", "REVISAR"))

                # High-risk check
                hr_result = self.evaluate_dmn(context=context, decision_key="med_highrisk_001", variables={"medicationClass": med_class})
                if hr_result.get("isHighRisk"):
                    warnings.append({"type": "HIGH_RISK", "medication": med_name, "action": hr_result.get("action", "REVISAR"), "requiredChecks": hr_result.get("requiredChecks", "")})
                    overall_action = self._escalate(overall_action, hr_result.get("action", "REVISAR"))

                # Route validation
                if med.get("medication_form"):
                    route_result = self.evaluate_dmn(context=context, decision_key="med_route_001",
                        variables={"medicationForm": med.get("medication_form", ""), "prescribedRoute": med.get("route", "ORAL")})
                    if route_result.get("action") != "PROSSEGUIR":
                        warnings.append({"type": "ROUTE", "medication": med_name, "action": route_result.get("action", "REVISAR"), "reason": route_result.get("reason", "")})
                        overall_action = self._escalate(overall_action, route_result.get("action", "REVISAR"))

                # Timing / schedule
                timing_result = self.evaluate_dmn(context=context, decision_key="med_timing_001", variables={"frequency": med.get("frequency", "24/24h")})
                times = (timing_result.get("scheduleTimes") or "08:00").split(",")
                for t in times:
                    schedule.append({"medication_name": med_name, "dosage": med.get("dosage", ""), "route": med.get("route", "ORAL"), "scheduled_time": t.strip(), "status": "pending"})

                # Allergy cross-reactivity
                for allergy in allergies:
                    allergy_result = self.evaluate_dmn(context=context, decision_key="med_allergy_cross_001",
                        variables={"allergyGroup": allergy.upper().strip(), "medicationGroup": med_class})
                    if allergy_result.get("crossReactive"):
                        warnings.append({"type": "ALLERGY", "medication": med_name, "allergy": allergy, "action": allergy_result.get("action", "BLOQUEAR"), "riskLevel": allergy_result.get("riskLevel", "HIGH")})
                        overall_action = self._escalate(overall_action, allergy_result.get("action", "BLOQUEAR"))

            # Drug-drug interactions (pairwise)
            for i, med1 in enumerate(medications):
                for med2 in medications[i + 1:]:
                    inter_result = self.evaluate_dmn(context=context, decision_key="med_interaction_001",
                        variables={"drug1Class": med1.get("medication_class", ""), "drug2Class": med2.get("medication_class", "")})
                    if inter_result.get("severity", "NONE") != "NONE":
                        warnings.append({"type": "INTERACTION", "drug1": med1.get("medication_name", ""), "drug2": med2.get("medication_name", ""),
                                       "severity": inter_result.get("severity"), "action": inter_result.get("action", "REVISAR"), "description": inter_result.get("description", "")})
                        overall_action = self._escalate(overall_action, inter_result.get("action", "REVISAR"))

            schedule.sort(key=lambda s: s["scheduled_time"])

            return TaskResult.success({
                "action": overall_action,
                "validated_medications": medications,
                "interaction_warnings": warnings,
                "administration_schedule": schedule,
                "warningCount": len(warnings),
                "processedAt": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Medication management failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="CLINICAL_ALERT", error_message=str(e), variables={"errorType": type(e).__name__, "action": "REVISAR"})

    @staticmethod
    def _escalate(current: str, new: str) -> str:
        """Return the more restrictive action (fail-safe escalation)."""
        priority = {"PROSSEGUIR": 0, "REVISAR": 1, "BLOQUEAR": 2}
        return new if priority.get(new, 1) > priority.get(current, 1) else current
