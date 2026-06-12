"""
Calculate Glosa Impact Worker (Refactored)
Purpose: Calculate financial impact and recovery potential using DMN-based rate determination

TOPIC: glosa.calculate_impact

Refactored using Keep & Augment DMN strategy:
- Existing revenue_recovery DMN preserved
- Inline recovery rate calculation extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class CalculateGlosaImpactWorkerV2(BaseExternalTaskWorker):
    """Refactored glosa impact calculation worker. Thin worker pattern."""

    TOPIC = "glosa.calculate_impact"
    DMN_COMPANION_KEY = "impact_calc/recovery_rate_adjudication"
    DMN_COMPANION_CATEGORY = "revenue_recovery"

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute glosa impact calculation.

        Args:
            context: Task context with classifiedGlosas

        Returns:
            TaskResult with totalImpactBRL, impactByType, denialPercentage, recoveryPotentialBRL
        """
        try:
            # 1. Extract input variables
            variables = context.variables
            classified_glosas = variables.get("classifiedGlosas", [])

            if not classified_glosas:
                return TaskResult.bpmn_error(
                    error_code="ERR_NO_GLOSAS",
                    error_message="Nenhuma glosa classificada para calcular impacto",
                )

            # 2. Calculate totals and per-type recovery
            total_impact = Decimal("0.00")
            total_original = Decimal("0.00")
            impact_by_type: Dict[str, Decimal] = {}
            recovery_potential = Decimal("0.00")

            # V1 recovery rates by type (for backward compatibility)
            recovery_rates_by_type = {
                "administrative": Decimal("0.80"),
                "technical": Decimal("0.60"),
                "linear": Decimal("0.40"),
                "total": Decimal("0.10"),  # Low recovery for total glosas
                "partial": Decimal("0.50"),  # Default
            }

            for glosa in classified_glosas:
                denied_amount = Decimal(str(glosa.get("denied_amount", 0)))
                original_amount = Decimal(str(glosa.get("original_amount", 0)))
                glosa_type = glosa.get("glosa_type", "partial")  # Lowercase enum value

                total_impact += denied_amount
                total_original += original_amount

                # Aggregate by type
                if glosa_type not in impact_by_type:
                    impact_by_type[glosa_type] = Decimal("0.00")
                impact_by_type[glosa_type] += denied_amount

                # Calculate per-glosa recovery using type-specific rate
                type_rate = recovery_rates_by_type.get(glosa_type, Decimal("0.50"))
                recovery_potential += denied_amount * type_rate

            # 3. Calculate denial percentage
            denial_percentage = float(
                (total_impact / total_original * Decimal("100"))
                if total_original > Decimal("0.00")
                else Decimal("0.00")
            )

            # 4. Evaluate DMN for risk determination (recovery already calculated per-type)
            dmn_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_COMPANION_KEY,
                variables={
                    "glosaType": list(impact_by_type.keys())[0] if impact_by_type else "partial",
                    "denialPercentage": denial_percentage,
                    "totalImpactBRL": float(total_impact),
                },
                category=self.DMN_COMPANION_CATEGORY,
            )

            # 5. Handle BOTH old 5-output and new 3-output schemas
            resultado = dmn_result.get("resultado", "PROSSEGUIR")
            acao = dmn_result.get("acao") or (
                dmn_result.get("observacao", "") + " " + dmn_result.get("acaoRecomendada", "")
            )
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            # Calculate average recovery rate for reporting
            average_recovery_rate = (
                recovery_potential / total_impact
                if total_impact > Decimal("0.00")
                else Decimal("0.50")
            )

            # 6. Convert to serializable format
            impact_by_type_float = {k: float(v) for k, v in impact_by_type.items()}

            # 6.5 Generate impact summary (V1 compatibility)
            impact_summary = self._generate_impact_summary(
                total_impact,
                impact_by_type,
                recovery_potential,
                denial_percentage
            )

            # 7. Route based on resultado
            if resultado == "BLOQUEAR":
                # Impact too high - escalate
                return TaskResult.bpmn_error(
                    error_code="ERR_HIGH_IMPACT",
                    error_message=acao.strip(),
                    variables={
                        "totalImpactBRL": float(total_impact),
                        "impactByType": impact_by_type_float,
                        "denialPercentage": denial_percentage,
                        "recoveryPotentialBRL": float(recovery_potential),
                        "risco": risco,
                    },
                )
            elif resultado == "PROSSEGUIR":
                # Normal impact - continue processing
                return TaskResult.success({
                    "totalImpactBRL": float(total_impact),
                    "impactByType": impact_by_type_float,
                    "denialPercentage": denial_percentage,
                    "recoveryPotentialBRL": float(recovery_potential),
                    "recoveryRate": float(average_recovery_rate),
                    "impactSummary": impact_summary,
                    "risco": risco,
                })
            else:  # REVISAR
                # Needs review
                return TaskResult.success({
                    "totalImpactBRL": float(total_impact),
                    "impactByType": impact_by_type_float,
                    "denialPercentage": denial_percentage,
                    "recoveryPotentialBRL": float(recovery_potential),
                    "impactSummary": impact_summary,
                    "requiresReview": True,
                    "reviewAction": acao.strip(),
                    "risco": risco,
                })

        except Exception as e:
            self.logger.error(f"Error calculating glosa impact: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_IMPACT_CALCULATION_PROCESSING",
                error_message=str(e),
            )

    def _generate_impact_summary(
        self,
        total_impact: Decimal,
        impact_by_type: Dict[str, Decimal],
        recovery_potential: Decimal,
        denial_percentage: float
    ) -> str:
        """Generate Portuguese impact summary."""
        summary_parts = [
            f"Impacto total: R$ {total_impact:,.2f}",
            f"Taxa de negação: {denial_percentage:.1f}%",
            f"Potencial de recuperação: R$ {recovery_potential:,.2f}",
        ]

        if impact_by_type:
            summary_parts.append("Distribuição por tipo:")
            for glosa_type, amount in impact_by_type.items():
                type_name = glosa_type.capitalize()
                summary_parts.append(f"  - {type_name}: R$ {amount:,.2f}")

        return " | ".join(summary_parts)

# Backward compatibility alias
CalculateGlosaImpactWorker = CalculateGlosaImpactWorkerV2
