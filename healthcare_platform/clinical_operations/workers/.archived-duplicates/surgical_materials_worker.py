"""
Worker para preparação e validação de materiais cirúrgicos.
Verifica disponibilidade de equipamentos, instrumentais e materiais especiais.

Archetype: COMPLIANCE_VALIDATION
"""
from __future__ import annotations
from typing import Any, Dict
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__, worker="SURGICAL_MATERIALS")


class SurgicalMaterialsWorker(BaseExternalTaskWorker):
    """Preparação de materiais cirúrgicos. Topic: surgical.materials"""

    TOPIC = "surgical.materials"
    OPERATION_NAME = "Preparação de Materiais Cirúrgicos"

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        correlation_id = context.process_instance_id

        # Extract inputs
        procedure_type = variables.get("procedureType", "")
        preference_card_id = variables.get("preferenceCardId", "")
        special_equipment = variables.get("specialEquipment", [])

        # Evaluate equipment matching
        equipment_result = self.evaluate_dmn(
            context,
            decision_key="surg_sched_002",
            variables={
                "procedureType": procedure_type,
                "preferenceCardId": preference_card_id,
                "specialEquipment": special_equipment,
            },
            category="surgical_services",
        )

        equipment_available = equipment_result.get("resultado", "REVISAR")
        equipment_list = equipment_result.get("equipmentList", [])

        # Evaluate material validation
        material_result = self.evaluate_dmn(
            context,
            decision_key="surg_bill_004",
            variables={
                "procedureType": procedure_type,
                "equipmentList": equipment_list,
            },
            category="surgical_services",
        )

        resultado = material_result.get("resultado", "REVISAR")
        acao = material_result.get("acao", "")
        missing_items = material_result.get("missingItems", [])
        sterility_confirmed = material_result.get("sterilityConfirmed", False)

        logger.info(
            "Surgical materials validation result",
            extra={
                "correlation_id": correlation_id,
                "resultado": resultado,
                "equipment_count": len(equipment_list),
                "missing_items_count": len(missing_items),
                "sterility_confirmed": sterility_confirmed,
            },
        )

        if resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="SURG_MATERIALS_BLOCKED",
                error_message=acao,
                variables={
                    "correlation_id": correlation_id,
                    "missingItems": missing_items,
                    "sterilityConfirmed": sterility_confirmed,
                },
            )

        return TaskResult.success({
            "resultado": resultado,
            "acao": acao,
            "equipmentList": equipment_list,
            "missingItems": missing_items,
            "sterilityConfirmed": sterility_confirmed,
            "requiresReview": resultado == "REVISAR",
            "correlation_id": correlation_id,
        })
