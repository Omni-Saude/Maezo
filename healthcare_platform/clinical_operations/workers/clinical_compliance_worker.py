"""
Clinical Compliance Worker V2 - TOPIC: clinical.compliance

Refactored from 588 lines to ~150 lines using DMN-first approach.
Business rules extracted to 9 DMN tables under clinical_safety/compliance/.
Archetype: ADMIN_ADJUDICATION (regulatory rules, scoring, escalation).

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class ClinicalComplianceWorker(BaseExternalTaskWorker):
    """
    V2 clinical compliance worker (thin worker pattern).

    Responsibilities:
    1. Parse compliance verification request
    2. Evaluate DMN for regulatory rules, scoring, escalation
    3. Return structured output for BPMN routing

    All business rules (ANVISA, ANS, CNES, JNA) handled by DMN.
    All orchestration (corrective actions, notifications) handled by BPMN.
    """

    TOPIC = "clinical.compliance"
    DMN_DECISION_KEY = "compliance_regulatory"
    DMN_CATEGORY = "clinical_safety"

    # DMN decision keys for each compliance sub-domain
    DMN_KEYS = {
        "regulatory": "compliance_regulatory",
        "documentation": "compliance_documentation",
        "consent": "compliance_consent",
        "medication": "compliance_medication",
        "infection": "compliance_infection_control",
        "safety": "compliance_safety_protocol",
        "reporting": "compliance_reporting",
        "escalation": "compliance_escalation",
        "scoring": "compliance_scoring",
    }

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute clinical compliance verification via DMN evaluation."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            compliance_domain = variables.get("compliance_domain", "regulatory")
            encounter_ref = variables.get("encounter_reference", "")
            rule_reference = variables.get("rule_reference", "")
            severity = variables.get("severity", "")
            verification_items = variables.get("verification_items", [])

            self.logger.info(
                "Processing compliance: domain=%s, encounter=%s",
                compliance_domain, encounter_ref,
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id, "task_id": context.task_id},
            )

            # 1. Evaluate primary regulatory compliance DMN
            regulatory_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_KEYS.get("regulatory", self.DMN_DECISION_KEY),
                variables={
                    "complianceDomain": compliance_domain,
                    "ruleReference": rule_reference,
                    "encounterReference": encounter_ref,
                    "severity": severity,
                },
                category=self.DMN_CATEGORY,
            )

            action = regulatory_result.get("action", "REVISAR")

            # 2. Evaluate compliance scoring
            scoring_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_KEYS["scoring"],
                variables={
                    "complianceDomain": compliance_domain,
                    "violationsCount": int(regulatory_result.get("violationsCount", 0)),
                    "criticalCount": int(regulatory_result.get("criticalCount", 0)),
                    "totalRules": len(verification_items) or 1,
                },
                category=self.DMN_CATEGORY,
            )

            # 3. Evaluate escalation rules if violations found
            escalation_result = {}
            if action in ("BLOQUEAR", "REVISAR"):
                escalation_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_KEYS["escalation"],
                    variables={
                        "complianceDomain": compliance_domain,
                        "severity": regulatory_result.get("violationSeverity", "minor"),
                        "criticalCount": int(regulatory_result.get("criticalCount", 0)),
                        "complianceScore": float(scoring_result.get("complianceScore", 100.0)),
                    },
                    category=self.DMN_CATEGORY,
                )

            # 4. Build output with ADMIN_ADJUDICATION archetype
            compliance_status = scoring_result.get("complianceStatus", "partial")
            compliance_score = float(scoring_result.get("complianceScore", 0.0))

            return TaskResult.success({
                # DMN routing outputs (3-output pattern)
                "action": action,
                "nivelAlerta": regulatory_result.get("nivelAlerta", "Revisar"),
                "acaoRequerida": regulatory_result.get("acaoRequerida", ""),
                "justificativa": regulatory_result.get("justificativa", ""),
                # Compliance results
                "complianceStatus": compliance_status,
                "complianceScore": compliance_score,
                "violationsCount": int(regulatory_result.get("violationsCount", 0)),
                "criticalViolationsCount": int(regulatory_result.get("criticalCount", 0)),
                "violationSeverity": regulatory_result.get("violationSeverity", ""),
                # Escalation
                "escalationLevel": escalation_result.get("escalationLevel", "none"),
                "escalationTarget": escalation_result.get("escalationTarget", ""),
                "nextVerificationDays": int(escalation_result.get("nextVerificationDays", 90)),
                # Metadata
                "complianceDomain": compliance_domain,
                "verifiedAt": datetime.utcnow().isoformat(),
                "dmnDecisionKey": self.DMN_DECISION_KEY,
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Compliance processing failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_CLINICAL_COMPLIANCE",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
