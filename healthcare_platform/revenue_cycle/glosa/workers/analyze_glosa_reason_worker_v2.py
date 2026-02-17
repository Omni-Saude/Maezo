"""
Analyze Glosa Reason Worker (Refactored)
Purpose: Analyze glosa reasons and identify systemic patterns using DMN-based classification

TOPIC: glosa.analyze_reason

Refactored using Keep & Augment DMN strategy:
- Existing glosa_prevention DMN preserved
- Inline pattern detection rules extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""
from __future__ import annotations

from typing import Any, Dict, List

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class AnalyzeGlosaReasonWorkerV2(BaseExternalTaskWorker):
    """Refactored glosa reason analysis worker. Thin worker pattern."""

    TOPIC = "glosa.analyze_reason"
    DMN_COMPANION_KEY = "reason_analysis/glosa_reason_adjudication"
    DMN_COMPANION_CATEGORY = "glosa_prevention"

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute glosa reason analysis.

        Args:
            context: Task context with classifiedGlosas, claimId

        Returns:
            TaskResult with analyzedGlosas, reasonDistribution, rootCausePatterns
        """
        try:
            # 1. Extract input variables
            variables = context.variables
            classified_glosas = variables.get("classifiedGlosas", [])
            claim_id = variables.get("claimId", "unknown")

            if not classified_glosas:
                return TaskResult.bpmn_error(
                    error_code="ERR_NO_GLOSAS",
                    error_message="Nenhuma glosa para analisar",
                    variables={"claimId": claim_id},
                )

            # 2. Process each glosa through DMN
            analyzed_glosas = []
            reason_distribution = {}

            for glosa in classified_glosas:
                glosa_type = glosa.get("glosa_type", "")
                description = glosa.get("description", "")

                # Evaluate companion DMN for reason code determination
                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_COMPANION_KEY,
                    variables={
                        "glosaType": glosa_type,
                        "description": description,
                        "deniedAmount": glosa.get("denied_amount", 0),
                    },
                    category=self.DMN_COMPANION_CATEGORY,
                )

                # 3. Handle BOTH old 5-output and new 3-output schemas
                resultado = dmn_result.get("resultado", "REVISAR")
                acao = dmn_result.get("acao") or (
                    dmn_result.get("observacao", "") + " " + dmn_result.get("acaoRecomendada", "")
                )
                risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

                # Extract reason code from DMN or infer from acao
                reason_code = dmn_result.get("reasonCode", self._infer_reason_code(glosa))
                reason_description = dmn_result.get("reasonDescription", acao.strip())

                # Enrich glosa with analysis
                enriched = {
                    **glosa,
                    "reason_code": reason_code,
                    "reason_description": reason_description,
                    "risco": risco,
                }
                analyzed_glosas.append(enriched)

                # Update distribution
                reason_distribution[reason_code] = reason_distribution.get(reason_code, 0) + 1

            # 4. Identify root cause patterns from distribution
            root_cause_patterns = self._identify_patterns(
                reason_distribution,
                len(analyzed_glosas)
            )

            # 4.5 Detect systemic issues (>50% same reason)
            systemic_issues = self._detect_systemic_issues(
                analyzed_glosas,
                reason_distribution,
                len(analyzed_glosas)
            )

            # 5. Route based on overall risk level
            max_risco = self._get_max_risk(analyzed_glosas)

            if max_risco == "ALTO" and len(root_cause_patterns) > 0:
                # High risk with patterns detected - needs review
                return TaskResult.success({
                    "analyzedGlosas": analyzed_glosas,
                    "reasonDistribution": reason_distribution,
                    "rootCausePatterns": root_cause_patterns,
                    "systemicIssues": systemic_issues,
                    "requiresReview": True,
                    "reviewAction": f"Padrões sistêmicos detectados: {len(root_cause_patterns)} padrões",
                    "maxRisco": max_risco,
                })
            elif max_risco == "CRITICO":
                return TaskResult.bpmn_error(
                    error_code="ERR_CRITICAL_PATTERN",
                    error_message="Padrão crítico detectado - requer escalação imediata",
                    variables={
                        "analyzedGlosas": analyzed_glosas,
                        "reasonDistribution": reason_distribution,
                        "rootCausePatterns": root_cause_patterns,
                        "systemicIssues": systemic_issues,
                        "maxRisco": max_risco,
                    },
                )
            else:
                # Normal processing - continue
                return TaskResult.success({
                    "analyzedGlosas": analyzed_glosas,
                    "reasonDistribution": reason_distribution,
                    "rootCausePatterns": root_cause_patterns,
                    "systemicIssues": systemic_issues,
                    "maxRisco": max_risco,
                })

        except Exception as e:
            self.logger.error(f"Error analyzing glosa reasons: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_REASON_ANALYSIS_PROCESSING",
                error_message=str(e),
            )

    def _infer_reason_code(self, glosa: Dict[str, Any]) -> str:
        """Infer reason code from glosa data.
        Fallback only - primary logic lives in companion DMN (glosa_reason_adjudication).
        """
        description = glosa.get("description", "").lower()
        mapping = [
            (["autorização", "auth"], "MISSING_AUTH"),
            (["documentação", "documento"], "MISSING_DOCUMENTATION"),
            (["código", "code"], "WRONG_CODE"),
            (["duplicad", "duplicate"], "DUPLICATE_CHARGE"),
            (["quantidade", "quantity"], "EXCEEDS_QUANTITY"),
        ]
        for keywords, code in mapping:
            if any(kw in description for kw in keywords):
                return code
        return "MISSING_DOCUMENTATION"

    def _identify_patterns(
        self,
        reason_distribution: Dict[str, int],
        total_count: int
    ) -> List[Dict[str, Any]]:
        """Identify patterns from reason distribution.

        Maps reason codes to semantic pattern types for backward compatibility with V1 tests.
        """
        patterns = []
        pattern_threshold = 3

        # Map reason codes to semantic pattern types (V1 compatibility)
        pattern_type_map = {
            "MISSING_AUTH": "authorization_process",
            "EXPIRED_AUTH": "authorization_process",
            "MISSING_DOCUMENTATION": "documentation_gap",
            "DUPLICATE_CHARGE": "billing_control",
            "EXCEEDS_QUANTITY": "billing_control",
            "WRONG_CODE": "coding_accuracy",
        }

        for reason_code, count in reason_distribution.items():
            if count >= pattern_threshold:
                # Determine severity
                if reason_code == "DUPLICATE_CHARGE":
                    severity = "critical"  # Duplicates are always critical
                elif count >= 5:
                    severity = "high"
                else:
                    severity = "medium"

                # Map to semantic pattern type
                pattern_type = pattern_type_map.get(reason_code, f"recurring_{reason_code.lower()}")

                patterns.append({
                    "pattern_type": pattern_type,
                    "description": f"Padrão recorrente: {reason_code}",
                    "occurrences": count,
                    "severity": severity,
                    "percentage": (count / total_count * 100) if total_count > 0 else 0,
                })

        return patterns

    def _detect_systemic_issues(
        self,
        analyzed_glosas: List[Dict[str, Any]],
        reason_distribution: Dict[str, int],
        total_count: int
    ) -> List[str]:
        """Detect systemic issues when >50% of glosas have the same reason.

        Returns:
            List of issue descriptions
        """
        systemic_issues = []
        systemic_threshold = 0.5  # 50%

        for reason_code, count in reason_distribution.items():
            percentage = count / total_count if total_count > 0 else 0
            if percentage > systemic_threshold:
                # Build issue description using actual glosa descriptions
                glosa_descriptions = {
                    g.get("description", "") for g in analyzed_glosas
                    if g.get("reason_code") == reason_code
                }
                # Use most common description
                for desc in glosa_descriptions:
                    if desc:
                        systemic_issues.append(
                            f"Problema sistêmico detectado: {desc} ({count}/{total_count} glosas, {percentage*100:.0f}%)"
                        )
                        break

        return systemic_issues

    def _get_max_risk(self, analyzed_glosas: List[Dict[str, Any]]) -> str:
        """Get maximum risk level from analyzed glosas."""
        risk_levels = {"CRITICO": 4, "ALTO": 3, "MEDIO": 2, "BAIXO": 1, "OK": 0}
        max_level = "OK"
        max_value = 0

        for glosa in analyzed_glosas:
            risco = glosa.get("risco", "MEDIO")
            value = risk_levels.get(risco, 2)
            if value > max_value:
                max_value = value
                max_level = risco

        return max_level
# Backward compatibility alias
AnalyzeGlosaReasonWorker = AnalyzeGlosaReasonWorkerV2
