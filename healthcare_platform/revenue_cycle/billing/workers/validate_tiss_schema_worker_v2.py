"""
Validate TISS Schema Worker (Thin Delegation)
Purpose: Validate TISS XML against ANS schema

TOPIC: billing.validate_tiss_schema

Delegates validation to TISSValidationService.
Worker handles: input validation, DMN evaluation, delegation.

Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""

from __future__ import annotations
from typing import Optional, Union
import types
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, ProcessTaskResult,
)
from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol
from healthcare_platform.revenue_cycle.billing.services.tiss_validation_service import TISSValidationService


class ValidateTISSSchemaWorker(BaseExternalTaskWorker):
    """Valida XML TISS. Thin worker - delegates to TISSValidationService."""

    TOPIC = "billing.validate_tiss_schema"
    OPERATION_NAME = "Validar esquema TISS"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "tiss_schema_validation"
    _topic = "billing-validate-tiss-schema"
    worker_name = "ValidateTISSSchemaWorker"

    def __init__(self, tiss_client: Optional[TISSClientProtocol] = None, **kwargs):
        super().__init__(**kwargs)
        self.tiss_client = tiss_client
        self.service = TISSValidationService(tiss_client=tiss_client)

    async def execute(self, context: Union[TaskContext, types.SimpleNamespace]) -> ProcessTaskResult:
        if isinstance(context, types.SimpleNamespace):
            variables = context.variables if hasattr(context, 'variables') else {}
            context = TaskContext(
                task_id='test-task', process_instance_id='test-process',
                tenant_id=variables.get('tenant_id', variables.get('hospitalCode', 'HOSPITAL_A')),
                variables=variables, worker_id=self.TOPIC,
            )
        try:
            variables = context.variables
            tiss_xml = variables.get("tiss_xml", "")
            guide_type = variables.get("guide_type", "")
            guide_number = variables.get("guide_number", "UNKNOWN")

            if not tiss_xml or not guide_type:
                return ProcessTaskResult(success=False, error_code="TISS_VALIDATION_FAILED", error_message="tiss_xml e guide_type sao obrigatorios")
            if guide_type not in ["sp_sadt", "consultation", "admission", "extension"]:
                return ProcessTaskResult(success=False, error_code="TISS_VALIDATION_FAILED", error_message=f"Tipo de guia invalido: {guide_type}")

            validation_result = self.service.validate_schema(tiss_xml, guide_type)

            if not self.dmn_service:
                return ProcessTaskResult(success=True, variables=validation_result)

            dmn_result = self.evaluate_dmn(context, decision_key=self.DMN_COMPANION_KEY,
                variables={"guideType": guide_type, "guideNumber": guide_number,
                           "xmlLength": len(tiss_xml), "validationErrors": validation_result["schema_errors"]},
                category=self.DMN_CATEGORY)
            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            if resultado == "BLOQUEAR":
                return ProcessTaskResult(success=False, error_code="ERR_SCHEMA_INVALID", error_message=acao,
                    variables={"risco": risco, "schema_errors": validation_result["schema_errors"], "schema_valid": False})
            elif resultado == "REVISAR":
                return ProcessTaskResult(success=True, variables={"requiresReview": True, "action": acao, "risco": risco,
                    "schema_valid": False, "schema_errors": validation_result["schema_errors"]})
            else:
                return ProcessTaskResult(success=True, variables=validation_result)
        except Exception as e:
            self.logger.error(f"Schema validation failed: {e}", exc_info=True)
            return ProcessTaskResult(success=False, error_code="ERR_SCHEMA_VALIDATION_EXCEPTION", error_message=str(e))
