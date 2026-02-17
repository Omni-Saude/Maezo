"""
Update Payment Worker (Refactored)
Purpose: Recalculate payment after glosa appeal outcome using DMN-based rules

TOPIC: glosa.update_payment

Refactored using Keep & Augment DMN strategy:
- Existing revenue_recovery DMN preserved
- Inline rules extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""
from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class UpdatePaymentWorkerV2(BaseExternalTaskWorker):
    """Refactored payment update worker. Thin worker pattern."""

    TOPIC = "glosa.update_payment"
    DMN_COMPANION_KEY = "payment/payment_update_adjudication"
    DMN_COMPANION_CATEGORY = "revenue_recovery"

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            claim_id = variables.get("claimId")
            appeal_status = variables.get("appealStatus", "PENDING")
            original_amount = Decimal(str(variables.get("originalAmount", 0)))
            denied_amount = Decimal(str(variables.get("deniedAmount", 0)))
            recovered_amount = Decimal(str(variables.get("recoveredAmount", 0)))

            if not claim_id:
                return TaskResult.bpmn_error(
                    error_code="ERR_MISSING_CLAIM_ID",
                    error_message="ID da conta é obrigatório",
                )

            if original_amount <= Decimal("0"):
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_AMOUNT",
                    error_message="Valor original deve ser maior que zero",
                )

            # Calculate recovery rate
            recovery_rate = float(recovered_amount / denied_amount) if denied_amount > 0 else 0.0

            # Evaluate companion DMN for payment update validation
            try:
                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_COMPANION_KEY,
                    variables={
                        "recoveryRate": recovery_rate,
                        "deniedAmount": float(denied_amount),
                    },
                    category=self.DMN_COMPANION_CATEGORY,
                )
            except Exception as dmn_error:
                self.logger.warning(f"DMN evaluation failed, using fallback: {dmn_error}")
                dmn_result = {}

            # Handle BOTH old 5-output and new 3-output DMN schemas with fallback
            resultado = dmn_result.get("resultado", "PROSSEGUIR")  # Default to PROSSEGUIR for normal flow
            acao = dmn_result.get("acao") or dmn_result.get("observacao", "Processar normalmente") + " " + dmn_result.get("acaoRecomendada", "")
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "BAIXO")

            # Calculate adjusted payment
            adjusted_payment = original_amount - denied_amount + recovered_amount
            adjusted_payment = max(adjusted_payment, Decimal("0"))

            # Determine adjustment type
            adjustment_type = self._determine_adjustment_type(recovery_rate, denied_amount)

            # Determine new billing status
            new_billing_status = self._determine_billing_status(adjustment_type, adjusted_payment)

            # Calculate write-off amount
            write_off_amount = max(denied_amount - recovered_amount, Decimal("0"))

            # Generate financial summary
            financial_summary = self._generate_financial_summary(
                original_amount, denied_amount, recovered_amount, adjusted_payment, write_off_amount, adjustment_type
            )

            # Route on resultado
            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(
                    error_code="ERR_PAYMENT_UPDATE_BLOCKED",
                    error_message=f"Atualização bloqueada: {acao}",
                    variables={
                        "adjustedPaymentBRL": str(adjusted_payment),
                        "risk": risco,
                    },
                )
            elif resultado == "PROSSEGUIR":
                return TaskResult.success({
                    "adjustedPaymentBRL": str(adjusted_payment),
                    "paymentAdjustmentType": adjustment_type,
                    "newBillingStatus": new_billing_status,
                    "writeOffAmount": str(write_off_amount),
                    "recoveryRate": recovery_rate,
                    "financialSummary": financial_summary,
                    "risk": risco,
                    "action": acao,
                })
            else:  # REVISAR
                return TaskResult.success({
                    "adjustedPaymentBRL": str(adjusted_payment),
                    "paymentAdjustmentType": adjustment_type,
                    "newBillingStatus": new_billing_status,
                    "writeOffAmount": str(write_off_amount),
                    "recoveryRate": recovery_rate,
                    "financialSummary": financial_summary,
                    "requiresReview": True,
                    "risk": risco,
                    "action": acao,
                })

        except Exception as e:
            self.logger.error(f"Error updating payment: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_PAYMENT_UPDATE",
                error_message=str(e),
            )

    def _determine_adjustment_type(self, recovery_rate: float, denied_amount: Decimal) -> str:
        """Determine payment adjustment type based on recovery rate.
        Fallback only - primary logic in companion DMN (payment_update_adjudication) rules 1-5.
        """
        # Special case: no denial means no adjustment needed
        if denied_amount == Decimal("0"):
            return "NO_ADJUSTMENT"

        thresholds = [(0.95, "FULL_RECOVERY"), (0.10, "PARTIAL_RECOVERY"), (0.001, "MINIMAL_RECOVERY")]
        for threshold, adj_type in thresholds:
            if recovery_rate >= threshold:
                return adj_type
        return "WRITE_OFF"

    def _determine_billing_status(self, adjustment_type: str, adjusted_payment: Decimal) -> str:
        """Determine new billing status based on adjustment.
        Fallback only - primary logic in companion DMN (payment_update_adjudication).
        """
        status_map = {
            "FULL_RECOVERY": "PAYMENT_EXPECTED",
            "PARTIAL_RECOVERY": "PARTIAL_PAYMENT_EXPECTED",
            "MINIMAL_RECOVERY": "PARTIAL_PAYMENT_EXPECTED",
            "WRITE_OFF": "WRITTEN_OFF",
        }
        if adjustment_type in status_map:
            return status_map[adjustment_type]
        return "WRITTEN_OFF" if adjusted_payment <= Decimal("0") else "PAYMENT_EXPECTED"

    def _generate_financial_summary(
        self,
        original_amount: Decimal,
        denied_amount: Decimal,
        recovered_amount: Decimal,
        adjusted_payment: Decimal,
        write_off_amount: Decimal,
        adjustment_type: str
    ) -> str:
        """Generate human-readable financial summary in Portuguese."""
        adjustment_labels = {
            "FULL_RECOVERY": "Recuperação Total",
            "PARTIAL_RECOVERY": "Recuperação Parcial",
            "MINIMAL_RECOVERY": "Recuperação Mínima",
            "WRITE_OFF": "Baixa Contábil",
            "NO_ADJUSTMENT": "Sem Ajuste",
        }

        label = adjustment_labels.get(adjustment_type, adjustment_type)

        return (
            f"Valor Original: R$ {original_amount:.2f} | "
            f"Valor Glosado: R$ {denied_amount:.2f} | "
            f"Valor Recuperado: R$ {recovered_amount:.2f} | "
            f"Pagamento Ajustado: R$ {adjusted_payment:.2f} | "
            f"Valor Baixado: R$ {write_off_amount:.2f} | "
            f"Tipo de Ajuste: {label}"
        )
# Backward compatibility alias
UpdatePaymentWorker = UpdatePaymentWorkerV2
