"""
Worker para avaliação anestésica pré-operatória.
Valida classificação ASA, via aérea, alergias e tipo de anestesia proposta.
"""
from __future__ import annotations
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_ANESTHESIA_EVAL")


class SurgicalAnesthesiaEvalWorker(BaseExternalTaskWorker):
    """Avaliação anestésica pré-operatória.

    Archetype: CLINICAL_ALERT
    """

    TOPIC = "surgical.anesthesia_eval"
    OPERATION_NAME = "Avaliação Anestésica"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        asa_class = variables.get("asaClass", "ASA_III")
        mallampatti_score = variables.get("mallampattiScore", 2)
        allergy_history = variables.get("allergyHistory", [])
        airway_difficulty = variables.get("airwayDifficulty", False)
        anesthesia_type = variables.get("anesthesiaType", "GERAL")

        # Evaluate anesthesia risk
        risk_result = self.evaluate_dmn(
            context,
            decision_key="surg_safety_006",
            variables={
                "asaClass": asa_class,
                "mallampattiScore": mallampatti_score,
                "airwayDifficulty": airway_difficulty,
                "anesthesiaType": anesthesia_type,
            },
            category="surgical_services",
        )

        risk_level = risk_result.get("resultado", "REVISAR")
        risk_score = risk_result.get("riskScore", 50)

        # Evaluate allergy alerts
        allergy_result = self.evaluate_dmn(
            context,
            decision_key="surg_safety_008",
            variables={
                "allergyHistory": allergy_history,
                "anesthesiaType": anesthesia_type,
            },
            category="surgical_services",
        )

        resultado = allergy_result.get("resultado", "REVISAR")
        acao = allergy_result.get("acao", "")
        contraindications = allergy_result.get("contraindications", [])
        alternative_agents = allergy_result.get("alternativeAgents", [])
        requires_specialist = allergy_result.get("requiresSpecialist", False)

        logger.info(
            "Surgical anesthesia evaluation result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "asa_class": asa_class,
                "risk_score": risk_score,
                "contraindications_count": len(contraindications),
                "requires_specialist": requires_specialist,
            },
        )

        if resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_ANESTHESIA_BLOCKED",
                error_message=acao,
                variables={
                    "correlation_id": correlation_id,
                    "riskScore": risk_score,
                    "contraindications": contraindications,
                    "requiresSpecialist": requires_specialist,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "riskLevel": risk_level,
            "riskScore": risk_score,
            "contraindications": contraindications,
            "alternativeAgents": alternative_agents,
            "requiresSpecialist": requires_specialist,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
