"""
Escalate to Supervisor Worker

Sets up human task for manual review of complex or high-impact glosas.
This is a HUMAN TASK worker that prepares escalation packages for supervisor review.

Topic: escalate-to-supervisor
"""

from datetime import datetime, timezone
from typing import Any
import uuid

from healthcare_platform.revenue_cycle.billing.workers.base import WorkerResult, worker
from healthcare_platform.revenue_cycle.glosa.workers.base import GlosaWorkerMixin
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.enums import GlosaType
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


# Escalation thresholds
ESCALATION_THRESHOLD_CRITICAL = 50_000.00  # R$ 50,000
ESCALATION_THRESHOLD_HIGH = 10_000.00  # R$ 10,000
ESCALATION_THRESHOLD_MEDIUM = 5_000.00  # R$ 5,000
ESCALATION_THRESHOLD_GLOSA_COUNT = 5  # Number of glosas


@worker(topic="escalate-to-supervisor", max_jobs=3, lock_duration=15000)
class EscalateToSupervisorWorker(GlosaWorkerMixin):
    """
    Worker that prepares escalation package for human supervisor review.

    This is a HUMAN TASK worker - it does not make automated decisions.
    Instead, it sets up structured data for manual review.

    Escalation criteria:
    - Financial impact > R$ 10,000
    - More than 5 glosas in single claim
    - TOTAL type glosa (full claim denial)
    - Systemic issues detected (recurring patterns)

    Priority levels:
    - CRITICAL: > R$ 50,000
    - HIGH: > R$ 10,000
    - MEDIUM: > R$ 5,000
    - LOW: < R$ 5,000

        Archetype: FINANCIAL_CALCULATION
    """

    def __init__(self) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()

    def _evaluate_glosa_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate glosa_prevention DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='glosa_prevention',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    def _evaluate_appeal_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate revenue_recovery DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='revenue_recovery',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """
        Prepare escalation package for supervisor review.

        Args:
            job: Zeebe job instance
            variables: Task variables containing:
                - analyzedGlosas: List of analyzed glosa dicts
                - totalImpactBRL: Total financial impact string
                - claimId: Claim identifier
                - escalationReason: Reason for escalation

        Returns:
            WorkerResult with escalation package and human task flag
        """
        claim_id = variables.get("claimId", "UNKNOWN")
        logger.info(
            _("Preparando escalação para supervisor - Conta {claim_id}").format(
                claim_id=claim_id
            )
        )

        try:
            # Parse input
            analyzed_glosas = variables.get("analyzedGlosas", [])
            total_impact_str = variables.get("totalImpactBRL", "0,00")
            escalation_reason = variables.get("escalationReason", _("Não especificado"))

            total_impact = self._parse_money(total_impact_str)
            glosa_count = len(analyzed_glosas)

            # Generate escalation ID
            escalation_id = f"ESC-{claim_id}-{uuid.uuid4().hex[:8].upper()}"
            escalation_date = datetime.now(timezone.utc)

            # Determine priority based on impact and count
            priority = self._determine_priority(total_impact.amount, glosa_count)

            # Determine assigned team
            assigned_team = self._determine_team(total_impact.amount, analyzed_glosas)

            # Build escalation summary in Portuguese
            escalation_summary = self._build_escalation_summary(
                claim_id=claim_id,
                total_impact=total_impact,
                glosa_count=glosa_count,
                priority=priority,
                escalation_reason=escalation_reason,
                escalation_date=escalation_date,
            )

            # Analyze glosas for patterns
            systemic_issues = self._detect_systemic_issues(analyzed_glosas)

            # Build escalation package
            escalation_package = {
                "escalationId": escalation_id,
                "claimId": claim_id,
                "escalationDate": escalation_date.isoformat(),
                "priority": priority,
                "assignedTeam": assigned_team,
                "totalImpact": total_impact.format_brl(),
                "glosaCount": glosa_count,
                "escalationReason": escalation_reason,
                "glosasSummary": self._summarize_glosas(analyzed_glosas),
                "systemicIssues": systemic_issues,
                "recommendedActions": self._recommend_actions(
                    analyzed_glosas, systemic_issues
                ),
                "financialImpactBreakdown": self._breakdown_financial_impact(
                    analyzed_glosas
                ),
            }

            logger.info(
                _(
                    "Escalação criada: {esc_id}, prioridade {priority}, "
                    "equipe {team}, valor R$ {amount}"
                ).format(
                    esc_id=escalation_id,
                    priority=priority,
                    team=assigned_team,
                    amount=total_impact.format_brl(),
                )
            )

            return WorkerResult(
                variables={
                    "escalationId": escalation_id,
                    "escalationPackage": escalation_package,
                    "assignedTeam": assigned_team,
                    "priority": priority,
                    "escalationSummary": escalation_summary,
                    "requiresHumanDecision": True,
                    "humanTaskType": "supervisor_review",
                    "systemicIssuesDetected": len(systemic_issues) > 0,
                },
                success=True,
            )

        except Exception as e:
            logger.error(
                _("Erro ao preparar escalação: {error}").format(error=str(e))
            )
            return WorkerResult(
                variables={
                    "error": str(e),
                    "escalationId": "",
                    "requiresHumanDecision": True,
                },
                success=False,
            )

    def _determine_priority(self, amount: float, glosa_count: int) -> str:
        """Determine escalation priority based on impact."""
        if amount >= ESCALATION_THRESHOLD_CRITICAL:
            return "CRITICAL"
        elif amount >= ESCALATION_THRESHOLD_HIGH:
            return "HIGH"
        elif amount >= ESCALATION_THRESHOLD_MEDIUM or glosa_count > 10:
            return "MEDIUM"
        else:
            return "LOW"

    def _determine_team(self, amount: float, glosas: list[dict]) -> str:
        """Determine which team should handle the escalation."""
        # Check for TOTAL glosas
        has_total_glosa = any(
            g.get("type") == GlosaType.TOTAL.value for g in glosas
        )

        if has_total_glosa or amount >= ESCALATION_THRESHOLD_CRITICAL:
            return _("Diretoria Médica e Financeira")
        elif amount >= ESCALATION_THRESHOLD_HIGH:
            return _("Supervisão de Auditoria")
        else:
            return _("Coordenação de Glosas")

    def _build_escalation_summary(
        self,
        claim_id: str,
        total_impact: Any,
        glosa_count: int,
        priority: str,
        escalation_reason: str,
        escalation_date: datetime,
    ) -> str:
        """Build human-readable escalation summary in Portuguese."""
        priority_pt = {
            "CRITICAL": "CRÍTICA",
            "HIGH": "ALTA",
            "MEDIUM": "MÉDIA",
            "LOW": "BAIXA",
        }.get(priority, priority)

        return _(
            "ESCALAÇÃO PARA REVISÃO MANUAL\n\n"
            "Data: {date}\n"
            "Conta: {claim_id}\n"
            "Prioridade: {priority}\n"
            "Valor Total: R$ {amount}\n"
            "Quantidade de Glosas: {count}\n\n"
            "MOTIVO DA ESCALAÇÃO:\n"
            "{reason}\n\n"
            "Esta conta requer análise manual devido à complexidade, "
            "impacto financeiro ou necessidade de decisão especializada.\n\n"
            "Por favor, revise os detalhes completos no pacote de escalação "
            "e tome as ações apropriadas."
        ).format(
            date=escalation_date.strftime("%d/%m/%Y %H:%M"),
            claim_id=claim_id,
            priority=priority_pt,
            amount=total_impact.format_brl(),
            count=glosa_count,
            reason=escalation_reason,
        )

    def _detect_systemic_issues(self, glosas: list[dict]) -> list[dict]:
        """Detect patterns that may indicate systemic issues."""
        issues = []

        # Check for recurring reason codes
        reason_counts = {}
        for glosa in glosas:
            reason = glosa.get("reasonCode", "UNKNOWN")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        for reason, count in reason_counts.items():
            if count >= 3:
                issues.append(
                    {
                        "issueType": "recurring_reason",
                        "description": _(
                            "Motivo recorrente: {reason} ({count} ocorrências)"
                        ).format(
                            reason=self._get_glosa_reason_display(reason), count=count
                        ),
                        "severity": "HIGH" if count >= 5 else "MEDIUM",
                        "recommendation": _(
                            "Investigar processo relacionado a {reason}"
                        ).format(reason=self._get_glosa_reason_display(reason)),
                    }
                )

        # Check for TOTAL glosa
        has_total = any(g.get("type") == GlosaType.TOTAL.value for g in glosas)
        if has_total:
            issues.append(
                {
                    "issueType": "total_glosa",
                    "description": _("Glosa total detectada - conta inteira negada"),
                    "severity": "CRITICAL",
                    "recommendation": _(
                        "Revisão urgente com equipe médica e jurídica"
                    ),
                }
            )

        return issues

    def _summarize_glosas(self, glosas: list[dict]) -> list[dict]:
        """Create summary of glosas for quick review."""
        summary = []
        for glosa in glosas:
            summary.append(
                {
                    "type": glosa.get("type", ""),
                    "reasonCode": glosa.get("reasonCode", ""),
                    "reasonDisplay": self._get_glosa_reason_display(
                        glosa.get("reasonCode", "")
                    ),
                    "amount": glosa.get("amountBRL", "0,00"),
                    "severity": glosa.get("severityScore", 0),
                }
            )
        return summary

    def _recommend_actions(
        self, glosas: list[dict], systemic_issues: list[dict]
    ) -> list[str]:
        """Recommend actions based on glosa analysis."""
        actions = []

        # Standard action
        actions.append(_("Revisar documentação completa da conta"))

        # Based on systemic issues
        if any(i.get("severity") == "CRITICAL" for i in systemic_issues):
            actions.append(_("Convocar reunião de emergência com equipe responsável"))

        # Based on glosa types
        has_technical = any(g.get("type") == GlosaType.TECHNICAL.value for g in glosas)
        if has_technical:
            actions.append(_("Solicitar parecer da auditoria médica"))

        has_admin = any(
            g.get("type") == GlosaType.ADMINISTRATIVE.value for g in glosas
        )
        if has_admin:
            actions.append(_("Verificar processos administrativos e documentação"))

        # Based on count
        if len(glosas) > 10:
            actions.append(_("Investigar possível falha sistêmica no processo"))

        return actions

    def _breakdown_financial_impact(self, glosas: list[dict]) -> dict:
        """Break down financial impact by type and reason."""
        breakdown = {"byType": {}, "byReason": {}}

        for glosa in glosas:
            glosa_type = glosa.get("type", "UNKNOWN")
            reason = glosa.get("reasonCode", "UNKNOWN")
            amount = self._parse_money(glosa.get("amountBRL", "0,00"))

            # By type
            if glosa_type not in breakdown["byType"]:
                breakdown["byType"][glosa_type] = {"count": 0, "amount": "0,00"}
            breakdown["byType"][glosa_type]["count"] += 1
            current_amount = self._parse_money(
                breakdown["byType"][glosa_type]["amount"]
            )
            breakdown["byType"][glosa_type]["amount"] = (
                current_amount + amount
            ).format_brl()

            # By reason
            if reason not in breakdown["byReason"]:
                breakdown["byReason"][reason] = {"count": 0, "amount": "0,00"}
            breakdown["byReason"][reason]["count"] += 1
            current_amount = self._parse_money(breakdown["byReason"][reason]["amount"])
            breakdown["byReason"][reason]["amount"] = (
                current_amount + amount
            ).format_brl()

        return breakdown
