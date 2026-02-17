"""
Worker para monitoramento e otimização de tempo de turnover da sala cirúrgica.
Rastreia tempo entre cirurgias e sugere melhorias para maximizar eficiência da sala.
"""
from __future__ import annotations
from typing import Any, Dict
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_OR_TURNOVER")


class SurgicalOrTurnoverWorker(BaseExternalTaskWorker):
    """Monitoramento de tempo de sala. Topic: surgical.or_turnover

    Archetype: CLINICAL_SCORE
    """

    TOPIC = "surgical.or_turnover"
    OPERATION_NAME = "Monitoramento de Tempo de Sala"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        previous_case_complexity = variables.get("previousCaseComplexity", "MEDIO")
        cleaning_level = variables.get("cleaningLevel", "STANDARD")
        next_case_setup_needs = variables.get("nextCaseSetupNeeds", "STANDARD")
        turnaround_time_minutes = variables.get("turnaroundTimeMinutes", 30)

        # Evaluate OR turnover optimization
        turnover_result = self.evaluate_dmn(
            context,
            decision_key="surg_coord_005",
            variables={
                "previousCaseComplexity": previous_case_complexity,
                "cleaningLevel": cleaning_level,
                "nextCaseSetupNeeds": next_case_setup_needs,
                "turnaroundTimeMinutes": turnaround_time_minutes,
            },
            category="surgical_services",
        )

        resultado = turnover_result.get("resultado", "REVISAR")
        acao = turnover_result.get("acao", "")
        risco = turnover_result.get("risco", "MEDIO")
        expected_time = turnover_result.get("expectedTime", 30)
        optimization_suggestions = turnover_result.get("suggestions", [])

        logger.info(
            "OR turnover result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "turnaround_time": turnaround_time_minutes,
                "expected_time": expected_time,
            },
        )

        if resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_OR_TURNOVER",
                error_message=acao,
                variables={
                    "risco": risco,
                    "expectedTime": expected_time,
                    "correlation_id": correlation_id,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "risco": risco,
            "expectedTime": expected_time,
            "optimizationSuggestions": optimization_suggestions,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
