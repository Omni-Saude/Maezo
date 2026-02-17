"""
Worker para transferência pós-operatória e monitoramento na SRPA (PACU).
Valida critérios de alta da SRPA e coordena transferências seguras.
"""
from __future__ import annotations
from typing import Any, Dict
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_POST_OP")


class SurgicalPostOpRecoveryWorker(BaseExternalTaskWorker):
    """Transferência para SRPA (PACU) e monitoramento pós-operatório.

    Archetype: CLINICAL_ALERT
    """

    TOPIC = "surgical.post_op_recovery"
    OPERATION_NAME = "Transferência para SRPA (PACU)"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        alderete_score = variables.get("aldereteScore", 0)
        pain_controlled = variables.get("painControlled", False)
        nausea_controlled = variables.get("nauseaControlled", True)
        bleeding_controlled = variables.get("bleedingControlled", True)
        consciousness_level = variables.get("consciousnessLevel", "ALERTA")
        handoff_type = variables.get("handoffType", "PACU")
        vital_signs_stable = variables.get("vitalSignsStable", False)

        # Evaluate PACU discharge criteria
        discharge_result = self.evaluate_dmn(
            context,
            decision_key="surg_coord_002",
            variables={
                "aldereteScore": alderete_score,
                "painControlled": pain_controlled,
                "nauseaControlled": nausea_controlled,
                "bleedingControlled": bleeding_controlled,
                "consciousnessLevel": consciousness_level,
                "vitalSignsStable": vital_signs_stable,
            },
            category="surgical_services",
        )

        resultado = discharge_result.get("resultado", "REVISAR")
        acao = discharge_result.get("acao", "")
        risco = discharge_result.get("risco", "MEDIO")

        # Evaluate handoff protocol
        handoff_result = self.evaluate_dmn(
            context,
            decision_key="surg_coord_001",
            variables={
                "handoffType": handoff_type,
                "aldereteScore": alderete_score,
                "vitalSignsStable": vital_signs_stable,
            },
            category="surgical_services",
        )

        handoff_complete = handoff_result.get("resultado", "REVISAR") == "PROSSEGUIR"

        # Check if ICU transfer needed
        icu_result = self.evaluate_dmn(
            context,
            decision_key="surg_coord_003",
            variables={
                "aldereteScore": alderete_score,
                "consciousnessLevel": consciousness_level,
                "bleedingControlled": bleeding_controlled,
            },
            category="surgical_services",
        )

        icu_required = icu_result.get("resultado", "REVISAR") == "PROSSEGUIR"

        logger.info(
            "Post-op recovery result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "alderete_score": alderete_score,
                "icu_required": icu_required,
                "handoff_complete": handoff_complete,
            },
        )

        if resultado == "BLOQUEAR" or not handoff_complete:
            return TaskResult.bpmn_error(
                error_code="SURG_RECOVERY",
                error_message=acao or "Critérios de alta SRPA não atendidos",
                variables={
                    "risco": risco,
                    "aldereteScore": alderete_score,
                    "icuRequired": icu_required,
                    "correlation_id": correlation_id,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "risco": risco,
            "aldereteScore": alderete_score,
            "icuRequired": icu_required,
            "handoffComplete": handoff_complete,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
