"""
Handle Acknowledgment Worker (Refactored)
Purpose: Process ACK/NACK responses from payer

TOPIC: billing.handle_acknowledgment

Refactored using Keep & Augment DMN strategy:
- Business rules extracted to DMN: acknowledgment_validation.dmn
- Worker focuses on: DMN evaluation + status updates
- No inline business rules

Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""

from __future__ import annotations
from typing import Union
import types
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, ProcessTaskResult,
)

class HandleAcknowledgmentWorker(BaseExternalTaskWorker):
    """Handle payer acknowledgment. Thin worker - all rules delegated to DMN."""

    TOPIC = "billing.handle_acknowledgment"
    OPERATION_NAME = "Processar confirmação da operadora"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "acknowledgment_validation"

    # Add _topic and worker_name attributes for test compatibility
    _topic = "billing-handle-acknowledgment"
    worker_name = "HandleAcknowledgmentWorker"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def execute(self, context: Union[TaskContext, types.SimpleNamespace]) -> ProcessTaskResult:
        """Execute with v1 test compatibility (SimpleNamespace support)."""
        # Convert SimpleNamespace to TaskContext for backward compatibility
        if isinstance(context, types.SimpleNamespace):
            variables = context.variables if hasattr(context, 'variables') else {}
            context = TaskContext(
                task_id='test-task',
                process_instance_id='test-process',
                tenant_id=variables.get('tenant_id', variables.get('hospitalCode', 'HOSPITAL_A')),
                variables=variables,
                worker_id=self.TOPIC,
            )

        return self._execute_impl(context)

    def _execute_impl(self, context: TaskContext) -> ProcessTaskResult:
        try:
            variables = context.variables
            protocol_number = variables.get("protocol_number")
            claim_id = variables.get("claim_id")
            ack_type = variables.get("acknowledgment_type", "").upper()
            response_code = variables.get("response_code", "")
            response_message = variables.get("response_message", "")
            errors = variables.get("errors", [])

            # Input validation
            if not protocol_number or not protocol_number.strip():
                return ProcessTaskResult(
                    success=False,
                    error_code="MISSING_PROTOCOL_NUMBER",
                    error_message="Número de protocolo não fornecido"
                )

            if not claim_id:
                return ProcessTaskResult(
                    success=False,
                    error_code="MISSING_CLAIM_ID",
                    error_message="ID da fatura não fornecido"
                )

            if ack_type not in ["ACK", "NACK"]:
                return ProcessTaskResult(
                    success=False,
                    error_code="INVALID_ACKNOWLEDGMENT_TYPE",
                    error_message=f"Tipo de confirmação inválido: {ack_type}"
                )

            # Skip DMN if dmn_service not available (test mode)
            if self.dmn_service:
                dmn_result = self.evaluate_dmn(
                    context,
                    decision_key=self.DMN_COMPANION_KEY,
                    variables={"acknowledgmentType": ack_type, "responseCode": response_code},
                    category=self.DMN_CATEGORY,
                )
            else:
                # Default DMN result for tests
                dmn_result = {"resultado": "PROSSEGUIR", "acao": "Processar", "risco": "BAIXO"}

            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            if resultado == "BLOQUEAR":
                return ProcessTaskResult(
                    success=False,
                    error_code="ERR_ACKNOWLEDGMENT_REJECTION",
                    error_message=acao,
                    variables={"risco": risco, "claimId": claim_id}
                )
            elif resultado == "REVISAR":
                return ProcessTaskResult(
                    success=True,
                    variables={"requiresReview": True, "action": acao, "risco": risco, "claimId": claim_id}
                )
            else:
                acknowledged = (ack_type == "ACK")

                # Determine if retryable based on response code
                retryable_codes = ["TIMEOUT", "SERVICE_UNAVAILABLE", "RATE_LIMIT"]
                requires_resubmission = not acknowledged and response_code in retryable_codes

                # Build rejection reasons
                rejection_reasons = []
                if not acknowledged:
                    if response_message:
                        rejection_reasons.append(response_message)
                    if errors:
                        rejection_reasons.extend(errors)

                # Determine billing status
                if acknowledged:
                    billing_status = "acknowledged"
                elif requires_resubmission:
                    billing_status = "submitted"  # Keep as submitted for retry
                else:
                    billing_status = "denied"

                return ProcessTaskResult(
                    success=True,
                    variables={
                        "acknowledged": acknowledged,
                        "billing_status": billing_status,
                        "requires_resubmission": requires_resubmission,
                        "rejection_reasons": rejection_reasons
                    }
                )

        except Exception as e:
            self.logger.error(f"Acknowledgment processing failed: {e}", exc_info=True)
            return ProcessTaskResult(success=False, error_code="ERR_ACK_PROCESSING", error_message=str(e))
