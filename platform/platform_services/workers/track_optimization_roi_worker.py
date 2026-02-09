"""
Track Optimization ROI Worker.

Measures actual revenue impact of implemented optimizations, calculates payback
periods, and performs trend analysis for continuous improvement tracking.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.integrations.fhir_client import FHIRClientProtocol
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)

# Prometheus metrics
roi_calculations_total = Counter(
    "track_optimization_roi_calculations_total",
    "Total ROI calculations performed",
    ["tenant_id", "optimization_type"],
)
roi_duration_seconds = Histogram(
    "track_optimization_roi_duration_seconds",
    "Duration of ROI tracking",
    ["tenant_id"],
)


class OptimizationROITrackingError(DomainException):
    """Exception raised when optimization ROI tracking fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="OPTIMIZATION_ROI_TRACKING_ERROR",
            bpmn_error_code="OptimizationROITrackingError",
            details=details or {},
        )


class TrackOptimizationROIInput(BaseModel):
    """Input model for tracking optimization ROI."""

    tracking_period_months: int = Field(
        6, description=_("Período de tracking em meses")
    )
    optimization_ids: list[str] | None = Field(
        None, description=_("IDs de otimizações específicas (None = todas)")
    )
    include_revenue_impact: bool = Field(
        True, description=_("Incluir análise de impacto na receita")
    )
    include_cost_savings: bool = Field(
        True, description=_("Incluir análise de economia de custos")
    )
    include_efficiency_gains: bool = Field(
        True, description=_("Incluir análise de ganhos de eficiência")
    )
    calculate_payback_period: bool = Field(
        True, description=_("Calcular período de payback")
    )
    trend_analysis: bool = Field(
        True, description=_("Incluir análise de tendências")
    )


class OptimizationImpact(BaseModel):
    """Individual optimization impact tracking."""

    optimization_id: str = Field(..., description=_("ID da otimização"))
    optimization_name: str = Field(..., description=_("Nome da otimização"))
    implementation_date: datetime = Field(
        ..., description=_("Data de implementação")
    )
    category: str = Field(..., description=_("Categoria da otimização"))
    initial_investment: Decimal = Field(
        ..., description=_("Investimento inicial (R$)")
    )
    cumulative_revenue_impact: Decimal = Field(
        ..., description=_("Impacto acumulado na receita (R$)")
    )
    cumulative_cost_savings: Decimal = Field(
        ..., description=_("Economia acumulada de custos (R$)")
    )
    efficiency_improvement: Decimal = Field(
        ..., description=_("Melhoria de eficiência (%)")
    )
    roi_percentage: Decimal = Field(
        ..., description=_("ROI percentual (%)")
    )
    payback_period_months: Decimal | None = Field(
        None, description=_("Período de payback (meses)")
    )
    status: str = Field(
        ..., description=_("Status (POSITIVE/NEUTRAL/NEGATIVE)")
    )


class MonthlyTrend(BaseModel):
    """Monthly trend data point."""

    month: str = Field(..., description=_("Mês (YYYY-MM)"))
    total_revenue_impact: Decimal = Field(
        ..., description=_("Impacto total na receita (R$)")
    )
    total_cost_savings: Decimal = Field(
        ..., description=_("Economia total de custos (R$)")
    )
    cumulative_roi: Decimal = Field(
        ..., description=_("ROI acumulado (%)")
    )
    active_optimizations: int = Field(
        ..., description=_("Otimizações ativas")
    )


class CategoryROI(BaseModel):
    """ROI summary by optimization category."""

    category: str = Field(..., description=_("Categoria"))
    total_investment: Decimal = Field(
        ..., description=_("Investimento total (R$)")
    )
    total_return: Decimal = Field(
        ..., description=_("Retorno total (R$)")
    )
    roi_percentage: Decimal = Field(
        ..., description=_("ROI percentual (%)")
    )
    optimization_count: int = Field(
        ..., description=_("Quantidade de otimizações")
    )


class TrackOptimizationROIOutput(BaseModel):
    """Output model for optimization ROI tracking."""

    optimization_impacts: list[OptimizationImpact] = Field(
        ..., description=_("Impactos individuais de otimizações")
    )
    overall_roi: Decimal = Field(
        ..., description=_("ROI geral do programa (%)")
    )
    total_investment: Decimal = Field(
        ..., description=_("Investimento total (R$)")
    )
    total_return: Decimal = Field(
        ..., description=_("Retorno total (R$)")
    )
    average_payback_months: Decimal = Field(
        ..., description=_("Período médio de payback (meses)")
    )
    category_roi: list[CategoryROI] = Field(
        ..., description=_("ROI por categoria")
    )
    monthly_trends: list[MonthlyTrend] | None = Field(
        None, description=_("Tendências mensais")
    )
    best_performing_optimization: str = Field(
        ..., description=_("Otimização com melhor performance")
    )
    recommendations: list[str] = Field(
        ..., description=_("Recomendações para melhoria")
    )
    tracking_timestamp: datetime = Field(
        ..., description=_("Timestamp do tracking")
    )


class TrackOptimizationROIProtocol(ABC):
    """Protocol for tracking optimization ROI."""

    @abstractmethod
    async def execute(
        self, input_data: TrackOptimizationROIInput
    ) -> TrackOptimizationROIOutput:
        """
        Track ROI of implemented optimizations.

        Args:
            input_data: ROI tracking parameters

        Returns:
            TrackOptimizationROIOutput with comprehensive ROI analysis

        Raises:
            OptimizationROITrackingError: If tracking fails
        """
        pass


class TrackOptimizationROIWorkerStub(TrackOptimizationROIProtocol):
    """Stub implementation for tracking optimization ROI."""

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self.fhir_client = fhir_client

    def _get_optimization_list(
        self, optimization_ids: list[str] | None
    ) -> list[tuple[str, str, str, datetime, Decimal]]:
        """Get list of optimizations to track."""
        # (id, name, category, impl_date, investment)
        all_optimizations = [
            (
                "OPT001",
                "Redução de tempo de virada OR",
                _("Utilização de Recursos"),
                datetime.now() - timedelta(days=120),
                Decimal("15000.00"),
            ),
            (
                "OPT002",
                "Recuperação de procedimentos não faturados",
                _("Perda de Receita"),
                datetime.now() - timedelta(days=90),
                Decimal("5000.00"),
            ),
            (
                "OPT003",
                "Otimização de processo de autorização",
                _("Performance de Operadoras"),
                datetime.now() - timedelta(days=60),
                Decimal("10000.00"),
            ),
            (
                "OPT004",
                "Implementação de sistema de priorização",
                _("Priorização de Casos"),
                datetime.now() - timedelta(days=45),
                Decimal("25000.00"),
            ),
            (
                "OPT005",
                "Melhoria de gestão de estoque de materiais",
                _("Perda de Receita"),
                datetime.now() - timedelta(days=30),
                Decimal("8000.00"),
            ),
        ]

        if optimization_ids:
            return [opt for opt in all_optimizations if opt[0] in optimization_ids]
        return all_optimizations

    def _calculate_impact(
        self,
        opt_id: str,
        category: str,
        impl_date: datetime,
        investment: Decimal,
        months_active: int,
    ) -> OptimizationImpact:
        """Calculate impact for a single optimization."""
        # Simulate different impact levels based on category
        if category == _("Perda de Receita"):
            monthly_revenue = Decimal("15000.00")
            monthly_savings = Decimal("2000.00")
            efficiency = Decimal("8.5")
        elif category == _("Utilização de Recursos"):
            monthly_revenue = Decimal("25000.00")
            monthly_savings = Decimal("5000.00")
            efficiency = Decimal("12.0")
        elif category == _("Performance de Operadoras"):
            monthly_revenue = Decimal("10000.00")
            monthly_savings = Decimal("3000.00")
            efficiency = Decimal("6.5")
        else:
            monthly_revenue = Decimal("8000.00")
            monthly_savings = Decimal("1500.00")
            efficiency = Decimal("5.0")

        cumulative_revenue = monthly_revenue * months_active
        cumulative_savings = monthly_savings * months_active
        total_return = cumulative_revenue + cumulative_savings

        roi = (
            ((total_return - investment) / investment) * 100
            if investment > 0
            else Decimal("0")
        )

        # Calculate payback period
        monthly_return = monthly_revenue + monthly_savings
        payback = (
            investment / monthly_return
            if monthly_return > 0
            else None
        )

        status = "POSITIVE" if roi > 50 else "NEUTRAL" if roi > 0 else "NEGATIVE"

        # Get optimization name from the list
        opt_name = f"Otimização {opt_id}"

        return OptimizationImpact(
            optimization_id=opt_id,
            optimization_name=opt_name,
            implementation_date=impl_date,
            category=category,
            initial_investment=investment,
            cumulative_revenue_impact=cumulative_revenue,
            cumulative_cost_savings=cumulative_savings,
            efficiency_improvement=efficiency,
            roi_percentage=roi,
            payback_period_months=payback,
            status=status,
        )

    def _calculate_category_roi(
        self, impacts: list[OptimizationImpact]
    ) -> list[CategoryROI]:
        """Calculate ROI by category."""
        categories: dict[str, dict[str, Any]] = {}

        for impact in impacts:
            if impact.category not in categories:
                categories[impact.category] = {
                    "investment": Decimal("0"),
                    "return": Decimal("0"),
                    "count": 0,
                }

            cat = categories[impact.category]
            cat["investment"] += impact.initial_investment
            cat["return"] += (
                impact.cumulative_revenue_impact + impact.cumulative_cost_savings
            )
            cat["count"] += 1

        category_rois = []
        for category, data in categories.items():
            roi = (
                ((data["return"] - data["investment"]) / data["investment"]) * 100
                if data["investment"] > 0
                else Decimal("0")
            )

            category_rois.append(
                CategoryROI(
                    category=category,
                    total_investment=data["investment"],
                    total_return=data["return"],
                    roi_percentage=roi,
                    optimization_count=data["count"],
                )
            )

        return category_rois

    def _generate_monthly_trends(
        self, tracking_months: int, impacts: list[OptimizationImpact]
    ) -> list[MonthlyTrend]:
        """Generate monthly trend data."""
        trends = []
        current_date = datetime.now()

        for i in range(tracking_months, 0, -1):
            month_date = current_date - timedelta(days=30 * i)
            month_str = month_date.strftime("%Y-%m")

            # Simulate progressive growth
            month_factor = Decimal(str(tracking_months - i + 1)) / Decimal(
                str(tracking_months)
            )

            total_revenue = sum(
                impact.cumulative_revenue_impact * month_factor / tracking_months
                for impact in impacts
            )
            total_savings = sum(
                impact.cumulative_cost_savings * month_factor / tracking_months
                for impact in impacts
            )

            total_investment = sum(impact.initial_investment for impact in impacts)
            cumulative_return = total_revenue + total_savings
            cumulative_roi = (
                ((cumulative_return - total_investment) / total_investment) * 100
                if total_investment > 0
                else Decimal("0")
            )

            # Count active optimizations for that month
            active = sum(
                1 for impact in impacts if impact.implementation_date <= month_date
            )

            trends.append(
                MonthlyTrend(
                    month=month_str,
                    total_revenue_impact=total_revenue,
                    total_cost_savings=total_savings,
                    cumulative_roi=cumulative_roi,
                    active_optimizations=active,
                )
            )

        return trends

    def _generate_recommendations(
        self,
        impacts: list[OptimizationImpact],
        category_roi: list[CategoryROI],
    ) -> list[str]:
        """Generate recommendations for improvement."""
        recommendations = []

        # Identify best performing category
        if category_roi:
            best_category = max(category_roi, key=lambda x: x.roi_percentage)
            recommendations.append(
                _(
                    f"Priorizar investimentos em categoria '{best_category.category}' (ROI: {best_category.roi_percentage:.1f}%)"
                )
            )

        # Identify slow performers
        slow_performers = [
            impact
            for impact in impacts
            if impact.roi_percentage < 50 and impact.status != "NEGATIVE"
        ]
        if slow_performers:
            recommendations.append(
                _(
                    f"Revisar {len(slow_performers)} otimização(ões) com ROI abaixo de 50%"
                )
            )

        # Payback analysis
        long_payback = [
            impact
            for impact in impacts
            if impact.payback_period_months and impact.payback_period_months > 12
        ]
        if long_payback:
            recommendations.append(
                _(
                    f"Avaliar {len(long_payback)} iniciativa(s) com payback >12 meses"
                )
            )

        # General recommendations
        recommendations.append(
            _("Documentar e compartilhar melhores práticas de otimizações bem-sucedidas")
        )
        recommendations.append(
            _("Estabelecer revisão trimestral de ROI de todas otimizações ativas")
        )

        return recommendations

    @require_tenant
    @track_task_execution
    async def execute(
        self, input_data: TrackOptimizationROIInput
    ) -> TrackOptimizationROIOutput:
        """Execute optimization ROI tracking."""
        tenant_id = get_required_tenant()
        logger.info(
            "Tracking optimization ROI",
            extra={
                "tenant_id": tenant_id,
                "tracking_months": input_data.tracking_period_months,
            },
        )

        with roi_duration_seconds.labels(tenant_id=tenant_id).time():
            try:
                optimizations = self._get_optimization_list(input_data.optimization_ids)
                impacts: list[OptimizationImpact] = []

                for opt_id, opt_name, category, impl_date, investment in optimizations:
                    # Calculate months active
                    months_active = max(
                        1,
                        int((datetime.now() - impl_date).days / 30),
                    )
                    months_active = min(months_active, input_data.tracking_period_months)

                    impact = self._calculate_impact(
                        opt_id, category, impl_date, investment, months_active
                    )
                    impact.optimization_name = opt_name  # Update with actual name
                    impacts.append(impact)

                    roi_calculations_total.labels(
                        tenant_id=tenant_id, optimization_type=category
                    ).inc()

                # Calculate aggregates
                total_investment = sum(i.initial_investment for i in impacts)
                total_return = sum(
                    i.cumulative_revenue_impact + i.cumulative_cost_savings
                    for i in impacts
                )
                overall_roi = (
                    ((total_return - total_investment) / total_investment) * 100
                    if total_investment > 0
                    else Decimal("0")
                )

                # Calculate average payback
                valid_paybacks = [
                    i.payback_period_months
                    for i in impacts
                    if i.payback_period_months is not None
                ]
                average_payback = (
                    sum(valid_paybacks) / len(valid_paybacks)
                    if valid_paybacks
                    else Decimal("0")
                )

                # Category analysis
                category_roi = self._calculate_category_roi(impacts)

                # Trends
                monthly_trends = None
                if input_data.trend_analysis:
                    monthly_trends = self._generate_monthly_trends(
                        input_data.tracking_period_months, impacts
                    )

                # Best performer
                best_optimization = (
                    max(impacts, key=lambda x: x.roi_percentage).optimization_name
                    if impacts
                    else "N/A"
                )

                # Recommendations
                recommendations = self._generate_recommendations(impacts, category_roi)

                result = TrackOptimizationROIOutput(
                    optimization_impacts=impacts,
                    overall_roi=overall_roi,
                    total_investment=total_investment,
                    total_return=total_return,
                    average_payback_months=average_payback,
                    category_roi=category_roi,
                    monthly_trends=monthly_trends,
                    best_performing_optimization=best_optimization,
                    recommendations=recommendations,
                    tracking_timestamp=datetime.now(),
                )

                logger.info(
                    "Optimization ROI tracking completed",
                    extra={
                        "tenant_id": tenant_id,
                        "optimizations_tracked": len(impacts),
                        "overall_roi": float(overall_roi),
                        "total_return": float(total_return),
                    },
                )

                return result

            except Exception as e:
                logger.error(
                    "Optimization ROI tracking failed",
                    extra={"tenant_id": tenant_id, "error": str(e)},
                    exc_info=True,
                )
                raise OptimizationROITrackingError(
                    _("Falha ao rastrear ROI de otimizações"),
                    details={"error": str(e)},
                ) from e


# Topic constant for Camunda message correlation
TOPIC = "track-optimization-roi"
