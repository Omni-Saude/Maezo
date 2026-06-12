"""
Clinical Auditing Worker V2 (ADMIN_ADJUDICATION archetype)
TOPIC: clinical.auditing | 707 LOC -> ~100 LOC | 8 DMN tables in clinical_safety/
ADR: 002, 003, 007, 013 | Author: Claude Flow V3 | License: MIT
"""

from __future__ import annotations
from datetime import datetime
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult

_AUDIT_DMN = {
    "documentation": ("audit_documentation_completeness", lambda v: {"completenessScore": float(v.get("completeness_score", v.get("compliance_score", 0)))}),
    "medication": ("audit_documentation_completeness", lambda v: {"completenessScore": float(v.get("completeness_score", v.get("compliance_score", 0)))}),
    "procedure": ("audit_protocol_adherence", lambda v: {"adherenceRate": float(v.get("adherence_rate", 0)), "isCriticalProtocol": v.get("is_critical_protocol", False)}),
    "protocol": ("audit_protocol_adherence", lambda v: {"adherenceRate": float(v.get("adherence_rate", 0)), "isCriticalProtocol": v.get("is_critical_protocol", False)}),
    "coding": ("audit_coding_accuracy", lambda v: {"accuracyRate": float(v.get("accuracy_rate", 0))}),
    "billing": ("audit_billing_rules", lambda v: {"billingDiscrepancy": float(v.get("billing_discrepancy", 0))}),
    "regulatory": ("audit_regulatory_compliance", lambda v: {"regulatoryScore": float(v.get("regulatory_score", 0)), "criticalFindings": int(v.get("critical_findings_count", 0))}),
    "safety": ("audit_safety_checklist", lambda v: {"checklistCompletionPct": float(v.get("checklist_completion_pct", 0))}),
}


class ClinicalAuditingWorker(BaseExternalTaskWorker):
    """V2 clinical auditing worker - 100% DMN delegation.

    Archetype: CLINICAL_SCORE
    """

    TOPIC = "clinical.auditing"
    DMN_DECISION_KEY = "audit_rule_compliance"
    DMN_CATEGORY = "clinical_safety"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute clinical audit via DMN evaluation."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            audit_type = variables.get("audit_type", "documentation")

            self.logger.info("Processing audit: type=%s", audit_type, extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id})

            # Evaluate type-specific, compliance, and priority DMNs
            dmn_key, var_mapper = _AUDIT_DMN.get(audit_type, _AUDIT_DMN["documentation"])
            type_vars = {"auditType": audit_type, **var_mapper(variables)}
            type_result = self.evaluate_dmn(context=context, decision_key=dmn_key, variables=type_vars, category=self.DMN_CATEGORY)

            compliance_result = self.evaluate_dmn(
                context=context, decision_key=self.DMN_DECISION_KEY,
                variables={"complianceScore": float(variables.get("compliance_score", 0)), "criticalFindingsCount": int(variables.get("critical_findings_count", 0))},
                category=self.DMN_CATEGORY,
            )

            priority_result = self.evaluate_dmn(
                context=context, decision_key="audit_priority_classification",
                variables={"auditType": audit_type, "findingSeverity": variables.get("finding_severity", "medium")},
                category=self.DMN_CATEGORY,
            )

            # Worst-case action (fail-safe)
            actions = [type_result.get("action", "REVISAR"), compliance_result.get("action", "REVISAR")]
            action = min(actions, key=lambda a: {"BLOQUEAR": 0, "REVISAR": 1, "PROSSEGUIR": 2}.get(a, 1))

            return TaskResult.success({
                "action": action,
                "auditId": f"AUDIT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "auditType": audit_type,
                "encounterReference": variables.get("encounter_reference", ""),
                "complianceScore": float(variables.get("compliance_score", 0)),
                "overallStatus": compliance_result.get("overallStatus", "needs_review"),
                "findingPriority": priority_result.get("priority", "medium"),
                "correctiveActionDueDays": priority_result.get("dueDays", 7),
                "nextAuditDays": compliance_result.get("nextAuditDays", 30),
                "justificativa": compliance_result.get("justificativa", ""),
                "processedAt": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Clinical audit failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="ERR_CLINICAL_AUDIT", error_message=str(e), variables={"errorType": type(e).__name__})
