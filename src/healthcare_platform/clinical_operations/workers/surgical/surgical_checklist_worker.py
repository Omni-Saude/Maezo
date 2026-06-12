"""
Worker para validação do checklist de segurança cirúrgica WHO Time-Out.
Verifica confirmação de equipe, identidade do paciente, procedimento e administração de antibióticos.
"""
from __future__ import annotations
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_CHECKLIST")


class SurgicalChecklistWorker(BaseExternalTaskWorker):
    """Checklist WHO Time-Out. Topic: surgical.checklist.

    Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = "surgical.checklist"
    OPERATION_NAME = "Checklist WHO Time-Out"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        team_members_confirmed = variables.get("teamMembersConfirmed", False)
        patient_identity_reconfirmed = variables.get("patientIdentityReconfirmed", False)
        procedure_confirmed = variables.get("procedureConfirmed", False)
        site_confirmed = variables.get("siteConfirmed", False)
        antibiotic_given = variables.get("antibioticGiven", False)

        # Evaluate WHO time-out checklist
        checklist_result = self.evaluate_dmn(
            context,
            decision_key="surg_safety_002",
            variables={
                "teamMembersConfirmed": team_members_confirmed,
                "patientIdentityReconfirmed": patient_identity_reconfirmed,
                "procedureConfirmed": procedure_confirmed,
                "siteConfirmed": site_confirmed,
                "antibioticGiven": antibiotic_given,
            },
            category="surgical_services",
        )

        resultado = checklist_result.get("resultado", "REVISAR")
        acao = checklist_result.get("acao", "")
        risco = checklist_result.get("risco", "MEDIO")

        # Validate timeout rules
        timeout_result = self.evaluate_dmn(
            context,
            decision_key="surg_safety_012",
            variables={
                "timeoutCompleted": resultado == "PROSSEGUIR",
                "teamMembersConfirmed": team_members_confirmed,
            },
            category="surgical_services",
        )

        timeout_status = timeout_result.get("resultado", "REVISAR")

        logger.info(
            "Surgical checklist result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "risco": risco,
                "timeout_status": timeout_status,
            },
        )

        if resultado == "BLOQUEAR" or timeout_status == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_SAFETY",
                error_message=acao or "Checklist incompleto - procedimento bloqueado",
                variables={
                    "risco": risco,
                    "correlation_id": correlation_id,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "risco": risco,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
