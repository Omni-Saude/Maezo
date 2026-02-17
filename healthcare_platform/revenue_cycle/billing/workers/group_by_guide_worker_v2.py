"""
Group By Guide Worker (Refactored)
Purpose: Group encounter procedures by TISS guide type

Archetype: OPERATIONAL_ROUTING

TOPIC: billing.group_by_guide

Refactored using Keep & Augment DMN strategy:
- Business rules extracted to DMN: guide_grouping_validation.dmn
- Worker focuses on: DMN evaluation + procedure grouping
- No inline business rules

Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)

class GroupByGuideWorker(BaseExternalTaskWorker):
    """Group procedures by TISS guide. Thin worker - all rules delegated to DMN."""

    TOPIC = "billing.group_by_guide"
    OPERATION_NAME = "Agrupar procedimentos por guia TISS"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "guide_grouping_validation"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            encounter_id = variables.get("encounter_id")
            procedures = variables.get("procedures", [])

            # Input validation
            if not encounter_id:
                return TaskResult.bpmn_error(
                    error_code="MISSING_ENCOUNTER_ID",
                    error_message="ID do atendimento não fornecido"
                )

            if not isinstance(procedures, list):
                return TaskResult.bpmn_error(
                    error_code="INVALID_PROCEDURES_FORMAT",
                    error_message="Procedimentos devem ser uma lista"
                )

            # Validate procedures (only if there are any)
            for idx, proc in enumerate(procedures):
                if not isinstance(proc, dict):
                    return TaskResult.bpmn_error(
                        error_code="INVALID_PROCEDURE_FORMAT",
                        error_message=f"Procedimento {idx} não é um dicionário"
                    )
                if "code" not in proc:
                    return TaskResult.bpmn_error(
                        error_code="MISSING_PROCEDURE_CODE",
                        error_message=f"Procedimento {idx} sem código"
                    )
                if "type" not in proc:
                    return TaskResult.bpmn_error(
                        error_code="MISSING_PROCEDURE_TYPE",
                        error_message=f"Procedimento {idx} sem tipo"
                    )

            # Call DMN - it will decide how to handle empty procedures
            dmn_result = self.evaluate_dmn(
                context,
                decision_key=self.DMN_COMPANION_KEY,
                variables={"encounterId": encounter_id, "procedureCount": len(procedures)},
                category=self.DMN_CATEGORY,
            )

            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(error_code="ERR_GUIDE_GROUPING", error_message=acao, variables={"risco": risco, "encounterId": encounter_id})
            elif resultado == "REVISAR":
                return TaskResult.success({"requiresReview": True, "action": acao, "risco": risco, "encounterId": encounter_id})
            else:
                grouped = self._group_procedures(procedures)
                return TaskResult.success({
                    "grouped_guides": grouped,
                    "guide_count": len(grouped),
                    "total_procedures": len(procedures),
                    "encounter_id": encounter_id
                })

        except Exception as e:
            self.logger.error(f"Guide grouping failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="ERR_GROUPING_PROCESSING", error_message=str(e))

    def _group_procedures(self, procedures):
        """Group procedures by TISS guide type."""
        from healthcare_platform.shared.domain.enums import TISSGuideType

        grouped = {}
        for proc in procedures:
            proc_type = proc.get("type", "").lower()
            code = proc.get("code", "")

            # Map procedure type to TISS guide type
            guide_type = self._map_to_guide_type(proc_type, code)

            if guide_type not in grouped:
                grouped[guide_type] = []

            # Enrich procedure with coded value
            enriched_proc = proc.copy()
            enriched_proc["coded_value"] = {
                "code": code,
                "system": "http://www.ans.gov.br/tiss/terminologia",
                "display": proc.get("description", "")
            }

            grouped[guide_type].append(enriched_proc)

        return grouped

    def _map_to_guide_type(self, proc_type: str, code: str) -> str:
        """Map procedure type and code to TISS guide type."""
        from healthcare_platform.shared.domain.enums import TISSGuideType

        # Map by procedure type
        type_mapping = {
            "consultation": TISSGuideType.CONSULTATION.value,
            "consulta": TISSGuideType.CONSULTATION.value,
            "ambulatory": TISSGuideType.CONSULTATION.value,
            "exam": TISSGuideType.SP_SADT.value,
            "exame": TISSGuideType.SP_SADT.value,
            "lab": TISSGuideType.SP_SADT.value,
            "surgery": TISSGuideType.SP_SADT.value,
            "admission": TISSGuideType.ADMISSION.value,
            "internacao": TISSGuideType.ADMISSION.value,
            "extension": TISSGuideType.EXTENSION.value,
            "extensao": TISSGuideType.EXTENSION.value,
            "honorarios": TISSGuideType.HONORARIOS.value,
            "summary": TISSGuideType.SUMMARY.value,
        }

        if proc_type in type_mapping:
            return type_mapping[proc_type]

        # Fall back to code-based classification
        if code.startswith("1"):
            return TISSGuideType.CONSULTATION.value
        elif code.startswith(("2", "3", "4")):
            return TISSGuideType.SP_SADT.value
        elif code.startswith("8"):
            return TISSGuideType.ADMISSION.value
        else:
            return TISSGuideType.SP_SADT.value  # Default
