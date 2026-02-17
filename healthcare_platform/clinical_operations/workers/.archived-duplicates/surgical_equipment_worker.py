"""
Worker para rastreamento e verificação de equipamentos cirúrgicos.
Valida disponibilidade, esterilização e calibração de equipamentos necessários.

Archetype: COMPLIANCE_VALIDATION
"""
from __future__ import annotations
from typing import Any, Dict
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_EQUIPMENT")


class SurgicalEquipmentWorker(BaseExternalTaskWorker):
    """Rastreamento de equipamentos. Topic: surgical.equipment_check"""

    TOPIC = "surgical.equipment_check"
    OPERATION_NAME = "Rastreamento de Equipamentos"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        procedure_type = variables.get("procedureType", "")
        equipment_list = variables.get("equipmentList", [])
        sterilization_status = variables.get("sterilizationStatus", "PENDING")
        calibration_current = variables.get("calibrationCurrent", False)

        # Evaluate equipment matching
        equipment_result = self.evaluate_dmn(
            context,
            decision_key="surg_sched_002",
            variables={
                "procedureType": procedure_type,
                "equipmentList": equipment_list,
                "sterilizationStatus": sterilization_status,
                "calibrationCurrent": calibration_current,
            },
            category="surgical_services",
        )

        resultado = equipment_result.get("resultado", "REVISAR")
        acao = equipment_result.get("acao", "")
        risco = equipment_result.get("risco", "MEDIO")
        missing_equipment = equipment_result.get("missingEquipment", [])

        # Check fire risk (electrical equipment validation)
        fire_risk_result = self.evaluate_dmn(
            context,
            decision_key="surg_safety_010",
            variables={
                "equipmentList": equipment_list,
                "calibrationCurrent": calibration_current,
            },
            category="surgical_services",
        )

        fire_risk = fire_risk_result.get("risco", "BAIXO")

        logger.info(
            "Surgical equipment check result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "fire_risk": fire_risk,
                "missing_count": len(missing_equipment),
            },
        )

        if resultado == "BLOQUEAR" or fire_risk == "ALTO":
            return TaskResult.bpmn_error(
                error_code="SURG_EQUIPMENT",
                error_message=acao or f"Equipamento bloqueado - risco de incêndio: {fire_risk}",
                variables={
                    "risco": risco,
                    "fireRisk": fire_risk,
                    "missingEquipment": missing_equipment,
                    "correlation_id": correlation_id,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "risco": risco,
            "fireRisk": fire_risk,
            "missingEquipment": missing_equipment,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
