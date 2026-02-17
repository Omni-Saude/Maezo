"""
Worker para verificação de consentimento informado pré-cirúrgico.
Valida assinatura, correspondência do procedimento e disclosure de riscos.

Archetype: COMPLIANCE_VALIDATION
"""
from __future__ import annotations
from typing import Any, Dict
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_CONSENT")


class SurgicalConsentWorker(BaseExternalTaskWorker):
    """Verificação de consentimento informado. Topic: surgical.consent"""

    TOPIC = "surgical.consent"
    OPERATION_NAME = "Verificação de Consentimento Informado"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        consent_signed = variables.get("consentSigned", False)
        procedure_on_consent = variables.get("procedureOnConsent", "")
        risks_disclosed = variables.get("risksDisclosed", False)
        patient_competent = variables.get("patientCompetent", True)
        witness_present = variables.get("witnessPresent", False)

        # Evaluate consent validation
        dmn_result = self.evaluate_dmn(
            context,
            decision_key="surg_safety_005",
            variables={
                "consentSigned": consent_signed,
                "procedureOnConsent": procedure_on_consent,
                "risksDisclosed": risks_disclosed,
                "patientCompetent": patient_competent,
                "witnessPresent": witness_present,
            },
            category="surgical_services",
        )

        resultado = dmn_result.get("resultado", "REVISAR")
        acao = dmn_result.get("acao", "")
        consent_valid = dmn_result.get("consentValid", False)
        missing_elements = dmn_result.get("missingElements", [])
        requires_witness = dmn_result.get("requiresWitness", False)

        logger.info(
            "Surgical consent validation result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "consent_valid": consent_valid,
                "consent_signed": consent_signed,
                "risks_disclosed": risks_disclosed,
                "missing_elements_count": len(missing_elements),
            },
        )

        if resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_CONSENT_BLOCKED",
                error_message=acao,
                variables={
                    "correlation_id": correlation_id,
                    "missingElements": missing_elements,
                    "consentValid": consent_valid,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "consentValid": consent_valid,
            "missingElements": missing_elements,
            "requiresWitness": requires_witness,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
