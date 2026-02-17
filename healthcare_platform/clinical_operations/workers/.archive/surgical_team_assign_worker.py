"""
Worker para escalação de equipe cirúrgica baseada em complexidade do procedimento.
Valida composição da equipe, especialidades necessárias e disponibilidade.
"""
from __future__ import annotations
from typing import Any, Dict
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_TEAM_ASSIGN")


class SurgicalTeamAssignWorker(BaseExternalTaskWorker):
    """Escalação de equipe cirúrgica. Topic: surgical.team_assign"""

    TOPIC = "surgical.team_assign"
    OPERATION_NAME = "Escalação de Equipe Cirúrgica"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        procedure_complexity = variables.get("procedureComplexity", "MEDIA")
        specialty_required = variables.get("specialtyRequired", "")
        surgeon_id = variables.get("surgeonId", "")

        # Evaluate team assignment
        dmn_result = self.evaluate_dmn(
            context,
            decision_key="surg_sched_003",
            variables={
                "procedureComplexity": procedure_complexity,
                "specialtyRequired": specialty_required,
                "surgeonId": surgeon_id,
            },
            category="surgical_services",
        )

        resultado = dmn_result.get("resultado", "REVISAR")
        acao = dmn_result.get("acao", "")
        team_composition = dmn_result.get("teamComposition", {})
        required_roles = dmn_result.get("requiredRoles", [])
        min_team_size = dmn_result.get("minTeamSize", 3)

        logger.info(
            "Surgical team assignment result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "procedure_complexity": procedure_complexity,
                "min_team_size": min_team_size,
                "required_roles_count": len(required_roles),
            },
        )

        if resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_TEAM_UNAVAILABLE",
                error_message=acao,
                variables={
                    "correlation_id": correlation_id,
                    "procedureComplexity": procedure_complexity,
                    "requiredRoles": required_roles,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "teamComposition": team_composition,
            "requiredRoles": required_roles,
            "minTeamSize": min_team_size,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
