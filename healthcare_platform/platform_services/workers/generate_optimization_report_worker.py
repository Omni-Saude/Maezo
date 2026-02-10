"""
Generate Optimization Report Worker.

Creates comprehensive monthly optimization reports aggregating all revenue
optimization findings with implementation progress tracking and executive summaries.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
reports_total = Counter(
    "generate_optimization_report_total",
    "Total optimization reports generated",
    ["tenant_id", "report_type"],
)
report_duration_seconds = Histogram(
    "generate_optimization_report_duration_seconds",
    "Duration of report generation",
    ["tenant_id"],
)


class OptimizationReportGenerationError(DomainException):
    """Exception raised when optimization report generation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="OPTIMIZATION_REPORT_GENERATION_ERROR",
            bpmn_error_code="OptimizationReportGenerationError",
            details=details or {},
        )


class GenerateOptimizationReportInput(BaseModel):
    """Input model for generating optimization report."""

    report_period_start: datetime = Field(
        ..., description=_("Data de início do período do relatório")
    )
    report_period_end: datetime = Field(
        ..., description=_("Data de fim do período do relatório")
    )
    include_revenue_leakage: bool = Field(
        True, description=_("Incluir análise de perda de receita")
    )
    include_case_prioritization: bool = Field(
        True, description=_("Incluir priorização de casos")
    )
    include_resource_utilization: bool = Field(
        True, description=_("Incluir utilização de recursos")
    )
    include_payer_performance: bool = Field(
        True, description=_("Incluir performance de operadoras")
    )
    include_revenue_forecast: bool = Field(
        True, description=_("Incluir previsão de receita")
    )
    include_roi_tracking: bool = Field(
        True, description=_("Incluir tracking de ROI")
    )
    executive_summary_only: bool = Field(
        False, description=_("Gerar apenas sumário executivo")
    )


class OptimizationFinding(BaseModel):
    """Individual optimization finding."""

    category: str = Field(..., description=_("Categoria da descoberta"))
    finding: str = Field(..., description=_("Descrição da descoberta"))
    impact: Decimal = Field(..., description=_("Impacto financeiro (R$)"))
    status: str = Field(
        ..., description=_("Status (IDENTIFIED/IN_PROGRESS/IMPLEMENTED/CLOSED)")
    )
    priority: str = Field(..., description=_("Prioridade (HIGH/MEDIUM/LOW)"))
    assigned_to: str | None = Field(None, description=_("Responsável"))
    due_date: datetime | None = Field(None, description=_("Data prevista"))


class ImplementationProgress(BaseModel):
    """Implementation progress tracking."""

    total_findings: int = Field(..., description=_("Total de descobertas"))
    implemented: int = Field(..., description=_("Implementadas"))
    in_progress: int = Field(..., description=_("Em andamento"))
    pending: int = Field(..., description=_("Pendentes"))
    completion_rate: Decimal = Field(..., description=_("Taxa de conclusão (%)"))


class KPISummary(BaseModel):
    """Key performance indicators summary."""

    total_revenue_opportunity: Decimal = Field(
        ..., description=_("Oportunidade total de receita (R$)")
    )
    realized_revenue: Decimal = Field(
        ..., description=_("Receita realizada (R$)")
    )
    cost_savings: Decimal = Field(
        ..., description=_("Economia de custos (R$)")
    )
    efficiency_improvement: Decimal = Field(
        ..., description=_("Melhoria de eficiência (%)")
    )
    roi: Decimal = Field(..., description=_("Retorno sobre investimento (%)"))


class ExecutiveSummary(BaseModel):
    """Executive summary."""

    key_achievements: list[str] = Field(
        ..., description=_("Principais conquistas")
    )
    critical_issues: list[str] = Field(
        ..., description=_("Questões críticas")
    )
    top_recommendations: list[str] = Field(
        ..., description=_("Principais recomendações")
    )
    outlook: str = Field(..., description=_("Perspectiva (POSITIVE/NEUTRAL/CONCERNING)"))


class GenerateOptimizationReportOutput(BaseModel):
    """Output model for optimization report."""

    report_id: str = Field(..., description=_("ID do relatório"))
    report_period: str = Field(..., description=_("Período do relatório"))
    executive_summary: ExecutiveSummary = Field(
        ..., description=_("Sumário executivo")
    )
    kpi_summary: KPISummary = Field(..., description=_("Resumo de KPIs"))
    findings: list[OptimizationFinding] = Field(
        ..., description=_("Descobertas de otimização")
    )
    implementation_progress: ImplementationProgress = Field(
        ..., description=_("Progresso de implementação")
    )
    detailed_sections: dict[str, Any] | None = Field(
        None, description=_("Seções detalhadas (se não executivo apenas)")
    )
    report_generation_timestamp: datetime = Field(
        ..., description=_("Timestamp de geração")
    )
    next_report_due: datetime = Field(
        ..., description=_("Próximo relatório previsto")
    )


class GenerateOptimizationReportProtocol(ABC):
    """Protocol for generating optimization reports."""

    @abstractmethod
    async def execute(
        self, input_data: GenerateOptimizationReportInput
    ) -> GenerateOptimizationReportOutput:
        """
        Generate comprehensive optimization report.

        Args:
            input_data: Report generation parameters

        Returns:
            GenerateOptimizationReportOutput with comprehensive findings

        Raises:
            OptimizationReportGenerationError: If generation fails
        """
        pass


class GenerateOptimizationReportWorkerStub(GenerateOptimizationReportProtocol):
    """Stub implementation for generating optimization reports."""

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self.fhir_client = fhir_client
        self._dmn = get_dmn_service()

    def _collect_findings(
        self, input_data: GenerateOptimizationReportInput
    ) -> list[OptimizationFinding]:
        """Collect optimization findings from various analyses."""
        findings: list[OptimizationFinding] = []

        if input_data.include_revenue_leakage:
            findings.extend([
                OptimizationFinding(
                    category=_("Perda de Receita"),
                    finding=_("Detectados R$ 45.000 em procedimentos não faturados"),
                    impact=Decimal("45000.00"),
                    status="IN_PROGRESS",
                    priority="HIGH",
                    assigned_to="Equipe de Faturamento",
                    due_date=datetime.now(),
                ),
                OptimizationFinding(
                    category=_("Perda de Receita"),
                    finding=_("Materiais não cobrados totalizando R$ 12.500"),
                    impact=Decimal("12500.00"),
                    status="IMPLEMENTED",
                    priority="MEDIUM",
                    assigned_to="Equipe de Faturamento",
                    due_date=None,
                ),
            ])

        if input_data.include_resource_utilization:
            findings.extend([
                OptimizationFinding(
                    category=_("Utilização de Recursos"),
                    finding=_("Centro cirúrgico OR-03 com 65% utilização - potencial de R$ 80k/mês"),
                    impact=Decimal("80000.00"),
                    status="IDENTIFIED",
                    priority="HIGH",
                    assigned_to="Coordenação Cirúrgica",
                    due_date=datetime.now(),
                ),
                OptimizationFinding(
                    category=_("Utilização de Recursos"),
                    finding=_("Redução de 15min no tempo de virada - economia R$ 25k/mês"),
                    impact=Decimal("25000.00"),
                    status="IMPLEMENTED",
                    priority="MEDIUM",
                    assigned_to=None,
                    due_date=None,
                ),
            ])

        if input_data.include_payer_performance:
            findings.extend([
                OptimizationFinding(
                    category=_("Performance de Operadoras"),
                    finding=_("Operadora SUS com 45 dias de atraso médio - impacto no fluxo de caixa"),
                    impact=Decimal("150000.00"),
                    status="IN_PROGRESS",
                    priority="HIGH",
                    assigned_to="Gerência Financeira",
                    due_date=datetime.now(),
                ),
                OptimizationFinding(
                    category=_("Performance de Operadoras"),
                    finding=_("Taxa de glosa de 15% com Operadora X - acima da média"),
                    impact=Decimal("90000.00"),
                    status="IDENTIFIED",
                    priority="HIGH",
                    assigned_to="Auditoria Médica",
                    due_date=datetime.now(),
                ),
            ])

        if input_data.include_case_prioritization:
            findings.append(
                OptimizationFinding(
                    category=_("Priorização de Casos"),
                    finding=_("25 casos de alto valor identificados para processamento prioritário"),
                    impact=Decimal("200000.00"),
                    status="IN_PROGRESS",
                    priority="MEDIUM",
                    assigned_to="Equipe de Faturamento",
                    due_date=datetime.now(),
                )
            )

        return findings

    def _calculate_implementation_progress(
        self, findings: list[OptimizationFinding]
    ) -> ImplementationProgress:
        """Calculate implementation progress."""
        total = len(findings)
        implemented = sum(1 for f in findings if f.status == "IMPLEMENTED")
        in_progress = sum(1 for f in findings if f.status == "IN_PROGRESS")
        pending = sum(1 for f in findings if f.status in ["IDENTIFIED", "CLOSED"])

        completion_rate = (
            (Decimal(implemented) / Decimal(total)) * 100 if total > 0 else Decimal("0")
        )

        return ImplementationProgress(
            total_findings=total,
            implemented=implemented,
            in_progress=in_progress,
            pending=pending,
            completion_rate=completion_rate,
        )

    def _calculate_kpis(
        self, findings: list[OptimizationFinding]
    ) -> KPISummary:
        """Calculate KPI summary."""
        total_opportunity = sum(f.impact for f in findings)
        realized = sum(
            f.impact for f in findings if f.status == "IMPLEMENTED"
        )
        cost_savings = realized * Decimal("0.15")  # Assume 15% cost savings
        efficiency = Decimal("12.5")  # Simulated efficiency improvement
        roi = (
            ((realized - cost_savings) / cost_savings) * 100
            if cost_savings > 0
            else Decimal("0")
        )

        return KPISummary(
            total_revenue_opportunity=total_opportunity,
            realized_revenue=realized,
            cost_savings=cost_savings,
            efficiency_improvement=efficiency,
            roi=roi,
        )

    def _generate_executive_summary(
        self,
        findings: list[OptimizationFinding],
        kpis: KPISummary,
        progress: ImplementationProgress,
    ) -> ExecutiveSummary:
        """Generate executive summary."""
        achievements = []
        if kpis.realized_revenue > 0:
            achievements.append(
                _(
                    f"Recuperados R$ {kpis.realized_revenue:,.2f} em receita através de otimizações"
                )
            )
        if progress.completion_rate > 30:
            achievements.append(
                _(
                    f"{progress.completion_rate:.1f}% das iniciativas de otimização implementadas"
                )
            )
        if kpis.efficiency_improvement > 10:
            achievements.append(
                _(
                    f"Melhoria de {kpis.efficiency_improvement:.1f}% na eficiência operacional"
                )
            )

        critical_issues = []
        high_priority_pending = [
            f for f in findings if f.priority == "HIGH" and f.status != "IMPLEMENTED"
        ]
        if len(high_priority_pending) > 5:
            critical_issues.append(
                _(
                    f"{len(high_priority_pending)} itens de alta prioridade pendentes de implementação"
                )
            )

        high_impact_items = [f for f in findings if f.impact > 50000]
        if len(high_impact_items) > 3:
            critical_issues.append(
                _(
                    f"{len(high_impact_items)} oportunidades de alto impacto (>R$ 50k) identificadas"
                )
            )

        recommendations = [
            _("Priorizar implementação de itens de alto impacto financeiro"),
            _("Acelerar recuperação de receita perdida através de faturamento complementar"),
            _("Estabelecer força-tarefa para redução de glosas com operadoras problemáticas"),
        ]

        outlook = "POSITIVE" if kpis.roi > 100 else "NEUTRAL" if kpis.roi > 50 else "CONCERNING"

        return ExecutiveSummary(
            key_achievements=achievements,
            critical_issues=critical_issues,
            top_recommendations=recommendations,
            outlook=outlook,
        )

    def _generate_detailed_sections(
        self, input_data: GenerateOptimizationReportInput
    ) -> dict[str, Any]:
        """Generate detailed report sections."""
        sections = {}

        if input_data.include_revenue_leakage:
            sections["revenue_leakage"] = {
                "total_leakage": "57500.00",
                "items_count": 47,
                "recovery_rate": "75.0",
            }

        if input_data.include_resource_utilization:
            sections["resource_utilization"] = {
                "or_utilization": "78.5",
                "bed_occupancy": "82.3",
                "staff_productivity": "85.1",
            }

        if input_data.include_payer_performance:
            sections["payer_performance"] = {
                "best_performer": "Unimed",
                "worst_performer": "SUS",
                "average_payment_days": "38.5",
            }

        if input_data.include_revenue_forecast:
            sections["revenue_forecast"] = {
                "next_month_forecast": "2450000.00",
                "trend": "GROWING",
                "confidence": "85.5",
            }

        return sections

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: GenerateOptimizationReportInput
    ) -> GenerateOptimizationReportOutput:
        """Execute optimization report generation."""
        tenant_id = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.id,
                category='compliance',
                table_name='audit/comp_audit_003',
                inputs={'report_type': input_data.report_type},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        logger.info(
            "Generating optimization report",
            extra={
                "tenant_id": tenant_id,
                "period_start": input_data.report_period_start.isoformat(),
                "period_end": input_data.report_period_end.isoformat(),
            },
        )

        with report_duration_seconds.labels(tenant_id=tenant_id).time():
            try:
                # Collect all findings
                findings = self._collect_findings(input_data)

                # Calculate metrics
                progress = self._calculate_implementation_progress(findings)
                kpis = self._calculate_kpis(findings)
                executive_summary = self._generate_executive_summary(
                    findings, kpis, progress
                )

                # Generate detailed sections if not executive only
                detailed_sections = None
                if not input_data.executive_summary_only:
                    detailed_sections = self._generate_detailed_sections(input_data)

                # Generate report ID
                report_id = f"OPT-{input_data.report_period_start.strftime('%Y%m')}-{hashlib.md5(tenant_id.encode()).hexdigest()[:8].upper()}"

                # Calculate next report due date (30 days)
                next_due = datetime.now().replace(day=1) + timedelta(days=32)
                next_due = next_due.replace(day=1)

                from datetime import timedelta
                period_str = f"{input_data.report_period_start.strftime('%Y-%m-%d')} a {input_data.report_period_end.strftime('%Y-%m-%d')}"

                result = GenerateOptimizationReportOutput(
                    report_id=report_id,
                    report_period=period_str,
                    executive_summary=executive_summary,
                    kpi_summary=kpis,
                    findings=findings,
                    implementation_progress=progress,
                    detailed_sections=detailed_sections,
                    report_generation_timestamp=datetime.now(),
                    next_report_due=next_due,
                )

                reports_total.labels(
                    tenant_id=tenant_id,
                    report_type="executive" if input_data.executive_summary_only else "full",
                ).inc()

                logger.info(
                    "Optimization report generated",
                    extra={
                        "tenant_id": tenant_id,
                        "report_id": report_id,
                        "findings_count": len(findings),
                        "total_opportunity": float(kpis.total_revenue_opportunity),
                    },
                )

                return result

            except Exception as e:
                logger.error(
                    "Optimization report generation failed",
                    extra={"tenant_id": tenant_id, "error": str(e)},
                    exc_info=True,
                )
                raise OptimizationReportGenerationError(
                    _("Falha ao gerar relatório de otimização"),
                    details={"error": str(e)},
                ) from e


# Topic constant for Camunda message correlation
TOPIC = "generate-optimization-report"
