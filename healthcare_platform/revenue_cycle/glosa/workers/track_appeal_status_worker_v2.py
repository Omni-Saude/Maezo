"""
Track Appeal Status Worker (Refactored)
Purpose: Monitor appeal status with payer using DMN-based tracking rules

TOPIC: glosa.track_appeal_status

Refactored using Keep & Augment DMN strategy:
- Existing revenue_recovery DMN preserved
- Inline rules extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class TrackAppealStatusWorkerV2(BaseExternalTaskWorker):
    """Refactored appeal status tracking worker. Thin worker pattern."""

    TOPIC = "glosa.track_appeal_status"
    DMN_COMPANION_KEY = "tracking/appeal_tracking_adjudication"
    DMN_COMPANION_CATEGORY = "revenue_recovery"

    def __init__(self, tiss_client=None, **kwargs):
        """Initialize with optional TISS client (inject for testing)."""
        super().__init__(**kwargs)
        self.tiss_client = tiss_client

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            submission_protocol = variables.get("submissionProtocol")
            claim_id = variables.get("claimId")
            submission_timestamp = variables.get("submissionTimestamp")

            if not submission_protocol:
                return TaskResult.bpmn_error(
                    error_code="ERR_MISSING_PROTOCOL",
                    error_message="Protocolo de envio é obrigatório",
                )

            # Calculate elapsed days
            elapsed_days = self._calculate_elapsed_days(submission_timestamp)

            # Check status via TISS client
            payer_response = self._check_payer_status(submission_protocol)
            payer_status_code = payer_response.get("statusCode", "UNKNOWN") if isinstance(payer_response, dict) else payer_response

            # Evaluate companion DMN for tracking validation
            try:
                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_COMPANION_KEY,
                    variables={
                        "payerStatusCode": payer_status_code,
                        "elapsedDays": elapsed_days,
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

            # Map payer code to appeal status
            appeal_status = self._map_status_code(payer_status_code)
            follow_up_required = elapsed_days > 15 or payer_status_code == "PENDING_INFO"
            status_message = self._generate_status_message(appeal_status, elapsed_days)

            # Route on resultado
            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(
                    error_code="ERR_TRACKING_BLOCKED",
                    error_message=f"Rastreamento bloqueado: {acao}",
                    variables={
                        "appealStatus": appeal_status,
                        "elapsedDays": elapsed_days,
                        "risk": risco,
                    },
                )
            elif resultado == "PROSSEGUIR":
                return TaskResult.success({
                    "appealStatus": appeal_status,
                    "followUpRequired": follow_up_required,
                    "statusMessage": status_message,
                    "elapsedDays": elapsed_days,
                    "payerStatusCode": payer_status_code,
                    "payerResponse": payer_response if isinstance(payer_response, dict) else {"statusCode": payer_status_code},
                    "risk": risco,
                    "action": acao,
                })
            else:  # REVISAR
                return TaskResult.success({
                    "appealStatus": appeal_status,
                    "followUpRequired": True,
                    "statusMessage": status_message,
                    "elapsedDays": elapsed_days,
                    "payerStatusCode": payer_status_code,
                    "payerResponse": payer_response if isinstance(payer_response, dict) else {"statusCode": payer_status_code},
                    "requiresReview": True,
                    "risk": risco,
                    "action": acao,
                })

        except Exception as e:
            self.logger.error(f"Error tracking appeal status: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_APPEAL_TRACKING",
                error_message=str(e),
            )

    def _calculate_elapsed_days(self, submission_timestamp: str) -> int:
        """Calculate days elapsed since submission."""
        try:
            submission_dt = datetime.fromisoformat(submission_timestamp.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            delta = now_dt - submission_dt
            return delta.days
        except (ValueError, AttributeError):
            self.logger.warning("Invalid submission timestamp, using 0 days")
            return 0

    def _check_payer_status(self, submission_protocol: str):
        """Check status via TISS client. Returns dict or string."""
        if not self.tiss_client:
            # Mock status for testing
            return {"statusCode": "IN_ANALYSIS", "statusMessage": "Em análise"}

        try:
            # Appeals use SUMMARY guide type in TISS
            from healthcare_platform.shared.domain.enums import TISSGuideType
            status_response = self.tiss_client.check_submission_status(
                protocol_number=submission_protocol,
                guide_type=TISSGuideType.SUMMARY,
            )
            return status_response  # Return full response dict
        except Exception as e:
            self.logger.error(f"TISS status check failed: {e}", exc_info=True)
            return {"statusCode": "UNKNOWN", "statusMessage": str(e)}

    def _map_status_code(self, payer_code: str) -> str:
        """Map payer response code to appeal status."""
        status_mapping = {
            "RECEIVED": "PENDING",
            "IN_ANALYSIS": "IN_REVIEW",
            "APPROVED": "APPROVED",
            "PARTIALLY_APPROVED": "PARTIALLY_APPROVED",
            "DENIED": "DENIED",
            "REJECTED": "DENIED",
            "PENDING_INFO": "IN_REVIEW",
        }
        # Unknown codes map to UNKNOWN status
        return status_mapping.get(payer_code, "UNKNOWN")

    def _generate_status_message(self, appeal_status: str, elapsed_days: int) -> str:
        """Generate user-friendly status message in Portuguese.
        Fallback only - primary logic in companion DMN (appeal_tracking_adjudication).
        """
        messages = {
            "APPROVED": "Recurso aprovado pela operadora. Glosas revertidas.",
            "PARTIALLY_APPROVED": "Recurso parcialmente aprovado. Verificar itens aceitos.",
            "DENIED": "Recurso negado pela operadora. Avaliar próximas ações.",
            "IN_REVIEW": f"Recurso em análise pela operadora ({elapsed_days} dias).",
            "PENDING": f"Recurso pendente de resposta ({elapsed_days} dias)."
                      + (" Prazo excedido, acompanhamento necessário." if elapsed_days > 15 else ""),
            "UNKNOWN": "Status desconhecido - verificar com a operadora.",
        }

        base_message = messages.get(appeal_status, "Status desconhecido - verificar com a operadora.")

        return base_message
# Backward compatibility alias
TrackAppealStatusWorker = TrackAppealStatusWorkerV2
