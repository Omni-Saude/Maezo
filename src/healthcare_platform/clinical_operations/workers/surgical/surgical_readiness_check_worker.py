"""
Worker para avaliação de prontidão cirúrgica (WHO Surgical Safety Checklist).
Valida todas as checagens de segurança antes de autorizar início da cirurgia.
"""
from __future__ import annotations
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_READINESS_CHECK")


class SurgicalReadinessCheckWorker(BaseExternalTaskWorker):
    """Avaliação de prontidão cirúrgica.

    Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = "surgical.readiness_check"
    OPERATION_NAME = "Avaliação de Prontidão Cirúrgica"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        all_checks_complete = variables.get("allChecksComplete", False)
        consent_verified = variables.get("consentVerified", False)
        site_marked = variables.get("siteMarked", False)
        team_ready = variables.get("teamReady", False)
        materials_ready = variables.get("materialsReady", False)
        anesthesia_cleared = variables.get("anesthesiaCleared", False)

        # Evaluate WHO sign-in
        signin_result = self.evaluate_dmn(
            context,
            decision_key="surg_safety_001",
            variables={
                "consentVerified": consent_verified,
                "siteMarked": site_marked,
                "anesthesiaCleared": anesthesia_cleared,
            },
            category="surgical_services",
        )

        signin_passed = signin_result.get("resultado", "REVISAR")
        # TODO: signin_issues sera usado para detalhar problemas no signin cirurgico
        # signin_issues = signin_result.get("issues", [])

        # Evaluate timeout rules
        timeout_result = self.evaluate_dmn(
            context,
            decision_key="surg_safety_012",
            variables={
                "allChecksComplete": all_checks_complete,
                "teamReady": team_ready,
                "materialsReady": materials_ready,
            },
            category="surgical_services",
        )

        resultado = timeout_result.get("resultado", "REVISAR")
        acao = timeout_result.get("acao", "")
        can_proceed = timeout_result.get("canProceed", False)
        pending_items = timeout_result.get("pendingItems", [])
        critical_failures = timeout_result.get("criticalFailures", [])

        logger.info(
            "Surgical readiness check result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "can_proceed": can_proceed,
                "signin_passed": signin_passed == "PROSSEGUIR",
                "pending_items_count": len(pending_items),
                "critical_failures_count": len(critical_failures),
            },
        )

        if resultado == "BLOQUEAR" or not can_proceed:
            return TaskResult.bpmn_error(
                error_code="SURG_READINESS_BLOCKED",
                error_message=acao,
                variables={
                    "correlation_id": correlation_id,
                    "canProceed": False,
                    "pendingItems": pending_items,
                    "criticalFailures": critical_failures,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "canProceed": can_proceed,
            "signinPassed": signin_passed == "PROSSEGUIR",
            "pendingItems": pending_items,
            "criticalFailures": critical_failures,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
