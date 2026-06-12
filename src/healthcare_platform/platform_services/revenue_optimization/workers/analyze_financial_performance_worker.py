"""
Worker para análise de performance financeira hospitalar.

Analisa receita, custo por caso, margem por convênio/especialidade,
EBITDA e outros indicadores financeiros críticos.

Padrões:
- Protocolo ABC + Stub implementation
- Modelos Pydantic com i18n
- Decoradores @require_tenant e @track_task_execution
- Conformidade LGPD
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import get_dmn_service

logger = get_logger(__name__)

# Métricas Prometheus
financial_analyses_total = Counter(
    "financial_analyses_total",
    "Total de análises financeiras realizadas",
    ["tenant_id", "analysis_type", "status"],
)

financial_duration_seconds = Histogram(
    "financial_analysis_duration_seconds",
    "Duração das análises financeiras",
    ["tenant_id", "analysis_type"],
)


class FinancialAnalysisException(DomainException):
    """    Exceção lançada quando ocorrem erros na análise financeira.
    
        Archetype: FINANCIAL_CALCULATION
        """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="FINANCIAL_ANALYSIS_ERROR",
            bpmn_error_code="FinancialAnalysisError",
            details=details or {},
        )


# ============================================================================
# Modelos Pydantic
# ============================================================================


class AnalyzeFinancialPerformanceInput(BaseModel):
    """Input para análise de performance financeira."""

    analysis_types: list[
        Literal[
            "revenue_analysis",
            "cost_per_case",
            "margin_by_payer",
            "margin_by_specialty",
            "ebitda",
        ]
    ] = Field(..., description=_("Tipos de análises financeiras a realizar"))
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    specialty: str | None = Field(
        None, description=_("Especialidade (filtro opcional)")
    )
    payer: str | None = Field(None, description=_("Convênio (filtro opcional)"))
    include_projections: bool = Field(
        False, description=_("Incluir projeções para o próximo período")
    )


class FinancialMetric(BaseModel):
    """Métrica financeira calculada."""

    analysis_type: str = Field(..., description=_("Tipo de análise"))
    value: float = Field(..., description=_("Valor calculado"))
    currency: str = Field(default="BRL", description=_("Moeda"))
    unit: str | None = Field(None, description=_("Unidade adicional"))
    previous_period_value: float | None = Field(
        None, description=_("Valor do período anterior")
    )
    variance_percent: float | None = Field(
        None, description=_("Variação percentual")
    )
    trend: Literal["up", "down", "stable"] | None = Field(
        None, description=_("Tendência")
    )
    breakdown: dict[str, float] | None = Field(
        None, description=_("Detalhamento por categoria")
    )


class AnalyzeFinancialPerformanceOutput(BaseModel):
    """Output da análise de performance financeira."""

    analysis_id: str = Field(..., description=_("ID único da análise"))
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    metrics: list[FinancialMetric] = Field(..., description=_("Métricas calculadas"))
    specialty: str | None = Field(None, description=_("Especialidade filtrada"))
    payer: str | None = Field(None, description=_("Convênio filtrado"))
    total_revenue: float = Field(..., description=_("Receita total no período"))
    total_cost: float = Field(..., description=_("Custo total no período"))
    net_margin: float = Field(..., description=_("Margem líquida (%)"))
    analyzed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp da análise"),
    )
    duration_ms: int = Field(..., description=_("Duração em milissegundos"))


# ============================================================================
# Protocol e Implementação
# ============================================================================


class AnalyzeFinancialPerformanceProtocol(ABC):
    """Protocolo para análise de performance financeira."""

    @abstractmethod
    async def analyze_revenue(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> FinancialMetric:
        """
        Analisa receita hospitalar no período.

        Args:
            period_start: Início do período
            period_end: Fim do período
            filters: Filtros adicionais

        Returns:
            Métrica de receita
        """
        pass

    @abstractmethod
    async def calculate_cost_per_case(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> FinancialMetric:
        """
        Calcula custo médio por caso.

        Args:
            period_start: Início do período
            period_end: Fim do período
            filters: Filtros adicionais

        Returns:
            Métrica de custo por caso
        """
        pass

    @abstractmethod
    async def analyze_margin_by_payer(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> FinancialMetric:
        """
        Analisa margem por convênio.

        Args:
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Métrica de margem por convênio
        """
        pass

    @abstractmethod
    async def calculate_ebitda(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> FinancialMetric:
        """
        Calcula EBITDA do período.

        Args:
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Métrica de EBITDA
        """
        pass


class AnalyzeFinancialPerformanceStub(AnalyzeFinancialPerformanceProtocol):
    """Implementação stub para análise financeira."""

    async def analyze_revenue(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> FinancialMetric:
        """Analisa receita hospitalar."""
        current_revenue = 8_450_000.00
        previous_revenue = 7_890_000.00
        variance = ((current_revenue - previous_revenue) / previous_revenue) * 100

        return FinancialMetric(
            analysis_type="revenue_analysis",
            value=current_revenue,
            currency="BRL",
            previous_period_value=previous_revenue,
            variance_percent=round(variance, 2),
            trend="up",
            breakdown={
                "SUS": 2_535_000.00,
                "Private": 4_225_000.00,
                "Insurance": 1_690_000.00,
            },
        )

    async def calculate_cost_per_case(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> FinancialMetric:
        """Calcula custo médio por caso."""
        total_cost = 6_340_000.00
        total_cases = 850
        cost_per_case = total_cost / total_cases

        return FinancialMetric(
            analysis_type="cost_per_case",
            value=round(cost_per_case, 2),
            currency="BRL",
            unit="per case",
            previous_period_value=7_250.00,
            variance_percent=3.2,
            trend="up",
        )

    async def analyze_margin_by_payer(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> FinancialMetric:
        """Analisa margem por convênio."""
        weighted_margin = 24.8  # %

        return FinancialMetric(
            analysis_type="margin_by_payer",
            value=weighted_margin,
            unit="%",
            breakdown={
                "SUS": 12.5,
                "Private": 38.2,
                "Insurance": 22.1,
            },
        )

    async def calculate_ebitda(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> FinancialMetric:
        """Calcula EBITDA do período."""
        ebitda = 2_110_000.00
        previous_ebitda = 1_900_000.00
        variance = ((ebitda - previous_ebitda) / previous_ebitda) * 100

        return FinancialMetric(
            analysis_type="ebitda",
            value=ebitda,
            currency="BRL",
            previous_period_value=previous_ebitda,
            variance_percent=round(variance, 2),
            trend="up",
        )


# ============================================================================
# Função de Execução
# ============================================================================


@require_tenant
@track_task_execution
async def execute(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Executa análise de performance financeira.

    Args:
        input_data: Dados de entrada validados

    Returns:
        Resultado da análise

    Raises:
        FinancialAnalysisException: Se houver erro na análise
    """
    tenant = get_required_tenant()
    parsed_input = AnalyzeFinancialPerformanceInput(**input_data)


    analysis_id = (
        f"fin_analysis_{int(parsed_input.period_start.timestamp())}_"
        f"{int(parsed_input.period_end.timestamp())}"
    )

    logger.info(
        _("Iniciando análise de performance financeira"),
        extra={
            "tenant_id": tenant.tenant_code,
            "analysis_id": analysis_id,
            "analysis_types": parsed_input.analysis_types,
        },
    )

    start_time = datetime.utcnow()
    # DMN decision support
    _dmn = get_dmn_service()
    try:
        _dmn_config = _dmn.evaluate(
            tenant_id=tenant.tenant_code,
            category='compliance',
            table_name='ans/comp_ans_003',
            inputs={'analysis_type': parsed_input.analysis_type},
        )
    except (FileNotFoundError, ValueError):
        _dmn_config = {}



    try:
        service = AnalyzeFinancialPerformanceStub()

        filters = {
            "specialty": parsed_input.specialty,
            "payer": parsed_input.payer,
        }

        metrics = []

        for analysis_type in parsed_input.analysis_types:
            if analysis_type == "revenue_analysis":
                metric = await service.analyze_revenue(
                    parsed_input.period_start,
                    parsed_input.period_end,
                    filters,
                )
            elif analysis_type == "cost_per_case":
                metric = await service.calculate_cost_per_case(
                    parsed_input.period_start,
                    parsed_input.period_end,
                    filters,
                )
            elif analysis_type == "margin_by_payer":
                metric = await service.analyze_margin_by_payer(
                    parsed_input.period_start,
                    parsed_input.period_end,
                )
            elif analysis_type == "ebitda":
                metric = await service.calculate_ebitda(
                    parsed_input.period_start,
                    parsed_input.period_end,
                )
            else:
                continue

            metrics.append(metric)

            financial_analyses_total.labels(
                tenant_id=tenant.tenant_code,
                analysis_type=analysis_type,
                status="success",
            ).inc()

        # Calcular totais
        total_revenue = 8_450_000.00
        total_cost = 6_340_000.00
        net_margin = ((total_revenue - total_cost) / total_revenue) * 100

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        output = AnalyzeFinancialPerformanceOutput(
            analysis_id=analysis_id,
            period_start=parsed_input.period_start,
            period_end=parsed_input.period_end,
            metrics=metrics,
            specialty=parsed_input.specialty,
            payer=parsed_input.payer,
            total_revenue=total_revenue,
            total_cost=total_cost,
            net_margin=round(net_margin, 2),
            duration_ms=duration_ms,
        )

        logger.info(
            _("Análise de performance financeira concluída"),
            extra={
                "tenant_id": tenant.tenant_code,
                "analysis_id": analysis_id,
                "metrics_calculated": len(metrics),
                "net_margin": net_margin,
                "duration_ms": duration_ms,
            },
        )

        return output.model_dump()

    except Exception as e:
        logger.error(
            _("Erro na análise de performance financeira"),
            extra={
                "tenant_id": tenant.tenant_code,
                "analysis_id": analysis_id,
                "error": str(e),
            },
            exc_info=True,
        )
        raise FinancialAnalysisException(
            message=_("Falha ao analisar performance financeira"),
            details={"analysis_id": analysis_id, "error": str(e)},
        ) from e


# Topic Kafka
TOPIC = "platform.analyze_financial_performance"
