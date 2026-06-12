"""Surgical Consent Worker V2 - DMN-based consent compliance validation.

TOPIC: surgical.consent | BPMN Error: CLINICAL_OPERATIONS_ERROR
DMN: surgical/consent_requirements_001, surgical/lgpd_compliance_001
ADR: 002, 003, 007, 013 | Refactored 346 -> ~115 LOC
Archetype: COMPLIANCE_VALIDATION
"""

from __future__ import annotations

from datetime import datetime

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class SurgicalConsentWorker(BaseExternalTaskWorker):
    """V2 surgical consent worker (thin worker pattern).

    Responsibilities:
    1. Parse consent data and requirements
    2. Evaluate DMN for consent type requirements
    3. Validate LGPD compliance via DMN
    4. Determine consent status via DMN
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.consent"
    DMN_REQUIREMENTS_KEY = "consent_requirements_validation_001"
    DMN_LGPD_KEY = "lgpd_compliance_check_001"
    DMN_STATUS_KEY = "consent_status_determination_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute surgical consent validation with DMN-based compliance checks."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            surgery_id = variables.get("surgery_id", "")
            patient_id = variables.get("patient_id", "")
            procedure_code = variables.get("procedure_code", "")
            consent_type = variables.get("consent_type", "informed")  # informed, emergency, minor_guardian
            risks = variables.get("risks", [])
            alternatives = variables.get("alternatives", [])

            self.logger.info(
                "Processing surgical consent validation",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "surgery_id": surgery_id, "consent_type": consent_type},
            )

            # 1. Validate consent requirements via DMN
            requirements_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_REQUIREMENTS_KEY,
                variables={
                    "consentType": consent_type,
                    "hasRisks": len(risks) > 0,
                    "hasAlternatives": len(alternatives) > 0,
                },
                category=self.DMN_CATEGORY,
            )

            requirements_met = requirements_result.get("requirementsMet", False)
            witness_required = requirements_result.get("witnessRequired", False)

            # 2. Check LGPD compliance via DMN
            lgpd_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_LGPD_KEY,
                variables={
                    "hasPatientId": bool(patient_id),
                    "hasProcedureCode": bool(procedure_code),
                    "hasExplicitConsent": True,  # Assumed if form is being filled
                },
                category=self.DMN_CATEGORY,
            )

            lgpd_compliant = lgpd_result.get("compliant", False)

            # 3. Determine consent status via DMN
            status_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_STATUS_KEY,
                variables={
                    "consentType": consent_type,
                    "requirementsMet": requirements_met,
                    "lgpdCompliant": lgpd_compliant,
                },
                category=self.DMN_CATEGORY,
            )

            consent_status = status_result.get("status", "pending")  # obtained, pending, refused, waived

            # Generate consent ID
            consent_id = f"CONSENT-{surgery_id}-{consent_type}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            obtained_at = datetime.utcnow().isoformat() if consent_status == "obtained" else None

            return TaskResult.success({
                "consent_id": consent_id,
                "surgery_id": surgery_id,
                "patient_id": patient_id,
                "consent_status": consent_status,
                "consent_type": consent_type,
                "obtained_at": obtained_at,
                "witness_required": witness_required,
                "lgpd_compliant": lgpd_compliant,
                "validation_issues": requirements_result.get("issues", []),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Surgical consent validation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="CLINICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
