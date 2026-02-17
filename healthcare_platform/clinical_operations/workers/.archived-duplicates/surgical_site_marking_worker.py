"""
Worker para verificação de demarcação do sítio cirúrgico.
Valida lateralidade, demarcação visível e correspondência com exames de imagem.

Archetype: COMPLIANCE_VALIDATION
"""
from __future__ import annotations
from typing import Any, Dict
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_SITE_MARKING")


class SurgicalSiteMarkingWorker(BaseExternalTaskWorker):
    """Verificação de demarcação do sítio cirúrgico. Topic: surgical.site_marking"""

    TOPIC = "surgical.site_marking"
    OPERATION_NAME = "Verificação de Demarcação do Sítio Cirúrgico"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        laterality = variables.get("laterality", "")
        site_marked = variables.get("siteMarked", False)
        imaging_confirmed = variables.get("imagingConfirmed", False)
        consent_matches_site = variables.get("consentMatchesSite", False)

        # Evaluate laterality verification
        dmn_result = self.evaluate_dmn(
            context,
            decision_key="surg_safety_004",
            variables={
                "laterality": laterality,
                "siteMarked": site_marked,
                "imagingConfirmed": imaging_confirmed,
                "consentMatchesSite": consent_matches_site,
            },
            category="surgical_services",
        )

        resultado = dmn_result.get("resultado", "REVISAR")
        acao = dmn_result.get("acao", "")
        verification_passed = dmn_result.get("verificationPassed", False)
        discrepancies = dmn_result.get("discrepancies", [])
        marking_required = dmn_result.get("markingRequired", True)

        logger.info(
            "Surgical site marking verification result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "laterality": laterality,
                "site_marked": site_marked,
                "verification_passed": verification_passed,
                "discrepancies_count": len(discrepancies),
            },
        )

        if resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_SITE_MARKING_BLOCKED",
                error_message=acao,
                variables={
                    "correlation_id": correlation_id,
                    "discrepancies": discrepancies,
                    "verificationPassed": verification_passed,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "verificationPassed": verification_passed,
            "discrepancies": discrepancies,
            "markingRequired": marking_required,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
