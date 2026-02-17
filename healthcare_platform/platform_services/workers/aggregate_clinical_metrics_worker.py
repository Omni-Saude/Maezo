"""
Worker para agregação de métricas clínicas (KPIs de qualidade).

Calcula taxas de readmissão, índices de mortalidade, taxas de infecção,
tempo médio de permanência por especialidade e outros indicadores clínicos.

Padrões:
- Protocolo ABC + Stub implementation
- Modelos Pydantic com i18n
- Decoradores @require_tenant e @track_task_execution
- Conformidade LGPD com hash de identificadores
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
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
clinical_metrics_aggregations_total = Counter(
    "clinical_metrics_aggregations_total",
    "Total de agregações de métricas clínicas",
    ["tenant_id", "metric_type", "status"],
)

aggregation_duration_seconds = Histogram(
    "clinical_aggregation_duration_seconds",
    "Duração das agregações de métricas clínicas",
    ["tenant_id", "metric_type"],
)


class ClinicalMetricsException(DomainException):
    """Exceção lançada quando ocorrem erros na agregação de métricas clínicas."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="CLINICAL_METRICS_ERROR",
            bpmn_error_code="ClinicalMetricsError",
            details=details or {},
        )


# ============================================================================
# Modelos Pydantic
# ============================================================================


class AggregateClinicalMetricsInput(BaseModel):
    """Input para agregação de métricas clínicas."""

    metric_types: list[
        Literal[
            "readmission_rate",
            "mortality_index",
            "infection_rate",
            "los_average",
            "complication_rate",
        ]
    ] = Field(..., description=_("Tipos de métricas a calcular"))
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    specialty: str | None = Field(
        None, description=_("Especialidade médica (filtro opcional)")
    )
    department: str | None = Field(
        None, description=_("Departamento (filtro opcional)")
    )
    icd10_filter: list[str] | None = Field(
        None, description=_("Filtro por códigos CID-10")
    )
    include_comparison: bool = Field(
        True, description=_("Incluir comparação com período anterior")
    )


class MetricValue(BaseModel):
    """Valor de métrica clínica."""

    metric_type: str = Field(..., description=_("Tipo de métrica"))
    value: float = Field(..., description=_("Valor calculado"))
    unit: str = Field(..., description=_("Unidade de medida"))
    numerator: int = Field(..., description=_("Numerador da métrica"))
    denominator: int = Field(..., description=_("Denominador da métrica"))
    target_value: float | None = Field(
        None, description=_("Valor alvo (meta)")
    )
    performance: Literal["above", "at", "below"] | None = Field(
        None, description=_("Performance vs. meta")
    )
    previous_period_value: float | None = Field(
        None, description=_("Valor do período anterior")
    )
    trend: Literal["improving", "stable", "declining"] | None = Field(
        None, description=_("Tendência")
    )


class AggregateClinicalMetricsOutput(BaseModel):
    """Output da agregação de métricas clínicas."""

    aggregation_id: str = Field(..., description=_("ID único da agregação"))
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    metrics: list[MetricValue] = Field(..., description=_("Métricas calculadas"))
    specialty: str | None = Field(None, description=_("Especialidade filtrada"))
    department: str | None = Field(None, description=_("Departamento filtrado"))
    total_encounters: int = Field(
        ..., description=_("Total de atendimentos no período")
    )
    aggregated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp da agregação"),
    )
    duration_ms: int = Field(..., description=_("Duração em milissegundos"))


# ============================================================================
# Protocol e Implementação
# ============================================================================


class AggregateClinicalMetricsProtocol(ABC):
    """Protocolo para agregação de métricas clínicas.

    Archetype: CLINICAL_SCORE
    """

    @abstractmethod
    async def calculate_readmission_rate(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> MetricValue:
        """
        Calcula taxa de readmissão em 30 dias.

        Args:
            period_start: Início do período
            period_end: Fim do período
            filters: Filtros adicionais

        Returns:
            Métrica de readmissão
        """
        pass

    @abstractmethod
    async def calculate_mortality_index(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> MetricValue:
        """
        Calcula índice de mortalidade hospitalar.

        Args:
            period_start: Início do período
            period_end: Fim do período
            filters: Filtros adicionais

        Returns:
            Métrica de mortalidade
        """
        pass

    @abstractmethod
    async def calculate_infection_rate(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> MetricValue:
        """
        Calcula taxa de infecção hospitalar.

        Args:
            period_start: Início do período
            period_end: Fim do período
            filters: Filtros adicionais

        Returns:
            Métrica de infecção
        """
        pass

    @abstractmethod
    async def calculate_los_average(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> MetricValue:
        """
        Calcula tempo médio de permanência.

        Args:
            period_start: Início do período
            period_end: Fim do período
            filters: Filtros adicionais

        Returns:
            Métrica de LOS médio
        """
        pass


class AggregateClinicalMetricsStub(AggregateClinicalMetricsProtocol):
    """Implementação stub para agregação de métricas clínicas."""

    async def calculate_readmission_rate(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> MetricValue:
        """Calcula taxa de readmissão."""
        numerator = 45  # Readmissões em 30 dias
        denominator = 850  # Total de altas
        rate = (numerator / denominator) * 100 if denominator > 0 else 0.0

        return MetricValue(
            metric_type="readmission_rate",
            value=round(rate, 2),
            unit="%",
            numerator=numerator,
            denominator=denominator,
            target_value=5.0,
            performance="above" if rate > 5.0 else "at",
            previous_period_value=5.8,
            trend="improving",
        )

    async def calculate_mortality_index(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> MetricValue:
        """Calcula índice de mortalidade."""
        numerator = 12  # Óbitos
        denominator = 850  # Total de altas
        rate = (numerator / denominator) * 100 if denominator > 0 else 0.0

        return MetricValue(
            metric_type="mortality_index",
            value=round(rate, 2),
            unit="%",
            numerator=numerator,
            denominator=denominator,
            target_value=2.0,
            performance="at",
            previous_period_value=1.9,
            trend="stable",
        )

    async def calculate_infection_rate(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> MetricValue:
        """Calcula taxa de infecção hospitalar."""
        numerator = 8  # Infecções
        denominator = 850  # Total de altas
        rate = (numerator / denominator) * 100 if denominator > 0 else 0.0

        return MetricValue(
            metric_type="infection_rate",
            value=round(rate, 2),
            unit="%",
            numerator=numerator,
            denominator=denominator,
            target_value=1.5,
            performance="below",
            previous_period_value=1.2,
            trend="declining",
        )

    async def calculate_los_average(
        self,
        period_start: datetime,
        period_end: datetime,
        filters: dict[str, Any],
    ) -> MetricValue:
        """Calcula tempo médio de permanência."""
        total_days = 3825  # Total de dias de internação
        total_encounters = 850

        avg_los = total_days / total_encounters if total_encounters > 0 else 0.0

        return MetricValue(
            metric_type="los_average",
            value=round(avg_los, 1),
            unit="days",
            numerator=total_days,
            denominator=total_encounters,
            target_value=4.0,
            performance="above",
            previous_period_value=4.7,
            trend="improving",
        )


# ============================================================================
# Função de Execução
# ============================================================================


@require_tenant
@track_task_execution
async def execute(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Executa agregação de métricas clínicas.

    Args:
        input_data: Dados de entrada validados

    Returns:
        Resultado da agregação

    Raises:
        ClinicalMetricsException: Se houver erro na agregação
    """
    tenant = get_required_tenant()
    parsed_input = AggregateClinicalMetricsInput(**input_data)


    aggregation_id = (
        f"clinical_agg_{int(parsed_input.period_start.timestamp())}_"
        f"{int(parsed_input.period_end.timestamp())}"
    )

    logger.info(
        _("Iniciando agregação de métricas clínicas"),
        extra={
            "tenant_id": tenant.tenant_code,
            "aggregation_id": aggregation_id,
            "metric_types": parsed_input.metric_types,
            "period_days": (
                parsed_input.period_end - parsed_input.period_start
            ).days,
        },
    )

    start_time = datetime.utcnow()
    # DMN decision support
    _dmn = get_dmn_service()
    try:
        _dmn_config = _dmn.evaluate(
            tenant_id=tenant.tenant_code,
            category='compliance',
            table_name='accred/comp_accred_001',
            inputs={'metric_types': parsed_input.metric_types, 'specialty': parsed_input.specialty},
        )
    except (FileNotFoundError, ValueError):
        _dmn_config = {}



    try:
        service = AggregateClinicalMetricsStub()

        filters = {
            "specialty": parsed_input.specialty,
            "department": parsed_input.department,
            "icd10_filter": parsed_input.icd10_filter,
        }

        metrics = []

        # Calcular cada métrica solicitada
        for metric_type in parsed_input.metric_types:
            if metric_type == "readmission_rate":
                metric = await service.calculate_readmission_rate(
                    parsed_input.period_start,
                    parsed_input.period_end,
                    filters,
                )
            elif metric_type == "mortality_index":
                metric = await service.calculate_mortality_index(
                    parsed_input.period_start,
                    parsed_input.period_end,
                    filters,
                )
            elif metric_type == "infection_rate":
                metric = await service.calculate_infection_rate(
                    parsed_input.period_start,
                    parsed_input.period_end,
                    filters,
                )
            elif metric_type == "los_average":
                metric = await service.calculate_los_average(
                    parsed_input.period_start,
                    parsed_input.period_end,
                    filters,
                )
            else:
                continue

            metrics.append(metric)

            # Métricas Prometheus por tipo
            clinical_metrics_aggregations_total.labels(
                tenant_id=tenant.tenant_code,
                metric_type=metric_type,
                status="success",
            ).inc()

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        output = AggregateClinicalMetricsOutput(
            aggregation_id=aggregation_id,
            period_start=parsed_input.period_start,
            period_end=parsed_input.period_end,
            metrics=metrics,
            specialty=parsed_input.specialty,
            department=parsed_input.department,
            total_encounters=850,  # Simulado
            duration_ms=duration_ms,
        )

        logger.info(
            _("Agregação de métricas clínicas concluída"),
            extra={
                "tenant_id": tenant.tenant_code,
                "aggregation_id": aggregation_id,
                "metrics_calculated": len(metrics),
                "duration_ms": duration_ms,
            },
        )

        return output.model_dump()

    except Exception as e:
        logger.error(
            _("Erro na agregação de métricas clínicas"),
            extra={
                "tenant_id": tenant.tenant_code,
                "aggregation_id": aggregation_id,
                "error": str(e),
            },
            exc_info=True,
        )
        raise ClinicalMetricsException(
            message=_("Falha ao agregar métricas clínicas"),
            details={"aggregation_id": aggregation_id, "error": str(e)},
        )


# Topic Kafka
TOPIC = "platform.services.aggregate-clinical-metrics"
