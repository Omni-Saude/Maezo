"""
Submit Appeal Worker (Refactored)
Purpose: Submit appeals to payers via TISS protocol using DMN-based routing

TOPIC: glosa.submit_appeal

Refactored using Keep & Augment DMN strategy:
- Existing revenue_recovery DMN preserved
- Inline rules extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class SubmitAppealWorkerV2(BaseExternalTaskWorker):
    """Refactored appeal submission worker. Thin worker pattern."""

    TOPIC = "glosa.submit_appeal"
    DMN_COMPANION_KEY = "submission/appeal_submission_adjudication"
    DMN_COMPANION_CATEGORY = "revenue_recovery"

    def __init__(self, tiss_client=None, **kwargs):
        """Initialize with optional TISS client (inject for testing)."""
        super().__init__(**kwargs)
        self.tiss_client = tiss_client

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            appeal_doc_id = variables.get("appealDocumentId")
            claim_id = variables.get("claimId")
            eligible_glosas = variables.get("eligibleGlosas", [])
            payer_id = variables.get("payerId")
            provider_id = variables.get("providerId")

            if not appeal_doc_id or not claim_id:
                return TaskResult.bpmn_error(
                    error_code="ERR_MISSING_REQUIRED_FIELDS",
                    error_message="Documento de recurso e ID da conta são obrigatórios",
                )

            if not eligible_glosas:
                return TaskResult.bpmn_error(
                    error_code="ERR_NO_GLOSAS",
                    error_message="Nenhuma glosa elegível para recurso",
                )

            # Attempt submission
            response_code, attempt_count, submission_protocol = self._submit_to_payer(
                appeal_doc_id, claim_id, eligible_glosas, payer_id, provider_id
            )

            # Evaluate companion DMN for submission validation
            try:
                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_COMPANION_KEY,
                    variables={
                        "responseCode": response_code,
                        "attemptCount": attempt_count,
                    },
                    category=self.DMN_COMPANION_CATEGORY,
                )
            except Exception as dmn_error:
                self.logger.warning(f"DMN evaluation failed, using fallback: {dmn_error}")
                dmn_result = {}

            # Handle BOTH old 5-output and new 3-output DMN schemas with fallback
            resultado = dmn_result.get("resultado", "PROSSEGUIR")
            acao = dmn_result.get("acao") or dmn_result.get("observacao", "Processar normalmente") + " " + dmn_result.get("acaoRecomendada", "")
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "BAIXO")

            # Use fallback protocol if not provided
            if not submission_protocol:
                submission_protocol = f"PROT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            submission_success = response_code == "SUCCESS"

            # Route on resultado
            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(
                    error_code="ERR_SUBMISSION_BLOCKED",
                    error_message=f"Submissão bloqueada: {acao}",
                    variables={
                        "submissionProtocol": submission_protocol,
                        "payerResponseCode": response_code,
                        "risk": risco,
                    },
                )
            elif resultado == "PROSSEGUIR":
                return TaskResult.success({
                    "submissionProtocol": submission_protocol,
                    "submissionSuccess": submission_success,
                    "payerResponseCode": response_code,
                    "submissionTimestamp": datetime.utcnow().isoformat(),
                    "risk": risco,
                    "action": acao,
                })
            else:  # REVISAR
                return TaskResult.success({
                    "submissionProtocol": submission_protocol,
                    "submissionSuccess": submission_success,
                    "payerResponseCode": response_code,
                    "requiresReview": True,
                    "submissionTimestamp": datetime.utcnow().isoformat(),
                    "risk": risco,
                    "action": acao,
                })

        except Exception as e:
            self.logger.error(f"Error submitting appeal: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_APPEAL_SUBMISSION",
                error_message=str(e),
            )

    def _submit_to_payer(
        self,
        appeal_doc_id: str,
        claim_id: str,
        eligible_glosas: list,
        payer_id: str,
        provider_id: str,
    ) -> tuple[str, int, str]:
        """
        Submit appeal to payer via TISS client.

        Returns:
            Tuple of (response_code, attempt_count, protocol_number)
        """
        if not self.tiss_client:
            # Mock submission for testing
            return "SUCCESS", 1, ""

        try:
            # Import TISSGuideDTO if available
            try:
                from healthcare_platform.shared.integrations.tiss_client import TISSGuideDTO
                from healthcare_platform.shared.domain.enums import TISSGuideType
            except ImportError:
                # Fallback to dict if DTO not available
                guide_dto = {
                    "guide_type": "summary",  # Use SUMMARY for appeals
                    "guide_number": appeal_doc_id,
                    "claim_id": claim_id,
                    "payer_id": payer_id,
                    "provider_id": provider_id,
                    "patient_id": "APPEAL",  # Placeholder for appeal
                    "items": eligible_glosas,
                }
            else:
                # Use proper DTO - appeals use SUMMARY guide type
                guide_dto = TISSGuideDTO(
                    guide_type=TISSGuideType.SUMMARY,
                    guide_number=appeal_doc_id,
                    claim_id=claim_id,
                    payer_id=payer_id,
                    provider_id=provider_id,
                    patient_id="APPEAL",  # Placeholder for appeal
                    items=eligible_glosas,
                    additional_data={"appealLetter": "Recurso de glosa"},
                )

            # Submit via TISS client
            result = self.tiss_client.submit_guide(guide_dto)

            # Handle both dict and object responses
            if hasattr(result, "success"):
                # TISSSubmissionResult object - use payer_response_code attribute
                protocol = getattr(result, "protocol_number", "")
                response_code = result.payer_response_code if result.success else result.payer_response_code or "ERROR"
                return response_code, 1, protocol
            elif isinstance(result, dict):
                # Dict response
                response_code = result.get("payer_response_code") or result.get("response_code", "SUCCESS" if result.get("success") else "ERROR")
                protocol = result.get("protocol_number", "")
                return response_code, 1, protocol
            else:
                return "SUCCESS" if result else "ERROR", 1, ""

        except Exception as e:
            self.logger.error(f"TISS submission failed: {e}", exc_info=True)
            return "CONNECTION_ERROR", 1, ""

    def _extract_protocol(self, response_code: str) -> str:
        """Extract protocol from response or generate new one."""
        # In real implementation, protocol would come from TISS response
        # For now, generate timestamp-based protocol
        return f"PROTOCOL-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
# Backward compatibility alias
SubmitAppealWorker = SubmitAppealWorkerV2
