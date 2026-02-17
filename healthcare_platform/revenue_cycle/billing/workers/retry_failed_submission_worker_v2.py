"""Retry Failed Submission Worker (Thin Delegation)
Purpose: Retry failed submissions with exponential backoff
TOPIC: billing.retry_failed_submission
Delegates retry logic to ClaimSubmissionService.
Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""
from __future__ import annotations
from typing import Optional, Union
import types
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, ProcessTaskResult
from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol
from healthcare_platform.revenue_cycle.billing.services.claim_submission_service import ClaimSubmissionService


class RetryFailedSubmissionWorker(BaseExternalTaskWorker):
    """Retenta submissoes falhadas. Thin worker - delegates to ClaimSubmissionService."""
    TOPIC = "billing.retry_failed_submission"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "retry_policy"

    def __init__(self, tiss_client: Optional[TISSClientProtocol] = None, **kwargs):
        super().__init__(**kwargs)
        self.service = ClaimSubmissionService(tiss_client=tiss_client)

    async def execute(self, context: Union[TaskContext, types.SimpleNamespace]) -> ProcessTaskResult:
        if isinstance(context, types.SimpleNamespace):
            variables = context.variables if hasattr(context, 'variables') else {}
            context = TaskContext(task_id='test-task', process_instance_id='test-process',
                tenant_id=variables.get('tenant_id', variables.get('hospitalCode', 'HOSPITAL_A')),
                variables=variables, worker_id=self.TOPIC)
        try:
            variables = context.variables
            claim_id, tiss_xml, payer_id = variables.get("claim_id"), variables.get("tiss_xml"), variables.get("payer_id")
            attempt_number, max_attempts = variables.get("attempt_number", 1), variables.get("max_attempts", 5)
            last_error = variables.get("last_error", "")

            if not claim_id:
                return ProcessTaskResult(success=False, error_code="MISSING_CLAIM_ID", error_message="ID da fatura não fornecido")
            if not tiss_xml:
                return ProcessTaskResult(success=False, error_code="MISSING_TISS_XML", error_message="XML TISS não fornecido")
            if not payer_id:
                return ProcessTaskResult(success=False, error_code="MISSING_PAYER_ID", error_message="ID da operadora não fornecido")

            dmn_result = self.evaluate_dmn(context, decision_key=self.DMN_COMPANION_KEY,
                variables={"attemptNumber": attempt_number, "maxAttempts": max_attempts, "lastError": last_error},
                category=self.DMN_CATEGORY)
            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            if resultado == "BLOQUEAR":
                return ProcessTaskResult(success=False, error_code="ERR_MAX_RETRY_REACHED", error_message=acao,
                    variables={"risco": risco, "max_attempts_reached": True, "retry_success": False})
            if resultado == "REVISAR":
                return ProcessTaskResult(success=True, variables={"requiresReview": True, "action": acao, "risco": risco, "retry_success": False})
            result = await self.service.retry_submission(tiss_xml, payer_id, claim_id, attempt_number, max_attempts)
            return ProcessTaskResult(success=True, variables=result)
        except Exception as e:
            self.logger.error(f"Retry failed: {e}", exc_info=True)
            return ProcessTaskResult(success=False, error_code="ERR_RETRY_FAILURE", error_message=str(e))
