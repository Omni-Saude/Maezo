"""Vital Signs Monitoring Worker V2 - DMN-based threshold evaluation.

TOPIC: clinical.vital_signs | BPMN Error: CLINICAL_ALERT
DMN: vit_threshold_001, vit_ews_001, vit_escalation_001
ADR: 002, 003, 007, 013 | Refactored 585 -> ~135 LOC
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult

_VITAL_SIGN_TYPES = ["heart_rate", "oxygen_saturation", "temperature_celsius", "systolic_bp", "diastolic_bp", "respiratory_rate"]


class VitalSignsMonitoringWorker(BaseExternalTaskWorker):
    """V2 vital signs monitoring worker (thin worker pattern).

    Archetype: CLINICAL_SCORE
    """

    TOPIC = "clinical.vital_signs"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute vital signs monitoring with DMN-based evaluation."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            vital_signs: Dict[str, Any] = variables.get("vital_signs", {})

            if not vital_signs:
                return TaskResult.bpmn_error(error_code="CLINICAL_ALERT", error_message="Sinais vitais obrigatorios para monitorizacao")

            self.logger.info("Processing vital signs: %d parameters", len(vital_signs),
                             extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id})

            # Evaluate each vital sign against threshold DMN
            alerts: List[Dict[str, Any]] = []
            critical_count = 0
            highest_severity = "INFO"

            for vs_type in _VITAL_SIGN_TYPES:
                value = vital_signs.get(vs_type)
                if value is None:
                    continue

                dmn_result = self.evaluate_dmn(context=context, decision_key="vit_threshold_001",
                                              variables={"vitalSignType": vs_type, "value": float(value)})

                action = dmn_result.get("action", "REVISAR")
                severity = dmn_result.get("severity", "WARNING")

                if severity == "CRITICAL":
                    critical_count += 1
                    highest_severity = "CRITICAL"
                elif severity == "WARNING" and highest_severity != "CRITICAL":
                    highest_severity = "WARNING"

                if action != "PROSSEGUIR":
                    alerts.append({"parameter": vs_type, "value": float(value), "severity": severity,
                                 "classification": dmn_result.get("classification", ""), "action": action})

            # Evaluate EWS score if provided
            ews_result: Dict[str, Any] = {}
            if variables.get("ewsScore") is not None:
                ews_result = self.evaluate_dmn(context=context, decision_key="vit_ews_001",
                                              variables={"ewsScore": int(variables.get("ewsScore"))})

            # Evaluate escalation rules
            escalation = self.evaluate_dmn(context=context, decision_key="vit_escalation_001",
                                          variables={"severityLevel": highest_severity, "criticalCount": critical_count})

            action = escalation.get("action", "REVISAR")
            requires_immediate = escalation.get("requiresImmediate", False)

            # Map to output status
            status = "CRITICAL" if highest_severity == "CRITICAL" else ("ABNORMAL" if highest_severity == "WARNING" else "NORMAL")

            return TaskResult.success({
                "action": action,
                "vital_signs_status": status,
                "severity_level": highest_severity,
                "requires_immediate_attention": requires_immediate,
                "alerts": alerts,
                "alertCount": len(alerts),
                "criticalCount": critical_count,
                "notifyTeam": escalation.get("notifyTeam", ""),
                "ewsRiskLevel": ews_result.get("riskLevel", ""),
                "ewsEscalationInterval": ews_result.get("escalationInterval", ""),
                "processedAt": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Vital signs monitoring failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="CLINICAL_ALERT", error_message=str(e), variables={"errorType": type(e).__name__, "action": "REVISAR"})
