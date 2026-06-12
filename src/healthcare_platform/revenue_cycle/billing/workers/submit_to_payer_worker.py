"""
Submit to Payer Worker (Thin Delegation)
Purpose: Submit TISS XML guide to payer via TISS client

TOPIC: billing.submit_to_payer

Delegates submission to ClaimSubmissionService.
Worker handles: input validation, DMN evaluation, delegation.

Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""

from __future__ import annotations
from typing import Optional, Union
import types
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol
from healthcare_platform.revenue_cycle.billing.services.claim_submission_service import ClaimSubmissionService


class SubmitToPayerWorker(BaseExternalTaskWorker):
    """Submete guia TISS a operadora. Thin worker - delegates to ClaimSubmissionService."""

    TOPIC = "billing.submit_to_payer"
    OPERATION_NAME = "Submeter guia TISS à operadora"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "submission_validation"

    def __init__(self, tiss_client: Optional[TISSClientProtocol] = None, **kwargs):
        super().__init__(**kwargs)
        self.tiss_client = tiss_client
        self.service = ClaimSubmissionService(tiss_client=tiss_client)

    async def execute(self, context: Union[TaskContext, types.SimpleNamespace]) -> TaskResult:
        if isinstance(context, types.SimpleNamespace):
            variables = context.variables if hasattr(context, 'variables') else {}
            context = TaskContext(task_id='test-task', process_instance_id='test-process',
                tenant_id=variables.get('tenant_id', variables.get('hospitalCode', 'HOSPITAL_A')),
                variables=variables, worker_id=self.TOPIC)
        try:
            variables = context.variables
            tissXml = variables.get("tissXml", variables.get("tiss_xml", ""))
            payer = variables.get("payer", variables.get("payer_id", ""))
            claim_id = variables.get("claim_id")
            # TODO: tiss_xml era alias de tissXml para padronizacao de nomenclatura
            # tiss_xml = tissXml
            # TODO: payer_id era alias de payer para padronizacao de nomenclatura
            # payer_id = payer

            if not tissXml:
                return TaskResult.bpmn_error(error_code="MISSING_TISS_XML", error_message="XML TISS não fornecido")
            if not payer:
                return TaskResult.bpmn_error(error_code="MISSING_PAYER_ID", error_message="ID da operadora não fornecido")

            dmn_result = self.evaluate_dmn(context, decision_key=self.DMN_COMPANION_KEY,
                variables={"tissXml": tissXml[:500], "payerId": payer}, category=self.DMN_CATEGORY)
            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(error_code="ERR_SUBMISSION_BLOCKED", error_message=acao, variables={"risco": risco})
            if resultado == "REVISAR":
                return TaskResult.success({"requiresReview": True, "action": acao, "risco": risco, "submission_success": False})

            result = await self.service.submit(tissXml, payer, claim_id or "")
            if result.get("submission_success"):
                return TaskResult.success({
                    **result,
                    "submissionId": result.get("submission_id", ""),
                    "submissionStatus": result.get("status", "submitted"),
                })
            if result.get("error"):
                return TaskResult.bpmn_error(error_code="ERR_SUBMISSION_FAILED", error_message=result["error"])
            return TaskResult.bpmn_error(error_code="ERR_SUBMISSION_FAILED",
                error_message=result.get("payer_response_message", "Falha na submissão"),
                variables={"submission_success": False, "payer_response_code": result.get("payer_response_code")})
        except Exception as e:
            self.logger.error(f"Submission failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="ERR_SUBMISSION_FAILURE", error_message=str(e))
