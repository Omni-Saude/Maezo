"""
Generate TISS XML Worker (Thin Delegation)
Purpose: Generate TISS 4.01 compliant XML from claim data

TOPIC: billing.generate_tiss_xml

Delegates XML generation to TISSGenerationService.
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
from healthcare_platform.revenue_cycle.billing.services.tiss_generation_service import TISSGenerationService


class GenerateTISSXMLWorker(BaseExternalTaskWorker):
    """Generate TISS XML. Thin worker - delegates to TISSGenerationService."""

    TOPIC = "billing.generate_tiss_xml"
    OPERATION_NAME = "Gerar XML TISS"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "tiss_xml_validation"
    _topic = "billing-generate-tiss-xml"
    worker_name = "GenerateTISSXMLWorker"

    def __init__(self, tiss_client: Optional[TISSClientProtocol] = None, **kwargs):
        super().__init__(**kwargs)
        self.tiss_client = tiss_client
        self.service = TISSGenerationService(tiss_client=tiss_client)

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
            payer_id = variables.get("payer_id")
            provider_id = variables.get("provider_id") or "PROVIDER_DEFAULT"
            guide_type = variables.get("guide_type")
            claim_data = variables.get("claim", {})

            if not payer_id:
                return ProcessTaskResult(success=False, error_code="TISS_ERROR", error_message="ID da operadora não fornecido")
            if not guide_type:
                return ProcessTaskResult(success=False, error_code="TISS_ERROR", error_message="Tipo de guia não fornecido")
            if guide_type.lower() not in ["sp_sadt", "consultation", "admission", "extension"]:
                return ProcessTaskResult(success=False, error_code="TISS_ERROR", error_message=f"Tipo de guia inválido: {guide_type}")

            if not self.dmn_service:
                result = self.service.generate_xml(claim_data, guide_type, provider_id)
                return ProcessTaskResult(success=True, variables=result)

            dmn_result = self.evaluate_dmn(context, decision_key=self.DMN_COMPANION_KEY,
                variables={"payerId": payer_id, "guideType": guide_type}, category=self.DMN_CATEGORY)
            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            if resultado == "BLOQUEAR":
                return ProcessTaskResult(success=False, error_code="TISS_ERROR", error_message=acao, variables={"risco": risco, "payerId": payer_id})
            elif resultado == "REVISAR":
                return ProcessTaskResult(success=True, variables={"requiresReview": True, "action": acao, "risco": risco, "payerId": payer_id})
            else:
                result = self.service.generate_xml(claim_data, guide_type, provider_id)
                return ProcessTaskResult(success=True, variables=result)
        except Exception as e:
            self.logger.error(f"TISS XML generation failed: {e}", exc_info=True)
            return ProcessTaskResult(success=False, error_code="TISS_ERROR", error_message=str(e))
