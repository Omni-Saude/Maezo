"""
Worker para análise de performance de processos BPMN.

Calcula métricas de processos orquestrados:
- Cycle time (duração total do processo)
- Bottlenecks (atividades mais lentas)
- SLA compliance (% dentro do SLA)
- Throughput (processos concluídos/hora)

Padrão: Protocol ABC + Stub implementation
Decorators: @require_tenant, @track_task_execution
Métricas: Prometheus Counter, Histogram
LGPD: Hash de identificadores de processo/paciente antes de log
i18n: Todas strings user-facing via _()
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

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

# Prometheus metrics
process_analyses_total = Counter(
    "process_analyses_total",
    "Total process performance analyses executed",
    ["tenant_id", "process_definition_key", "status"],
)
process_duration_seconds = Histogram(
    "process_duration_seconds",
    "Duration of process performance analysis",
    ["tenant_id", "process_definition_key"],
)

TOPIC = "platform.track_process_performance"


class ProcessPerformanceException(DomainException):
    """Exceção de análise de performance de processo."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="PROCESS_PERFORMANCE_ERROR",
            details=details or {},
        )


class TrackProcessPerformanceInput(BaseModel):
    """Input para análise de performance de processos BPMN."""

    process_definition_key: str = Field(
        ...,
        description=_("Chave do processo BPMN (ex: revenue_cycle, clinical_admission)"),
    )
    date_start: datetime = Field(..., description=_("Data inicial da janela de análise"))
    date_end: datetime = Field(..., description=_("Data final da janela de análise"))
    include_active_instances: bool = Field(
        default=False,
        description=_("Incluir instâncias em andamento (não finalizadas)"),
    )
    calculate_bottlenecks: bool = Field(default=True, description=_("Detectar bottlenecks (atividades lentas)"))
    sla_threshold_hours: float = Field(default=24.0, description=_("Threshold de SLA em horas"))


class ActivityPerformance(BaseModel):
    """Performance de uma atividade do processo."""

    activity_id: str = Field(..., description=_("ID da atividade BPMN"))
    activity_name: str = Field(..., description=_("Nome da atividade"))
    avg_duration_seconds: float = Field(..., description=_("Duração média em segundos"))
    min_duration_seconds: float = Field(..., description=_("Duração mínima"))
    max_duration_seconds: float = Field(..., description=_("Duração máxima"))
    total_executions: int = Field(..., description=_("Total de execuções"))
    is_bottleneck: bool = Field(default=False, description=_("Se é um bottleneck (>2x desvio padrão)"))


class TrackProcessPerformanceOutput(BaseModel):
    """Output da análise de performance de processos."""

    analysis_id: str = Field(..., description=_("ID único da análise"))
    process_definition_key: str = Field(..., description=_("Chave do processo BPMN"))
    total_instances: int = Field(..., description=_("Total de instâncias analisadas"))
    completed_instances: int = Field(..., description=_("Instâncias finalizadas"))
    avg_cycle_time_seconds: float = Field(..., description=_("Tempo médio de ciclo (end-to-end)"))
    min_cycle_time_seconds: float = Field(..., description=_("Tempo mínimo de ciclo"))
    max_cycle_time_seconds: float = Field(..., description=_("Tempo máximo de ciclo"))
    sla_compliance_rate: float = Field(..., description=_("Taxa de conformidade com SLA (%)"))
    throughput_per_hour: float = Field(..., description=_("Throughput (instâncias concluídas/hora)"))
    activities_performance: list[ActivityPerformance] = Field(
        default_factory=list,
        description=_("Performance por atividade"),
    )
    bottlenecks: list[str] = Field(default_factory=list, description=_("IDs das atividades bottleneck"))
    analyzed_at: datetime = Field(default_factory=datetime.utcnow, description=_("Timestamp da análise"))
    duration_seconds: float = Field(..., description=_("Duração da análise em segundos"))


class TrackProcessPerformanceProtocol(ABC):
    """Protocol para análise de performance de processos BPMN."""

    @abstractmethod
    async def execute(self, input_data: TrackProcessPerformanceInput) -> TrackProcessPerformanceOutput:
        """
        Analisa performance de processos BPMN.

        Args:
            input_data: Parâmetros da análise

        Returns:
            TrackProcessPerformanceOutput com métricas de performance

        Raises:
            ProcessPerformanceException: Erro na análise
        """
        pass


class TrackProcessPerformanceStub(TrackProcessPerformanceProtocol):
    """Stub implementation para análise de performance de processos."""

    @require_tenant
    @track_task_execution
    async def execute(self, input_data: TrackProcessPerformanceInput) -> TrackProcessPerformanceOutput:
        """
        Analisa performance de processos BPMN.

        Fluxo:
        1. Extrai histórico de instâncias do processo (Camunda History API)
        2. Calcula cycle time (start → end) para cada instância
        3. Calcula duração média por atividade
        4. Detecta bottlenecks (atividades >2x desvio padrão)
        5. Calcula SLA compliance (% dentro do threshold)
        6. Calcula throughput (instâncias/hora)
        7. Atualiza métricas Prometheus

        LGPD: Hash de process_instance_id antes de logar.
        """
        tenant = get_required_tenant()
        _dmn = get_dmn_service()
        try:
            _dmn_result = _dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='compliance',
                table_name='audit/comp_audit_002',
                inputs={'process_definition_key': input_data.process_definition_key},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        start_time = datetime.utcnow()

        logger.info(
            _("Analisando performance do processo {process_key}").format(
                process_key=input_data.process_definition_key,
            ),
            extra={
                "tenant_id": tenant.tenant_code,
                "date_start": input_data.date_start.isoformat(),
                "date_end": input_data.date_end.isoformat(),
            },
        )

        try:
            # Extrai histórico de instâncias do Camunda
            instances = await self._extract_process_instances(
                process_definition_key=input_data.process_definition_key,
                date_start=input_data.date_start,
                date_end=input_data.date_end,
                include_active=input_data.include_active_instances,
            )

            logger.info(
                _("Extraídas {count} instâncias do processo").format(count=len(instances))
            )

            # Calcula cycle time por instância
            cycle_times = await self._calculate_cycle_times(instances)

            # Calcula performance por atividade
            activities_performance = await self._calculate_activity_performance(instances)

            # Detecta bottlenecks
            bottlenecks = []
            if input_data.calculate_bottlenecks:
                bottlenecks = await self._detect_bottlenecks(activities_performance)

            # Calcula SLA compliance
            completed_instances = [i for i in instances if i["end_time"]]
            sla_compliant = sum(
                1
                for ct in cycle_times
                if ct <= input_data.sla_threshold_hours * 3600
            )
            sla_compliance_rate = (
                (sla_compliant / len(cycle_times)) * 100.0 if cycle_times else 0.0
            )

            # Calcula throughput
            time_window_hours = (input_data.date_end - input_data.date_start).total_seconds() / 3600
            throughput = len(completed_instances) / time_window_hours if time_window_hours > 0 else 0.0

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Atualiza métricas Prometheus
            process_analyses_total.labels(
                tenant_id=tenant.tenant_code,
                process_definition_key=input_data.process_definition_key,
                status="success",
            ).inc()

            process_duration_seconds.labels(
                tenant_id=tenant.tenant_code,
                process_definition_key=input_data.process_definition_key,
            ).observe(duration)

            analysis_id = f"PERF-{tenant.tenant_code}-{int(start_time.timestamp())}"

            output = TrackProcessPerformanceOutput(
                analysis_id=analysis_id,
                process_definition_key=input_data.process_definition_key,
                total_instances=len(instances),
                completed_instances=len(completed_instances),
                avg_cycle_time_seconds=sum(cycle_times) / len(cycle_times) if cycle_times else 0.0,
                min_cycle_time_seconds=min(cycle_times) if cycle_times else 0.0,
                max_cycle_time_seconds=max(cycle_times) if cycle_times else 0.0,
                sla_compliance_rate=sla_compliance_rate,
                throughput_per_hour=throughput,
                activities_performance=activities_performance,
                bottlenecks=bottlenecks,
                duration_seconds=duration,
            )

            logger.info(
                _("Análise concluída: cycle_time={avg}s, SLA={sla}%, throughput={tp}/h").format(
                    avg=round(output.avg_cycle_time_seconds, 1),
                    sla=round(sla_compliance_rate, 1),
                    tp=round(throughput, 2),
                ),
                extra={
                    "tenant_id": tenant.tenant_code,
                    "analysis_id": analysis_id,
                },
            )

            return output

        except Exception as e:
            process_analyses_total.labels(
                tenant_id=tenant.tenant_code,
                process_definition_key=input_data.process_definition_key,
                status="error",
            ).inc()
            logger.error(_("Erro na análise de performance: {error}").format(error=str(e)))
            raise ProcessPerformanceException(
                message=_("Falha ao analisar performance do processo"),
                details={"error": str(e)},
            )

    async def _extract_process_instances(
        self,
        process_definition_key: str,
        date_start: datetime,
        date_end: datetime,
        include_active: bool,
    ) -> list[dict[str, Any]]:
        """Extrai histórico de instâncias do Camunda (stub)."""
        # Stub: retorna dados simulados
        instances = []
        for i in range(200):
            start = date_start + timedelta(hours=i * 0.5)
            end = start + timedelta(hours=2 + i % 10) if i % 10 != 0 else None

            instances.append(
                {
                    "process_instance_id": f"PI-{i}",
                    "start_time": start,
                    "end_time": end,
                    "activities": [
                        {"activity_id": "task_1", "duration_seconds": 300},
                        {"activity_id": "task_2", "duration_seconds": 1800},
                        {"activity_id": "task_3", "duration_seconds": 600},
                    ],
                }
            )

        return instances

    async def _calculate_cycle_times(self, instances: list[dict[str, Any]]) -> list[float]:
        """Calcula cycle time (end-to-end) para cada instância finalizada."""
        cycle_times = []
        for instance in instances:
            if instance["end_time"]:
                cycle_time = (instance["end_time"] - instance["start_time"]).total_seconds()
                cycle_times.append(cycle_time)

        return cycle_times

    async def _calculate_activity_performance(
        self,
        instances: list[dict[str, Any]],
    ) -> list[ActivityPerformance]:
        """Calcula duração média por atividade."""
        activity_stats: dict[str, list[float]] = {}

        for instance in instances:
            for activity in instance.get("activities", []):
                activity_id = activity["activity_id"]
                duration = activity["duration_seconds"]

                if activity_id not in activity_stats:
                    activity_stats[activity_id] = []

                activity_stats[activity_id].append(duration)

        activities_performance = []
        for activity_id, durations in activity_stats.items():
            activities_performance.append(
                ActivityPerformance(
                    activity_id=activity_id,
                    activity_name=f"Activity {activity_id}",
                    avg_duration_seconds=sum(durations) / len(durations),
                    min_duration_seconds=min(durations),
                    max_duration_seconds=max(durations),
                    total_executions=len(durations),
                )
            )

        return activities_performance

    async def _detect_bottlenecks(
        self,
        activities_performance: list[ActivityPerformance],
    ) -> list[str]:
        """Detecta atividades bottleneck (>2x desvio padrão)."""
        if not activities_performance:
            return []

        avg_durations = [a.avg_duration_seconds for a in activities_performance]
        overall_avg = sum(avg_durations) / len(avg_durations)
        variance = sum((d - overall_avg) ** 2 for d in avg_durations) / len(avg_durations)
        std_dev = variance**0.5

        bottlenecks = []
        for activity in activities_performance:
            if activity.avg_duration_seconds > overall_avg + 2 * std_dev:
                activity.is_bottleneck = True
                bottlenecks.append(activity.activity_id)

        return bottlenecks
