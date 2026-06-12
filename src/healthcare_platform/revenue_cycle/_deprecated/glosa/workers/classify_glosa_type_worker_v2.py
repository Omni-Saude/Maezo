"""
Classify Glosa Type Worker (Refactored)
Purpose: Classify glosas into types (administrative, technical, linear) using DMN-based rules

TOPIC: glosa.classify_type

Refactored using Keep & Augment DMN strategy:
- Existing glosa_prevention DMN preserved
- Inline classification logic extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class ClassifyGlosaTypeWorkerV2(BaseExternalTaskWorker):
    """Refactored glosa type classification worker. Thin worker pattern."""

    TOPIC = "glosa.classify_type"
    DMN_COMPANION_KEY = "classification/glosa_type_adjudication"
    DMN_COMPANION_CATEGORY = "glosa_prevention"

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute glosa type classification.

        Args:
            context: Task context with glosaItems, reasonCode (optional)

        Returns:
            TaskResult with classifiedGlosas, glosaTypeDistribution, hasAdministrative, hasTechnical
        """
        try:
            # 1. Extract input variables
            variables = context.variables
            glosa_items = variables.get("glosaItems", [])
            reason_code_filter = variables.get("reasonCode")

            if not glosa_items:
                # Empty result - no glosas to classify
                return TaskResult.success({
                    "classifiedGlosas": [],
                    "glosaTypeDistribution": {},
                    "hasAdministrative": False,
                    "hasTechnical": False,
                })

            # 2. Process each glosa through DMN
            classified_glosas: List[Dict[str, Any]] = []
            type_distribution: Dict[str, int] = {}

            for glosa in glosa_items:
                reason_code = glosa.get("reason_code", "")

                # Apply filter if specified
                if reason_code_filter and reason_code != reason_code_filter:
                    continue

                # Calculate denial ratio
                denied_amount = Decimal(str(glosa.get("denied_amount", 0)))
                original_amount = Decimal(str(glosa.get("original_amount", 0)))
                denial_ratio = float(
                    denied_amount / original_amount
                    if original_amount > Decimal("0.00")
                    else Decimal("0.00")
                )

                # Evaluate companion DMN for type classification
                try:
                    dmn_result = self.evaluate_dmn(
                        context=context,
                        decision_key=self.DMN_COMPANION_KEY,
                        variables={
                            "reasonCode": reason_code,
                            "denialRatio": denial_ratio,
                            "deniedAmount": float(denied_amount),
                        },
                        category=self.DMN_COMPANION_CATEGORY,
                    )
                except Exception as dmn_error:
                    self.logger.warning(f"DMN evaluation failed, using fallback: {dmn_error}")
                    # Fallback classification based on denial ratio
                    dmn_result = {
                        "glosaType": "TOTAL" if denial_ratio >= 1.0 else "ADMINISTRATIVE",
                        "glosaExtent": "TOTAL" if denial_ratio >= 1.0 else "PARTIAL",
                    }

                # 3. Handle BOTH old 5-output and new 3-output schemas with fallback
                # DEPRECATED: resultado era usado no roteamento DMN padrao
                # resultado = dmn_result.get("resultado", "PROSSEGUIR")
                # DEPRECATED: acao era usada na descricao da acao recomendada
                # acao = dmn_result.get("acao") or dmn_result.get("observacao", "Processar normalmente") + " " + dmn_result.get("acaoRecomendada", "")
                risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "BAIXO")

                # Extract classification from DMN (uppercase)
                glosa_type_upper = dmn_result.get("glosaType", "TECHNICAL")
                glosa_extent_upper = dmn_result.get("glosaExtent", "PARTIAL")

                # Convert to lowercase enum values for compatibility with GlosaType/GlosaExtent enums
                glosa_type = glosa_type_upper.lower()
                glosa_extent = glosa_extent_upper.lower()

                # Enrich glosa with classification
                classified = {
                    **glosa,
                    "glosa_type": glosa_type,
                    "glosa_extent": glosa_extent,
                    "denial_ratio": denial_ratio,
                    "risco": risco,
                }
                classified_glosas.append(classified)

                # Update distribution (use lowercase for enum compatibility)
                type_distribution[glosa_type] = type_distribution.get(glosa_type, 0) + 1

            # 4. Calculate flags (use lowercase enum values)
            has_administrative = type_distribution.get("administrative", 0) > 0
            has_technical = type_distribution.get("technical", 0) > 0

            # 5. Route based on distribution patterns (use lowercase)
            if type_distribution.get("total", 0) > 0:
                # Has TOTAL glosa - needs escalation
                return TaskResult.success({
                    "classifiedGlosas": classified_glosas,
                    "glosaTypeDistribution": type_distribution,
                    "hasAdministrative": has_administrative,
                    "hasTechnical": has_technical,
                    "requiresReview": True,
                    "reviewAction": "Glosa TOTAL detectada - requer escalação",
                })
            else:
                # Normal classification
                return TaskResult.success({
                    "classifiedGlosas": classified_glosas,
                    "glosaTypeDistribution": type_distribution,
                    "hasAdministrative": has_administrative,
                    "hasTechnical": has_technical,
                })

        except Exception as e:
            self.logger.error(f"Error classifying glosa types: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_TYPE_CLASSIFICATION_PROCESSING",
                error_message=str(e),
            )
# Backward compatibility alias
ClassifyGlosaTypeWorker = ClassifyGlosaTypeWorkerV2
