"""
Worker para verificação de contagem de instrumentais e compressas cirúrgicas.
CRÍTICO: Divergências na contagem SEMPRE bloqueiam o fechamento cirúrgico.

Archetype: COMPLIANCE_VALIDATION
"""
from __future__ import annotations
from typing import Any, Dict
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_COUNT")


class SurgicalCountVerificationWorker(BaseExternalTaskWorker):
    """Contagem de instrumentais e compressas. Topic: surgical.count_verification"""

    TOPIC = "surgical.count_verification"
    OPERATION_NAME = "Contagem de Instrumentais e Compressas"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        instrument_count_pre = variables.get("instrumentCountPre", 0)
        instrument_count_post = variables.get("instrumentCountPost", 0)
        sponge_count_pre = variables.get("spongeCountPre", 0)
        sponge_count_post = variables.get("spongeCountPost", 0)
        needle_count_match = variables.get("needleCountMatch", True)

        # Evaluate count verification
        count_result = self.evaluate_dmn(
            context,
            decision_key="surg_coord_007",
            variables={
                "instrumentCountPre": instrument_count_pre,
                "instrumentCountPost": instrument_count_post,
                "spongeCountPre": sponge_count_pre,
                "spongeCountPost": sponge_count_post,
                "needleCountMatch": needle_count_match,
            },
            category="surgical_services",
        )

        resultado = count_result.get("resultado", "REVISAR")
        acao = count_result.get("acao", "")
        risco = count_result.get("risco", "ALTO")

        # CRITICAL: Count mismatch ALWAYS blocks
        count_matches = (
            instrument_count_pre == instrument_count_post
            and sponge_count_pre == sponge_count_post
            and needle_count_match
        )

        if not count_matches:
            resultado = "BLOQUEAR"
            risco = "ALTO"
            acao = "Contagem divergente - rastreamento radiográfico obrigatório"

        logger.info(
            "Surgical count verification result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "risco": risco,
                "count_matches": count_matches,
                "instrument_diff": instrument_count_post - instrument_count_pre,
                "sponge_diff": sponge_count_post - sponge_count_pre,
            },
        )

        if resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_COUNT_MISMATCH",
                error_message=acao,
                variables={
                    "risco": risco,
                    "instrumentDiff": instrument_count_post - instrument_count_pre,
                    "spongeDiff": sponge_count_post - sponge_count_pre,
                    "needleCountMatch": needle_count_match,
                    "correlation_id": correlation_id,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "risco": risco,
            "countMatches": count_matches,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
