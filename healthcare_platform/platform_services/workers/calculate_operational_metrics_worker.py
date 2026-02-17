"""
Worker para cálculo de métricas operacionais hospitalares.

Calcula tempo médio de permanência (LOS), taxa de ocupação de leitos,
utilização de centro cirúrgico, throughput de emergência e outros KPIs operacionais.

Padrões:
- Protocolo ABC + Stub implementation
- Modelos Pydantic com i18n
- Decoradores @require_tenant e @track_task_execution
- Conformidade LGPD

Archetype: OPERATIONAL_ROUTING
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Métricas Prometheus
operational_calculations_total = Counter(
    "operational_calculations_total",
    "Total de cálculos de métricas operacionais",
    ["tenant_id", "metric_type", "status"],
)

operational_duration_seconds = Histogram(
    "operational_calculation_duration_seconds",
    "Duração dos cálculos de métricas operacionais",
    ["tenant_id", "metric_type"],
)

bed_occupancy_gauge = Gauge(
    "bed_occupancy_rate",
    "Taxa de ocupação de leitos atual",
    ["tenant_id", "department"],
)


class OperationalMetricsException(DomainException):
    """Exceção lançada quando ocorrem erros no cálculo de métricas operacionais."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="OPERATIONAL_METRICS_ERROR",
            bpmn_error_code="OperationalMetricsError",
            details=details or {},
        )


# ============================================================================
# Modelos Pydantic
# ============================================================================


class CalculateOperationalMetricsInput(BaseModel):
    """Input para cálculo de métricas operacionais."""

    metric_types: list[
        Literal["los", "bed_occupancy", "or_utilization", "ed_throughput"]
    ] = Field(..., description=_("Tipos de métricas operacionais a calcular"))
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    department: str | None = Field(
        None, description=_("Departamento (filtro opcional)")
    )
    include_benchmarks: bool = Field(
        True, description=_("Incluir comparação com benchmarks")
    )


class OperationalMetric(BaseModel):
    """Métrica operacional calculada."""

    metric_type: str = Field(..., description=_("Tipo de métrica"))
    value: float = Field(..., description=_("Valor calculado"))
    unit: str = Field(..., description=_("Unidade de medida"))
    benchmark_value: float | None = Field(
        None, description=_("Valor de benchmark")
    )
    variance_from_benchmark: float | None = Field(
        None, description=_("Variação do benchmark (%)")
    )
    status: Literal["good", "warning", "critical"] = Field(
        ..., description=_("Status da métrica")
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description=_("Detalhes adicionais")
    )


class CalculateOperationalMetricsOutput(BaseModel):
    """Output do cálculo de métricas operacionais."""

    calculation_id: str = Field(..., description=_("ID único do cálculo"))
    period_start: datetime = Field(..., description=_("Início do período"))
    period_end: datetime = Field(..., description=_("Fim do período"))
    metrics: list[OperationalMetric] = Field(
        ..., description=_("Métricas calculadas")
    )
    department: str | None = Field(None, description=_("Departamento filtrado"))
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp do cálculo"),
    )
    duration_ms: int = Field(..., description=_("Duração em milissegundos"))


# ============================================================================
# Protocol e Implementação
# ============================================================================


class CalculateOperationalMetricsProtocol(ABC):
    """Protocolo para cálculo de métricas operacionais."""

    @abstractmethod
    async def calculate_los(
        self,
        period_start: datetime,
        period_end: datetime,
        department: str | None,
    ) -> OperationalMetric:
        """
        Calcula tempo médio de permanência (Length of Stay).

        Args:
            period_start: Início do período
            period_end: Fim do período
            department: Departamento filtrado

        Returns:
            Métrica de LOS
        """
        pass

    @abstractmethod
    async def calculate_bed_occupancy(
        self,
        period_start: datetime,
        period_end: datetime,
        department: str | None,
    ) -> OperationalMetric:
        """
        Calcula taxa de ocupação de leitos.

        Args:
            period_start: Início do período
            period_end: Fim do período
            department: Departamento filtrado

        Returns:
            Métrica de ocupação
        """
        pass

    @abstractmethod
    async def calculate_or_utilization(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> OperationalMetric:
        """
        Calcula taxa de utilização do centro cirúrgico.

        Args:
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Métrica de utilização de CC
        """
        pass

    @abstractmethod
    async def calculate_ed_throughput(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> OperationalMetric:
        """
        Calcula throughput do pronto-socorro.

        Args:
            period_start: Início do período
            period_end: Fim do período

        Returns:
            Métrica de throughput
        """
        pass


class CalculateOperationalMetricsStub(CalculateOperationalMetricsProtocol):
    """Implementação stub para cálculo de métricas operacionais."""

    async def calculate_los(
        self,
        period_start: datetime,
        period_end: datetime,
        department: str | None,
    ) -> OperationalMetric:
        """Calcula tempo médio de permanência."""
        avg_los = 4.5  # dias
        benchmark = 4.0
        variance = ((avg_los - benchmark) / benchmark) * 100

        return OperationalMetric(
            metric_type="los",
            value=avg_los,
            unit="days",
            benchmark_value=benchmark,
            variance_from_benchmark=round(variance, 1),
            status="warning" if avg_los > benchmark else "good",
            details={
                "total_admissions": 850,
                "total_patient_days": 3825,
                "department": department or "all",
            },
        )

    async def calculate_bed_occupancy(
        self,
        period_start: datetime,
        period_end: datetime,
        department: str | None,
    ) -> OperationalMetric:
        """Calcula taxa de ocupação de leitos."""
        occupancy_rate = 87.5  # %
        benchmark = 85.0
        variance = ((occupancy_rate - benchmark) / benchmark) * 100

        return OperationalMetric(
            metric_type="bed_occupancy",
            value=occupancy_rate,
            unit="%",
            benchmark_value=benchmark,
            variance_from_benchmark=round(variance, 1),
            status="good" if 80 <= occupancy_rate <= 90 else "warning",
            details={
                "total_beds": 120,
                "occupied_beds": 105,
                "available_beds": 15,
                "department": department or "all",
            },
        )

    async def calculate_or_utilization(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> OperationalMetric:
        """Calcula taxa de utilização do centro cirúrgico."""
        utilization_rate = 78.3  # %
        benchmark = 80.0
        variance = ((utilization_rate - benchmark) / benchmark) * 100

        return OperationalMetric(
            metric_type="or_utilization",
            value=utilization_rate,
            unit="%",
            benchmark_value=benchmark,
            variance_from_benchmark=round(variance, 1),
            status="warning" if utilization_rate < 75 else "good",
            details={
                "total_or_hours": 480,
                "used_or_hours": 376,
                "idle_hours": 104,
                "surgeries_performed": 124,
            },
        )

    async def calculate_ed_throughput(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> OperationalMetric:
        """Calcula throughput do pronto-socorro."""
        avg_throughput = 3.2  # horas
        benchmark = 4.0
        variance = ((avg_throughput - benchmark) / benchmark) * 100

        return OperationalMetric(
            metric_type="ed_throughput",
            value=avg_throughput,
            unit="hours",
            benchmark_value=benchmark,
            variance_from_benchmark=round(variance, 1),
            status="good" if avg_throughput <= benchmark else "warning",
            details={
                "total_ed_visits": 1250,
                "avg_wait_time_minutes": 45,
                "left_without_treatment": 15,
            },
        )


# ============================================================================
# Função de Execução
# ============================================================================


@require_tenant
@track_task_execution
async def execute(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Executa cálculo de métricas operacionais.

    Args:
        input_data: Dados de entrada validados

    Returns:
        Resultado do cálculo

    Raises:
        OperationalMetricsException: Se houver erro no cálculo
    """
    tenant = get_required_tenant()
    parsed_input = CalculateOperationalMetricsInput(**input_data)


    calculation_id = (
        f"oper_calc_{int(parsed_input.period_start.timestamp())}_"
        f"{int(parsed_input.period_end.timestamp())}"
    )

    logger.info(
        _("Iniciando cálculo de métricas operacionais"),
        extra={
            "tenant_id": tenant.tenant_code,
            "calculation_id": calculation_id,
            "metric_types": parsed_input.metric_types,
        },
    )

    start_time = datetime.utcnow()
    # DMN decision support
    _dmn = get_dmn_service()
    try:
        _dmn_config = _dmn.evaluate(
            tenant_id=tenant.tenant_code,
            category='compliance',
            table_name='accred/comp_accred_003',
            inputs={'metric_types': parsed_input.metric_types},
        )
    except (FileNotFoundError, ValueError):
        _dmn_config = {}



    try:
        service = CalculateOperationalMetricsStub()

        metrics = []

        for metric_type in parsed_input.metric_types:
            if metric_type == "los":
                metric = await service.calculate_los(
                    parsed_input.period_start,
                    parsed_input.period_end,
                    parsed_input.department,
                )
            elif metric_type == "bed_occupancy":
                metric = await service.calculate_bed_occupancy(
                    parsed_input.period_start,
                    parsed_input.period_end,
                    parsed_input.department,
                )
                # Atualizar gauge Prometheus
                bed_occupancy_gauge.labels(
                    tenant_id=tenant.tenant_code,
                    department=parsed_input.department or "all",
                ).set(metric.value)
            elif metric_type == "or_utilization":
                metric = await service.calculate_or_utilization(
                    parsed_input.period_start,
                    parsed_input.period_end,
                )
            elif metric_type == "ed_throughput":
                metric = await service.calculate_ed_throughput(
                    parsed_input.period_start,
                    parsed_input.period_end,
                )
            else:
                continue

            metrics.append(metric)

            operational_calculations_total.labels(
                tenant_id=tenant.tenant_code,
                metric_type=metric_type,
                status="success",
            ).inc()

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        output = CalculateOperationalMetricsOutput(
            calculation_id=calculation_id,
            period_start=parsed_input.period_start,
            period_end=parsed_input.period_end,
            metrics=metrics,
            department=parsed_input.department,
            duration_ms=duration_ms,
        )

        logger.info(
            _("Cálculo de métricas operacionais concluído"),
            extra={
                "tenant_id": tenant.tenant_code,
                "calculation_id": calculation_id,
                "metrics_calculated": len(metrics),
                "duration_ms": duration_ms,
            },
        )

        return output.model_dump()

    except Exception as e:
        logger.error(
            _("Erro no cálculo de métricas operacionais"),
            extra={
                "tenant_id": tenant.tenant_code,
                "calculation_id": calculation_id,
                "error": str(e),
            },
            exc_info=True,
        )
        raise OperationalMetricsException(
            message=_("Falha ao calcular métricas operacionais"),
            details={"calculation_id": calculation_id, "error": str(e)},
        )


# Topic Kafka
TOPIC = "platform.calculate_operational_metrics"
