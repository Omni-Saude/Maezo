"""
Worker para manejo e rastreamento de espécimes cirúrgicos.
Valida rotulagem, cadeia de custódia e envio para anatomia patológica.

Archetype: DATA_ENRICHMENT
"""
from __future__ import annotations
from typing import Any, Dict
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_SPECIMEN")


class SurgicalSpecimenWorker(BaseExternalTaskWorker):
    """Manejo de espécime cirúrgico. Topic: surgical.specimen_tracking"""

    TOPIC = "surgical.specimen_tracking"
    OPERATION_NAME = "Manejo de Espécime Cirúrgico"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        specimen_type = variables.get("specimenType", "")
        labeling_complete = variables.get("labelingComplete", False)
        chain_of_custody = variables.get("chainOfCustody", False)
        pathology_order_placed = variables.get("pathologyOrderPlaced", False)

        # Evaluate specimen tracking
        specimen_result = self.evaluate_dmn(
            context,
            decision_key="surg_coord_006",
            variables={
                "specimenType": specimen_type,
                "labelingComplete": labeling_complete,
                "chainOfCustody": chain_of_custody,
                "pathologyOrderPlaced": pathology_order_placed,
            },
            category="surgical_services",
        )

        resultado = specimen_result.get("resultado", "REVISAR")
        acao = specimen_result.get("acao", "")
        risco = specimen_result.get("risco", "MEDIO")
        tracking_id = specimen_result.get("trackingId", "")

        logger.info(
            "Surgical specimen tracking result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "specimen_type": specimen_type,
                "tracking_id": tracking_id,
            },
        )

        if resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_SPECIMEN",
                error_message=acao,
                variables={
                    "risco": risco,
                    "specimenType": specimen_type,
                    "correlation_id": correlation_id,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "risco": risco,
            "trackingId": tracking_id,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
