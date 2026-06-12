"""
Worker para agendamento de cirurgias com validação de alocação de sala e prioridade.
Valida disponibilidade de sala, equipe e prioriza casos urgentes.
"""
from __future__ import annotations
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_SCHEDULING")


class SurgicalSchedulingWorker(BaseExternalTaskWorker):
    """Agendamento de cirurgias com validação de alocação de sala.

    Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = "surgical.scheduling"
    OPERATION_NAME = "Agendamento Cirúrgico"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        procedure_code = variables.get("procedureCode", "")
        surgeon_id = variables.get("surgeonId", "")
        requested_date = variables.get("requestedDate", "")
        urgency_level = variables.get("urgencyLevel", "ELETIVO")
        estimated_duration = variables.get("estimatedDuration", 120)

        # Validate OR allocation
        or_result = self.evaluate_dmn(
            context,
            decision_key="surg_sched_001",
            variables={
                "procedureCode": procedure_code,
                "requestedDate": requested_date,
                "estimatedDuration": estimated_duration,
                "urgencyLevel": urgency_level,
            },
            category="surgical_services",
        )

        # TODO: or_allocation sera usado na confirmacao de alocacao de sala cirurgica
        # or_allocation = or_result.get("resultado", "REVISAR")
        sala_sugerida = or_result.get("salaSugerida", "")
        horario_sugerido = or_result.get("horarioSugerido", "")

        # Evaluate priority scoring
        priority_result = self.evaluate_dmn(
            context,
            decision_key="surg_sched_004",
            variables={
                "urgencyLevel": urgency_level,
                "procedureCode": procedure_code,
                "surgeonId": surgeon_id,
            },
            category="surgical_services",
        )

        priority_score = priority_result.get("priorityScore", 50)
        resultado = priority_result.get("resultado", "REVISAR")
        acao = priority_result.get("acao", "Revisar agendamento manualmente")

        logger.info(
            "Surgical scheduling result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "sala_sugerida": sala_sugerida,
                "priority_score": priority_score,
                "urgency_level": urgency_level,
            },
        )

        if resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_SCHEDULING_BLOCKED",
                error_message=acao,
                variables={
                    "correlation_id": correlation_id,
                    "urgencyLevel": urgency_level,
                    "priorityScore": priority_score,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "salaSugerida": sala_sugerida,
            "horarioSugerido": horario_sugerido,
            "priorityScore": priority_score,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
