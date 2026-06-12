"""
Worker para monitoramento de saúde da infraestrutura.

Monitora:
- Latência de APIs e microserviços
- Connection pools de banco de dados
- Profundidade de filas (RabbitMQ/Kafka)
- Uso de memória e CPU
- Disponibilidade de serviços (health checks)

Padrão: Protocol ABC + Stub implementation
Decorators: @require_tenant, @track_task_execution
Métricas: Prometheus Counter, Histogram, Gauge
i18n: Todas strings user-facing via _()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
health_checks_total = Counter(
    "health_checks_total",
    "Total system health checks executed",
    ["tenant_id", "component", "status"],
)
health_duration_seconds = Histogram(
    "health_duration_seconds",
    "Duration of system health check",
    ["tenant_id", "component"],
)
system_health_gauge = Gauge(
    "system_health_gauge",
    "Current health score (0-100) of system components",
    ["tenant_id", "component"],
)

TOPIC = "platform.monitor_system_health"


class SystemHealthException(DomainException):
    """    Exceção de monitoramento de saúde do sistema.
    
        Archetype: CLINICAL_ALERT
        """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="SYSTEM_HEALTH_ERROR",
            details=details or {},
        )


class MonitorSystemHealthInput(BaseModel):
    """Input para monitoramento de saúde do sistema."""

    components: list[str] = Field(
        default_factory=lambda: ["api", "database", "queue", "cache", "storage"],
        description=_("Componentes a monitorar: api, database, queue, cache, storage"),
    )
    include_detailed_metrics: bool = Field(
        default=True,
        description=_("Incluir métricas detalhadas (latência p95, connection pools, etc)"),
    )
    alert_threshold: float = Field(
        default=80.0,
        description=_("Threshold de alerta: gera alerta se health_score < threshold"),
    )


class ComponentHealth(BaseModel):
    """Saúde de um componente do sistema."""

    component_name: str = Field(..., description=_("Nome do componente"))
    status: str = Field(..., description=_("Status: healthy, degraded, unhealthy"))
    health_score: float = Field(..., description=_("Score de saúde (0-100)"))
    response_time_ms: float | None = Field(None, description=_("Tempo de resposta em ms (se aplicável)"))
    error_rate: float | None = Field(None, description=_("Taxa de erro (%)"))
    cpu_usage_percent: float | None = Field(None, description=_("Uso de CPU (%)"))
    memory_usage_percent: float | None = Field(None, description=_("Uso de memória (%)"))
    connection_pool_active: int | None = Field(None, description=_("Conexões ativas no pool"))
    connection_pool_max: int | None = Field(None, description=_("Tamanho máximo do pool"))
    queue_depth: int | None = Field(None, description=_("Profundidade da fila (mensagens pendentes)"))
    disk_usage_percent: float | None = Field(None, description=_("Uso de disco (%)"))
    last_error: str | None = Field(None, description=_("Última mensagem de erro"))


class MonitorSystemHealthOutput(BaseModel):
    """Output do monitoramento de saúde do sistema."""

    monitoring_id: str = Field(..., description=_("ID único do monitoramento"))
    overall_health_score: float = Field(..., description=_("Score geral de saúde (0-100)"))
    overall_status: str = Field(..., description=_("Status geral: healthy, degraded, unhealthy"))
    components_health: list[ComponentHealth] = Field(
        default_factory=list,
        description=_("Saúde por componente"),
    )
    degraded_components: list[str] = Field(
        default_factory=list,
        description=_("Componentes degradados"),
    )
    unhealthy_components: list[str] = Field(
        default_factory=list,
        description=_("Componentes não saudáveis"),
    )
    alert_triggered: bool = Field(default=False, description=_("Se alerta foi disparado"))
    alert_message: str | None = Field(None, description=_("Mensagem de alerta"))
    monitored_at: datetime = Field(default_factory=datetime.utcnow, description=_("Timestamp do monitoramento"))
    duration_seconds: float = Field(..., description=_("Duração do monitoramento em segundos"))


class MonitorSystemHealthProtocol(ABC):
    """Protocol para monitoramento de saúde do sistema."""

    @abstractmethod
    async def execute(self, input_data: MonitorSystemHealthInput) -> MonitorSystemHealthOutput:
        """
        Monitora saúde da infraestrutura.

        Args:
            input_data: Parâmetros do monitoramento

        Returns:
            MonitorSystemHealthOutput com métricas de saúde

        Raises:
            SystemHealthException: Erro no monitoramento
        """
        pass


class MonitorSystemHealthStub(MonitorSystemHealthProtocol):
    """Stub implementation para monitoramento de saúde do sistema."""

    @require_tenant
    @track_task_execution
    async def execute(self, input_data: MonitorSystemHealthInput) -> MonitorSystemHealthOutput:
        """
        Monitora saúde da infraestrutura.

        Fluxo:
        1. Para cada componente, executa health check
        2. Coleta métricas: latência, CPU, memória, connection pools, queue depth
        3. Calcula health_score (0-100) baseado em thresholds
        4. Identifica componentes degraded/unhealthy
        5. Se overall_health_score < alert_threshold, dispara alerta
        6. Atualiza métricas Prometheus

        Componentes:
        - API: latência, error_rate, CPU, memória
        - Database: connection_pool, query latency, CPU
        - Queue: queue_depth, message_rate, latency
        - Cache: hit_rate, memory_usage, eviction_rate
        - Storage: disk_usage, I/O latency
        """
        tenant = get_required_tenant()
        _dmn = get_dmn_service()
        try:
            _dmn_result = _dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='infrastructure',
                table_name='config/infra_001',
                inputs={'components': input_data.components, 'alert_threshold': input_data.alert_threshold},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        start_time = datetime.utcnow()

        logger.info(
            _("Iniciando monitoramento de saúde: {components}").format(
                components=", ".join(input_data.components)
            ),
            extra={"tenant_id": tenant.tenant_code},
        )

        try:
            components_health = []

            for component in input_data.components:
                component_health = await self._check_component_health(
                    component=component,
                    include_detailed_metrics=input_data.include_detailed_metrics,
                )
                components_health.append(component_health)

                # Atualiza gauge Prometheus
                system_health_gauge.labels(
                    tenant_id=tenant.tenant_code,
                    component=component,
                ).set(component_health.health_score)

                # Contador por status
                health_checks_total.labels(
                    tenant_id=tenant.tenant_code,
                    component=component,
                    status=component_health.status,
                ).inc()

            # Calcula saúde geral
            overall_health_score = (
                sum(c.health_score for c in components_health) / len(components_health)
                if components_health
                else 100.0
            )

            # Classifica status geral
            if overall_health_score >= 90:
                overall_status = "healthy"
            elif overall_health_score >= 70:
                overall_status = "degraded"
            else:
                overall_status = "unhealthy"

            # Identifica componentes degraded/unhealthy
            degraded = [c.component_name for c in components_health if c.status == "degraded"]
            unhealthy = [c.component_name for c in components_health if c.status == "unhealthy"]

            # Dispara alerta se necessário
            alert_triggered = overall_health_score < input_data.alert_threshold
            alert_message = None
            if alert_triggered:
                alert_message = _(
                    "Saúde do sistema abaixo do threshold: {score} < {threshold}. "
                    "Componentes não saudáveis: {unhealthy}"
                ).format(
                    score=round(overall_health_score, 1),
                    threshold=input_data.alert_threshold,
                    unhealthy=", ".join(unhealthy) if unhealthy else "nenhum",
                )

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Histogram de duração
            health_duration_seconds.labels(
                tenant_id=tenant.tenant_code,
                component="overall",
            ).observe(duration)

            monitoring_id = f"HEALTH-{tenant.tenant_code}-{int(start_time.timestamp())}"

            output = MonitorSystemHealthOutput(
                monitoring_id=monitoring_id,
                overall_health_score=overall_health_score,
                overall_status=overall_status,
                components_health=components_health,
                degraded_components=degraded,
                unhealthy_components=unhealthy,
                alert_triggered=alert_triggered,
                alert_message=alert_message,
                duration_seconds=duration,
            )

            logger.info(
                _("Monitoramento concluído: score={score}, status={status}").format(
                    score=round(overall_health_score, 1),
                    status=overall_status,
                ),
                extra={
                    "tenant_id": tenant.tenant_code,
                    "monitoring_id": monitoring_id,
                },
            )

            return output

        except Exception as e:
            logger.error(_("Erro no monitoramento de saúde: {error}").format(error=str(e)))
            raise SystemHealthException(
                message=_("Falha ao monitorar saúde do sistema"),
                details={"error": str(e)},
            ) from e

    async def _check_component_health(
        self,
        component: str,
        include_detailed_metrics: bool,
    ) -> ComponentHealth:
        """Executa health check de um componente (stub)."""
        # Stub: retorna métricas simuladas
        if component == "api":
            return ComponentHealth(
                component_name="api",
                status="healthy",
                health_score=95.0,
                response_time_ms=45.0,
                error_rate=0.5,
                cpu_usage_percent=35.0,
                memory_usage_percent=60.0,
            )
        elif component == "database":
            return ComponentHealth(
                component_name="database",
                status="healthy",
                health_score=92.0,
                response_time_ms=8.0,
                cpu_usage_percent=40.0,
                memory_usage_percent=70.0,
                connection_pool_active=15,
                connection_pool_max=50,
            )
        elif component == "queue":
            return ComponentHealth(
                component_name="queue",
                status="degraded",
                health_score=75.0,
                queue_depth=1500,
                cpu_usage_percent=50.0,
                memory_usage_percent=65.0,
            )
        elif component == "cache":
            return ComponentHealth(
                component_name="cache",
                status="healthy",
                health_score=98.0,
                response_time_ms=2.0,
                memory_usage_percent=45.0,
            )
        elif component == "storage":
            return ComponentHealth(
                component_name="storage",
                status="healthy",
                health_score=90.0,
                disk_usage_percent=55.0,
                response_time_ms=12.0,
            )
        else:
            return ComponentHealth(
                component_name=component,
                status="healthy",
                health_score=100.0,
            )
