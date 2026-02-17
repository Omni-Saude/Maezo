"""
Escalate to Supervisor Worker (Refactored)
Purpose: Prepare escalation package for supervisor review using DMN-based priority/team assignment

TOPIC: glosa.escalate_to_supervisor
ORPHAN: Yes (no BPMN reference found in glosa_management.bpmn)

Refactored using Keep & Augment DMN strategy:
- Existing revenue_recovery DMN preserved
- Inline priority/team determination extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)

Note: This worker is ORPHAN (not referenced by any BPMN). Preserved for future integration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class EscalateToSupervisorWorkerV2(BaseExternalTaskWorker):
    """Refactored escalation worker. Thin worker pattern. ORPHAN worker."""

    TOPIC = "glosa.escalate_to_supervisor"
    DMN_COMPANION_KEY = "escalation/escalation_adjudication"
    DMN_COMPANION_CATEGORY = "revenue_recovery"

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute escalation package preparation.

        Args:
            context: Task context with analyzedGlosas, totalImpactBRL, claimId, escalationReason

        Returns:
            TaskResult with escalationId, escalationPackage, priority, assignedTeam
        """
        try:
            # 1. Extract input variables
            variables = context.variables
            analyzed_glosas = variables.get("analyzedGlosas", [])
            total_impact_str = variables.get("totalImpactBRL", "0.00")
            claim_id = variables.get("claimId", "UNKNOWN")
            escalation_reason = variables.get("escalationReason", "Não especificado")

            # Parse impact amount (handle string or float)
            try:
                impact_amount = float(str(total_impact_str).replace(",", "."))
            except (ValueError, AttributeError):
                impact_amount = 0.0

            glosa_count = len(analyzed_glosas)

            # Check for TOTAL glosa
            has_total_glosa = any(
                g.get("glosa_type") == "TOTAL" or g.get("glosa_extent") == "TOTAL"
                for g in analyzed_glosas
            )

            # 2. Evaluate companion DMN for priority/team determination
            try:
                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_COMPANION_KEY,
                    variables={
                        "impactAmount": impact_amount,
                        "glosaCount": glosa_count,
                        "hasTotalGlosa": has_total_glosa,
                    },
                    category=self.DMN_COMPANION_CATEGORY,
                )
            except Exception as dmn_error:
                self.logger.warning(f"DMN evaluation failed, using fallback: {dmn_error}")
                dmn_result = {}

            # 3. Handle BOTH old 5-output and new 3-output schemas with fallback
            resultado = dmn_result.get("resultado", "PROSSEGUIR")
            acao = dmn_result.get("acao") or dmn_result.get("observacao", "Processar normalmente") + " " + dmn_result.get("acaoRecomendada", "")
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "BAIXO")

            # Extract priority and team from DMN
            priority = dmn_result.get("priority", self._determine_priority(impact_amount, glosa_count))
            assigned_team = dmn_result.get("assignedTeam", self._determine_team(impact_amount, has_total_glosa))

            # 4. Detect systemic issues
            systemic_issues_detected, systemic_issues = self._detect_systemic_issues(analyzed_glosas, has_total_glosa)

            # 5. Generate recommended actions
            recommended_actions = self._generate_recommended_actions(analyzed_glosas, priority, has_total_glosa)

            # 6. Generate financial impact breakdown
            financial_impact_breakdown = self._generate_financial_breakdown(analyzed_glosas)

            # 7. Generate escalation summary
            escalation_summary = self._generate_escalation_summary(
                claim_id, escalation_reason, priority, impact_amount, glosa_count, assigned_team
            )

            # 8. Generate escalation package
            escalation_id = f"ESC-{claim_id}-{uuid.uuid4().hex[:8].upper()}"
            escalation_date = datetime.now(timezone.utc)

            escalation_package = {
                "escalationId": escalation_id,
                "claimId": claim_id,
                "escalationDate": escalation_date.isoformat(),
                "priority": priority,
                "assignedTeam": assigned_team,
                "totalImpact": impact_amount,
                "glosaCount": glosa_count,
                "escalationReason": escalation_reason,
                "hasTotalGlosa": has_total_glosa,
                "recommendedAction": acao.strip(),
                "risco": risco,
                "systemicIssues": systemic_issues,
                "recommendedActions": recommended_actions,
                "financialImpactBreakdown": financial_impact_breakdown,
            }

            # 9. Route based on resultado
            if resultado == "BLOQUEAR":
                # Critical escalation - needs immediate attention
                return TaskResult.bpmn_error(
                    error_code="ERR_CRITICAL_ESCALATION",
                    error_message=acao.strip(),
                    variables={
                        "escalationId": escalation_id,
                        "escalationPackage": escalation_package,
                        "priority": priority,
                        "assignedTeam": assigned_team,
                        "requiresImmediateAction": True,
                        "systemicIssuesDetected": systemic_issues_detected,
                        "escalationSummary": escalation_summary,
                    },
                )
            elif resultado == "PROSSEGUIR":
                # Normal escalation
                return TaskResult.success({
                    "escalationId": escalation_id,
                    "escalationPackage": escalation_package,
                    "priority": priority,
                    "assignedTeam": assigned_team,
                    "requiresHumanDecision": True,
                    "humanTaskType": "supervisor_review",
                    "systemicIssuesDetected": systemic_issues_detected,
                    "escalationSummary": escalation_summary,
                })
            else:  # REVISAR
                # Needs additional review before escalation
                return TaskResult.success({
                    "escalationId": escalation_id,
                    "escalationPackage": escalation_package,
                    "priority": priority,
                    "assignedTeam": assigned_team,
                    "requiresReview": True,
                    "reviewAction": acao.strip(),
                    "requiresHumanDecision": True,
                    "risco": risco,
                    "systemicIssuesDetected": systemic_issues_detected,
                    "escalationSummary": escalation_summary,
                })

        except Exception as e:
            self.logger.error(f"Error escalating to supervisor: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_ESCALATION_PROCESSING",
                error_message=str(e),
            )

    def _determine_priority(self, amount: float, glosa_count: int) -> str:
        """Determine escalation priority (fallback if DMN doesn't provide).
        Primary logic in companion DMN (escalation_adjudication).
        """
        thresholds = [(50000.00, "CRITICAL"), (10000.00, "HIGH")]
        for threshold, priority in thresholds:
            if amount >= threshold:
                return priority
        return "MEDIUM" if amount >= 5000.00 or glosa_count > 10 else "LOW"

    def _determine_team(self, amount: float, has_total: bool) -> str:
        """Determine assigned team (fallback if DMN doesn't provide).
        Primary logic in companion DMN (escalation_adjudication).
        """
        if has_total or amount >= 50000.00:
            return "Diretoria Médica e Financeira"
        return "Supervisão de Auditoria" if amount >= 10000.00 else "Coordenação de Glosas"

    def _detect_systemic_issues(self, glosas: List[Dict[str, Any]], has_total: bool) -> tuple[bool, List[Dict[str, Any]]]:
        """Detect systemic issues from recurring patterns."""
        issues = []

        # Check for TOTAL glosa (critical systemic issue)
        if has_total:
            issues.append({
                "issueType": "total_glosa",
                "severity": "CRITICAL",
                "description": "Glosa total detectada - requer revisão urgente de processos",
            })

        # Check for recurring reason codes
        reason_counts = {}
        for glosa in glosas:
            reason = glosa.get("reasonCode", glosa.get("reason_code", "UNKNOWN"))
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        for reason, count in reason_counts.items():
            if count >= 3:  # 3+ glosas with same reason = systemic
                issues.append({
                    "issueType": "recurring_reason",
                    "severity": "HIGH" if count >= 5 else "MEDIUM",
                    "description": f"Motivo recorrente detectado: {reason} ({count} ocorrências)",
                    "reasonCode": reason,
                    "occurrences": count,
                })

        return len(issues) > 0, issues

    def _generate_recommended_actions(
        self, glosas: List[Dict[str, Any]], priority: str, has_total: bool
    ) -> List[str]:
        """Generate recommended actions based on glosa characteristics."""
        actions = []

        # Priority-based actions
        if priority == "CRITICAL":
            actions.append("Revisar urgentemente com diretoria médica e financeira")
            actions.append("Avaliar impacto no fluxo de caixa imediato")

        if has_total:
            actions.append("Analisar causa raiz da glosa total")
            actions.append("Revisar processo de autorização prévia")

        # Type-based actions
        types = {g.get("type", g.get("glosa_type", "")) for g in glosas}
        if "TECHNICAL" in types:
            actions.append("Encaminhar para auditoria médica para revisão técnica")
        if "ADMINISTRATIVE" in types:
            actions.append("Revisar processos administrativos e documentação")

        # Default action
        if not actions:
            actions.append("Revisar documentação e justificativas clínicas")

        return actions

    def _generate_financial_breakdown(self, glosas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate financial impact breakdown by type and reason."""
        from decimal import Decimal

        breakdown = {
            "byType": {},
            "byReason": {},
        }

        for glosa in glosas:
            glosa_type = glosa.get("type", glosa.get("glosa_type", "UNKNOWN"))
            reason = glosa.get("reasonCode", glosa.get("reason_code", "UNKNOWN"))
            amount_str = glosa.get("amountBRL", "0")

            # Parse amount
            try:
                amount = float(str(amount_str).replace(".", "").replace(",", "."))
            except (ValueError, AttributeError):
                amount = 0.0

            # By type
            if glosa_type not in breakdown["byType"]:
                breakdown["byType"][glosa_type] = {"count": 0, "totalAmount": 0.0}
            breakdown["byType"][glosa_type]["count"] += 1
            breakdown["byType"][glosa_type]["totalAmount"] += amount

            # By reason
            if reason not in breakdown["byReason"]:
                breakdown["byReason"][reason] = {"count": 0, "totalAmount": 0.0}
            breakdown["byReason"][reason]["count"] += 1
            breakdown["byReason"][reason]["totalAmount"] += amount

        return breakdown

    def _generate_escalation_summary(
        self,
        claim_id: str,
        reason: str,
        priority: str,
        impact: float,
        count: int,
        team: str,
    ) -> str:
        """Generate human-readable escalation summary in Portuguese."""
        from datetime import datetime

        return f"""
═══════════════════════════════════════════════════════
ESCALAÇÃO PARA REVISÃO MANUAL
═══════════════════════════════════════════════════════

Data: {datetime.now().strftime("%d/%m/%Y %H:%M")}
Conta: {claim_id}
Prioridade: {priority}

Valor Total: R$ {impact:,.2f}
Quantidade de Glosas: {count}

MOTIVO DA ESCALAÇÃO:
{reason}

EQUIPE DESIGNADA:
{team}

═══════════════════════════════════════════════════════
""".strip()
# Backward compatibility alias
EscalateToSupervisorWorker = EscalateToSupervisorWorkerV2
