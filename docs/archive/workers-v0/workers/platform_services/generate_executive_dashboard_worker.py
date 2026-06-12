"""
Worker para geração de dashboard executivo (C-level KPIs).

Compila indicadores-chave para diretoria: receita, ocupação, qualidade clínica,
mix de convênios, case mix index e outros KPIs estratégicos.

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
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Métricas Prometheus
dashboard_generations_total = Counter(
    "dashboard_generations_total",
    "Total de dashboards executivos gerados",
    ["tenant_id", "dashboard_type", "status"],
)

dashboard_duration_seconds = Histogram(
    "dashboard_generation_duration_seconds",
    "Duração da geração de dashboards executivos",
    ["tenant_id", "dashboard_type"],
)


class DashboardGenerationException(DomainException):
    """Exceção lançada quando ocorrem erros na geração do dashboard."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="DashboardGenerationError",
            details=details or {},
        )


# ============================================================================
# Modelos Pydantic
# ============================================================================


class GenerateExecutiveDashboardInput(BaseModel):
    """Input para geração de dashboard executivo."""

    dashboard_type: Literal["monthly", "quarterly", "yearly", "realtime"] = Field(
        ..., description=_("Tipo de dashboard executivo")
    )
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    include_trends: bool = Field(
        True, description=_("Incluir análise de tendências")
    )
    include_forecasts: bool = Field(
        True, description=_("Incluir projeções futuras")
    )
    compare_to_budget: bool = Field(
        True, description=_("Comparar com orçamento planejado")
    )


class ExecutiveKPI(BaseModel):
    """KPI executivo individual."""

    kpi_name: str = Field(..., description=_("Nome do KPI"))
    kpi_category: Literal["financial", "operational", "clinical", "strategic"] = (
        Field(..., description=_("Categoria do KPI"))
    )
    value: float = Field(..., description=_("Valor atual"))
    unit: str = Field(..., description=_("Unidade de medida"))
    target: float | None = Field(None, description=_("Meta estabelecida"))
    variance_from_target: float | None = Field(
        None, description=_("Variação da meta (%)")
    )
    previous_period: float | None = Field(
        None, description=_("Valor do período anterior")
    )
    trend: Literal["up", "down", "stable"] | None = Field(
        None, description=_("Tendência")
    )
    status: Literal["good", "warning", "critical"] = Field(
        ..., description=_("Status do indicador")
    )


class GenerateExecutiveDashboardOutput(BaseModel):
    """Output da geração de dashboard executivo."""

    dashboard_id: str = Field(..., description=_("ID único do dashboard"))
    dashboard_type: str = Field(..., description=_("Tipo de dashboard"))
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    kpis: list[ExecutiveKPI] = Field(..., description=_("KPIs executivos"))
    summary: dict[str, Any] = Field(
        ..., description=_("Resumo executivo com destaques")
    )
    alerts: list[str] = Field(
        default_factory=list, description=_("Alertas críticos para atenção")
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp da geração"),
    )
    duration_ms: int = Field(..., description=_("Duração em milissegundos"))


# ============================================================================
# Protocol e Implementação
# ============================================================================


class GenerateExecutiveDashboardProtocol(ABC):
    """Protocolo para geração de dashboard executivo."""

    @abstractmethod
    async def collect_financial_kpis(
        self, period_start: datetime, period_end: datetime
    ) -> list[ExecutiveKPI]:
        """
        Coleta KPIs financeiros.

        Args:
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Lista de KPIs financeiros
        """
        pass

    @abstractmethod
    async def collect_operational_kpis(
        self, period_start: datetime, period_end: datetime
    ) -> list[ExecutiveKPI]:
        """
        Coleta KPIs operacionais.

        Args:
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Lista de KPIs operacionais
        """
        pass

    @abstractmethod
    async def collect_clinical_kpis(
        self, period_start: datetime, period_end: datetime
    ) -> list[ExecutiveKPI]:
        """
        Coleta KPIs clínicos de qualidade.

        Args:
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Lista de KPIs clínicos
        """
        pass

    @abstractmethod
    async def generate_executive_summary(
        self, kpis: list[ExecutiveKPI]
    ) -> dict[str, Any]:
        """
        Gera resumo executivo com principais destaques.

        Args:
            kpis: Lista de todos os KPIs

        Returns:
            Resumo executivo estruturado
        """
        pass


class GenerateExecutiveDashboardStub(GenerateExecutiveDashboardProtocol):
    """Implementação stub para geração de dashboard executivo."""

    async def collect_financial_kpis(
        self, period_start: datetime, period_end: datetime
    ) -> list[ExecutiveKPI]:
        """Coleta KPIs financeiros."""
        return [
            ExecutiveKPI(
                kpi_name="Receita Total",
                kpi_category="financial",
                value=8_450_000.00,
                unit="BRL",
                target=8_000_000.00,
                variance_from_target=5.6,
                previous_period=7_890_000.00,
                trend="up",
                status="good",
            ),
            ExecutiveKPI(
                kpi_name="EBITDA",
                kpi_category="financial",
                value=2_110_000.00,
                unit="BRL",
                target=2_000_000.00,
                variance_from_target=5.5,
                previous_period=1_900_000.00,
                trend="up",
                status="good",
            ),
            ExecutiveKPI(
                kpi_name="Margem Líquida",
                kpi_category="financial",
                value=24.8,
                unit="%",
                target=25.0,
                variance_from_target=-0.8,
                previous_period=24.1,
                trend="up",
                status="warning",
            ),
        ]

    async def collect_operational_kpis(
        self, period_start: datetime, period_end: datetime
    ) -> list[ExecutiveKPI]:
        """Coleta KPIs operacionais."""
        return [
            ExecutiveKPI(
                kpi_name="Taxa de Ocupação",
                kpi_category="operational",
                value=87.5,
                unit="%",
                target=85.0,
                variance_from_target=2.9,
                previous_period=84.2,
                trend="up",
                status="good",
            ),
            ExecutiveKPI(
                kpi_name="Tempo Médio de Permanência",
                kpi_category="operational",
                value=4.5,
                unit="days",
                target=4.0,
                variance_from_target=12.5,
                previous_period=4.7,
                trend="down",
                status="warning",
            ),
            ExecutiveKPI(
                kpi_name="Case Mix Index",
                kpi_category="operational",
                value=1.28,
                unit="index",
                target=1.25,
                variance_from_target=2.4,
                previous_period=1.22,
                trend="up",
                status="good",
            ),
        ]

    async def collect_clinical_kpis(
        self, period_start: datetime, period_end: datetime
    ) -> list[ExecutiveKPI]:
        """Coleta KPIs clínicos."""
        return [
            ExecutiveKPI(
                kpi_name="Taxa de Readmissão 30 dias",
                kpi_category="clinical",
                value=5.3,
                unit="%",
                target=5.0,
                variance_from_target=6.0,
                previous_period=5.8,
                trend="down",
                status="warning",
            ),
            ExecutiveKPI(
                kpi_name="Índice de Mortalidade",
                kpi_category="clinical",
                value=1.4,
                unit="%",
                target=2.0,
                variance_from_target=-30.0,
                previous_period=1.9,
                trend="down",
                status="good",
            ),
            ExecutiveKPI(
                kpi_name="Taxa de Infecção Hospitalar",
                kpi_category="clinical",
                value=0.9,
                unit="%",
                target=1.5,
                variance_from_target=-40.0,
                previous_period=1.2,
                trend="down",
                status="good",
            ),
        ]

    async def generate_executive_summary(
        self, kpis: list[ExecutiveKPI]
    ) -> dict[str, Any]:
        """Gera resumo executivo."""
        return {
            "highlights": [
                _("Receita 5.6% acima da meta"),
                _("Taxa de ocupação em 87.5% (ideal)"),
                _("Indicadores de qualidade clínica dentro das metas"),
            ],
            "concerns": [
                _("Margem líquida ligeiramente abaixo da meta"),
                _("LOS 12.5% acima do alvo"),
            ],
            "recommendations": [
                _("Revisar custos operacionais para melhorar margem"),
                _("Implementar protocolo de alta precoce segura"),
            ],
        }


# ============================================================================
# Função de Execução
# ============================================================================


@require_tenant
@track_task_execution
async def execute(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Executa geração de dashboard executivo.

    Args:
        input_data: Dados de entrada validados

    Returns:
        Dashboard executivo gerado

    Raises:
        DashboardGenerationException: Se houver erro na geração
    """
    tenant = get_required_tenant()
    parsed_input = GenerateExecutiveDashboardInput(**input_data)


    dashboard_id = (
        f"exec_dash_{parsed_input.dashboard_type}_"
        f"{int(parsed_input.period_start.timestamp())}"
    )

    logger.info(
        _("Iniciando geração de dashboard executivo"),
        extra={
            "tenant_id": tenant.tenant_code,
            "dashboard_id": dashboard_id,
            "dashboard_type": parsed_input.dashboard_type,
        },
    )

    start_time = datetime.utcnow()
    # DMN decision support
    _dmn = get_dmn_service()
    try:
        _dmn_config = _dmn.evaluate(
            tenant_id=tenant.tenant_code,
            category='compliance',
            table_name='audit/comp_audit_004',
            inputs={'dashboard_type': parsed_input.dashboard_type},
        )
    except (FileNotFoundError, ValueError):
        _dmn_config = {}



    try:
        service = GenerateExecutiveDashboardStub()

        # Coletar todos os KPIs
        financial_kpis = await service.collect_financial_kpis(
            parsed_input.period_start, parsed_input.period_end
        )
        operational_kpis = await service.collect_operational_kpis(
            parsed_input.period_start, parsed_input.period_end
        )
        clinical_kpis = await service.collect_clinical_kpis(
            parsed_input.period_start, parsed_input.period_end
        )

        all_kpis = financial_kpis + operational_kpis + clinical_kpis

        # Gerar resumo executivo
        summary = await service.generate_executive_summary(all_kpis)

        # Identificar alertas críticos
        alerts = [
            kpi.kpi_name
            for kpi in all_kpis
            if kpi.status == "critical"
        ]

        duration_ms = max(1, int((datetime.utcnow() - start_time).total_seconds() * 1000))

        output = GenerateExecutiveDashboardOutput(
            dashboard_id=dashboard_id,
            dashboard_type=parsed_input.dashboard_type,
            period_start=parsed_input.period_start,
            period_end=parsed_input.period_end,
            kpis=all_kpis,
            summary=summary,
            alerts=alerts,
            duration_ms=duration_ms,
        )

        # Métricas
        dashboard_generations_total.labels(
            tenant_id=tenant.tenant_code,
            dashboard_type=parsed_input.dashboard_type,
            status="success",
        ).inc()

        dashboard_duration_seconds.labels(
            tenant_id=tenant.tenant_code,
            dashboard_type=parsed_input.dashboard_type,
        ).observe(duration_ms / 1000.0)

        logger.info(
            _("Dashboard executivo gerado com sucesso"),
            extra={
                "tenant_id": tenant.tenant_code,
                "dashboard_id": dashboard_id,
                "kpis_count": len(all_kpis),
                "alerts_count": len(alerts),
                "duration_ms": duration_ms,
            },
        )

        return output.model_dump()

    except Exception as e:
        logger.error(
            _("Erro na geração de dashboard executivo"),
            extra={
                "tenant_id": tenant.tenant_code,
                "dashboard_id": dashboard_id,
                "error": str(e),
            },
            exc_info=True,
        )
        raise DashboardGenerationException(
            message=_("Falha ao gerar dashboard executivo"),
            details={"dashboard_id": dashboard_id, "error": str(e)},
        )


# Topic Kafka
TOPIC = "platform.services.generate-executive-dashboard"
