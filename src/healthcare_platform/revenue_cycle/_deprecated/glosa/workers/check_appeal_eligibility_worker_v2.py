"""
Check Appeal Eligibility Worker (Refactored)
Purpose: Validate appeal eligibility according to ANS RN 424/2017 using DMN-based decision

TOPIC: glosa.check_appeal_eligibility

Refactored using Keep & Augment DMN strategy:
- Existing revenue_recovery DMN preserved
- Inline eligibility checks extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)
from healthcare_platform.shared.domain.exceptions import (
    GlosaAppealDeadlineExpired,
    GlosaNotAppealable,
)


class CheckAppealEligibilityWorkerV2(BaseExternalTaskWorker):
    """Refactored appeal eligibility check worker. Thin worker pattern."""

    TOPIC = "glosa.check_appeal_eligibility"
    DMN_COMPANION_KEY = "eligibility/appeal_eligibility_adjudication"
    DMN_COMPANION_CATEGORY = "revenue_recovery"
    APPEAL_DEADLINE_DAYS = 30  # ANS RN 424/2017

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute appeal eligibility check.

        Args:
            context: Task context with analyzedGlosas, glosaDate, claimId

        Returns:
            TaskResult with eligibleGlosas, ineligibleGlosas, appealDeadline, daysRemaining
        """
        try:
            # 1. Extract input variables
            variables = context.variables
            analyzed_glosas = variables.get("analyzedGlosas", [])
            glosa_date_str = variables.get("glosaDate")
            claim_id = variables.get("claimId", "UNKNOWN")
            available_documentation = variables.get("availableDocumentation", [])

            if not analyzed_glosas:
                return TaskResult.bpmn_error(
                    error_code="ERR_NO_GLOSAS",
                    error_message="Nenhuma glosa encontrada para análise",
                    variables={"claimId": claim_id},
                )

            if not glosa_date_str:
                return TaskResult.bpmn_error(
                    error_code="ERR_MISSING_DATE",
                    error_message="Data da glosa não informada",
                    variables={"claimId": claim_id},
                )

            # 2. Parse dates and calculate deadline
            glosa_date = datetime.fromisoformat(glosa_date_str.replace("Z", "+00:00"))
            if glosa_date.tzinfo is None:
                glosa_date = glosa_date.replace(tzinfo=timezone.utc)

            appeal_deadline = glosa_date + timedelta(days=self.APPEAL_DEADLINE_DAYS)
            now = datetime.now(timezone.utc)
            days_remaining = (appeal_deadline - now).days

            # 3. Process each glosa through DMN
            eligible_glosas: List[Dict[str, Any]] = []
            ineligible_glosas: List[Dict[str, Any]] = []

            for glosa in analyzed_glosas:
                # Support both "type" (v1) and "glosa_type" (v2) keys
                glosa_type = glosa.get("type") or glosa.get("glosa_type", "PARTIAL")
                reason_code = glosa.get("reasonCode") or glosa.get("reason_code", "")

                # Evaluate companion DMN for eligibility
                try:
                    dmn_result = self.evaluate_dmn(
                        context=context,
                        decision_key=self.DMN_COMPANION_KEY,
                        variables={
                            "glosaType": glosa_type,
                            "reasonCode": reason_code,
                            "daysRemaining": days_remaining,
                            "availableDocumentation": available_documentation,
                        },
                        category=self.DMN_COMPANION_CATEGORY,
                    )
                except Exception as dmn_error:
                    self.logger.warning(f"DMN evaluation failed, using fallback: {dmn_error}")
                    # Fallback: mark as eligible if not TOTAL type and within deadline
                    dmn_result = {"resultado": "PROSSEGUIR" if glosa_type != "TOTAL" else "BLOQUEAR"}

                # 4. Handle BOTH old 5-output and new 3-output schemas with fallback
                resultado = dmn_result.get("resultado", "PROSSEGUIR")
                acao = dmn_result.get("acao") or dmn_result.get("observacao", "Processar normalmente") + " " + dmn_result.get("acaoRecomendada", "")
                risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "BAIXO")

                # 5. Route based on resultado
                if resultado == "PROSSEGUIR":
                    # Eligible for appeal
                    eligible_glosas.append(glosa)
                else:
                    # Not eligible or needs review
                    ineligible_entry = {
                        **glosa,
                        "ineligibilityReason": acao.strip(),
                        "risco": risco,
                    }
                    # Add missing documentation if provided by DMN
                    if "missingDocumentation" in dmn_result:
                        ineligible_entry["missingDocumentation"] = dmn_result["missingDocumentation"]
                    ineligible_glosas.append(ineligible_entry)

            # Calculate total eligible amount
            total_eligible_amount = sum(
                self._parse_amount(g.get("amountBRL", "0"))
                for g in eligible_glosas
            )

            # 6. Determine overall result
            if days_remaining < 0:
                # Raise exception for deadline expired
                raise GlosaAppealDeadlineExpired(
                    f"Prazo de recurso expirado em {appeal_deadline.date()}. ANS RN 424/2017 define prazo de 30 dias."
                )
            elif not eligible_glosas:
                # Raise exception for no eligible glosas
                raise GlosaNotAppealable("Nenhuma glosa elegível para recurso")
            else:
                # Success - has eligible glosas
                return TaskResult.success({
                    "appealEligible": True,  # V1 compatibility
                    "eligibleGlosas": eligible_glosas,
                    "ineligibleGlosas": ineligible_glosas,
                    "appealDeadline": appeal_deadline.isoformat(),
                    "daysRemaining": days_remaining,
                    "eligibilityRate": len(eligible_glosas) / len(analyzed_glosas) if analyzed_glosas else 0,
                    "totalEligibleAmount": f"{total_eligible_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                })

        except (GlosaAppealDeadlineExpired, GlosaNotAppealable):
            # Re-raise business exceptions
            raise
        except Exception as e:
            self.logger.error(f"Error checking appeal eligibility: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_ELIGIBILITY_CHECK_PROCESSING",
                error_message=str(e),
            )

    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse Brazilian currency format to Decimal."""
        try:
            # Remove dots (thousands separator), replace comma with dot
            cleaned = str(amount_str).replace(".", "").replace(",", ".")
            return Decimal(cleaned)
        except (ValueError, TypeError):
            return Decimal("0")
# Backward compatibility alias
CheckAppealEligibilityWorker = CheckAppealEligibilityWorkerV2
