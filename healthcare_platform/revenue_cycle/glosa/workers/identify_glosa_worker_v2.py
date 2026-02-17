"""
Identify Glosa Worker (Refactored)
Purpose: Identify glosas from payer claim responses using DMN rules

TOPIC: glosa.identify

Refactored using Keep & Augment DMN strategy:
- Existing glosa_prevention DMN preserved
- Inline rules extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""
from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class IdentifyGlosaWorkerV2(BaseExternalTaskWorker):
    """Refactored glosa identification worker. Thin worker pattern."""

    TOPIC = "glosa.identify"
    DMN_COMPANION_KEY = "identification/glosa_identify_adjudication"
    DMN_COMPANION_CATEGORY = "glosa_prevention"

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            claim_response_data = variables.get("claimResponse")
            claim_id = variables.get("claimId")

            if not claim_response_data:
                return TaskResult.bpmn_error(
                    error_code="ERR_MISSING_CLAIM_RESPONSE",
                    error_message="Resposta da operadora não encontrada",
                )

            # Extract glosa items from claim response
            glosa_items = self._extract_glosa_items(claim_response_data)
            total_denied = sum(float(item["denied_amount"]) for item in glosa_items)

            # Evaluate companion DMN for identification validation
            reason_text = self._get_primary_reason_text(glosa_items)
            adjudication_category = self._get_adjudication_category(claim_response_data)

            try:
                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_COMPANION_KEY,
                    variables={
                        "reasonText": reason_text,
                        "adjudicationCategory": adjudication_category,
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

            # Route on resultado
            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(
                    error_code="ERR_GLOSA_IDENTIFICATION_BLOCKED",
                    error_message=f"Identificação bloqueada: {acao}",
                    variables={"risk": risco, "reason": acao},
                )
            elif resultado == "PROSSEGUIR":
                return TaskResult.success({
                    "glosaItems": glosa_items,
                    "totalDeniedAmount": total_denied,
                    "glosaCount": len(glosa_items),
                    "hasGlosas": len(glosa_items) > 0,
                    "risk": risco,
                    "action": acao,
                })
            else:  # REVISAR
                return TaskResult.success({
                    "glosaItems": glosa_items,
                    "totalDeniedAmount": total_denied,
                    "glosaCount": len(glosa_items),
                    "hasGlosas": len(glosa_items) > 0,
                    "requiresReview": True,
                    "risk": risco,
                    "action": acao,
                })

        except Exception as e:
            self.logger.error(f"Error identifying glosas: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_GLOSA_IDENTIFICATION",
                error_message=str(e),
            )

    def _extract_glosa_items(self, claim_response_data: Dict[str, Any]) -> list[dict]:
        """Extract glosa items from claim response."""
        glosa_items = []
        items = claim_response_data.get("items", [])

        for item in items:
            adjudication = item.get("adjudication", [])

            for adj in adjudication:
                if adj.get("category") in ["denied", "rejected"]:
                    reason_code = self._map_reason_code(adj.get("reason"))
                    denied_amount = Decimal(str(adj.get("amount", 0)))

                    # Calculate original amount from unit price and quantity
                    unit_price = Decimal(str(item.get("unitPrice", 0)))
                    quantity = Decimal(str(item.get("quantity", 1)))
                    original_amount = float(unit_price * quantity)

                    glosa_items.append({
                        "item_sequence": item.get("sequence"),
                        "procedure_code": item.get("productOrService", {}).get("code"),
                        "reason_code": reason_code,
                        "denied_amount": float(denied_amount),
                        "original_amount": original_amount,
                        "notes": adj.get("reason"),
                    })

        return glosa_items

    def _map_reason_code(self, reason: str) -> str:
        """Map payer reason text to standardized reason code.
        Delegated to companion DMN (glosa_identify_adjudication) rules 1-9.
        This fallback only fires when DMN is unavailable.
        Returns the enum VALUE (e.g., "GLOSA_001"), not the name.
        """
        from healthcare_platform.shared.domain.enums import GlosaReasonCode

        if not reason:
            return GlosaReasonCode.TISS_VALIDATION.value
        # Fallback mapping - primary logic lives in companion DMN
        reason_lower = reason.lower()
        mapping = [
            ("autorização ausente", GlosaReasonCode.MISSING_AUTH.value),
            ("autorização vencida", GlosaReasonCode.EXPIRED_AUTH.value),
            ("autorização expirada", GlosaReasonCode.EXPIRED_AUTH.value),
            ("duplicad", GlosaReasonCode.DUPLICATE_CHARGE.value),
            ("cobrança duplicada", GlosaReasonCode.DUPLICATE_BILLING.value),
            ("quantidade excede", GlosaReasonCode.EXCEEDS_QUANTITY.value),
            ("não coberto", GlosaReasonCode.NOT_COVERED.value),
            ("código incorreto", GlosaReasonCode.WRONG_CODE.value),
            ("código inválido", GlosaReasonCode.INVALID_CODE.value),
            ("procedimento incompatível", GlosaReasonCode.INCOMPATIBLE_PROCEDURE.value),
            ("documentação", GlosaReasonCode.MISSING_DOCUMENTATION.value),
            ("divergência no valor", GlosaReasonCode.PRICE_DIVERGENCE.value),
        ]
        for keyword, code_value in mapping:
            if keyword in reason_lower:
                return code_value
        return GlosaReasonCode.TISS_VALIDATION.value

    def _get_primary_reason_text(self, glosa_items: list[dict]) -> str:
        """Get primary reason text from glosa items."""
        if not glosa_items:
            return "Unknown"
        return glosa_items[0].get("notes", "Unknown")

    def _get_adjudication_category(self, claim_response_data: Dict[str, Any]) -> str:
        """Get adjudication category from claim response."""
        items = claim_response_data.get("items", [])
        if not items:
            return "general"

        first_adjudication = items[0].get("adjudication", [])
        if not first_adjudication:
            return "general"

        return first_adjudication[0].get("category", "general")
# Backward compatibility alias
IdentifyGlosaWorker = IdentifyGlosaWorkerV2
