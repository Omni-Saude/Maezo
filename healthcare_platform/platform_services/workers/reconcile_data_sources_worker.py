"""
Worker para reconciliação de fontes de dados heterogêneas.

Compara registros entre Tasy, FHIR, MV Soul e outros sistemas,
identifica inconsistências e gera relatórios de reconciliação.
Suporta reconciliação incremental e full-refresh.

Padrão: Protocol ABC + Stub implementation
Decorators: @require_tenant, @track_task_execution
Métricas: Prometheus Counter, Histogram, Gauge
LGPD: Hash de identificadores de paciente antes de log
i18n: Todas strings user-facing via _()
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram

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
reconciliations_total = Counter(
    "reconciliations_total",
    "Total data source reconciliations executed",
    ["tenant_id", "source_a", "source_b", "status"],
)
reconciliation_duration_seconds = Histogram(
    "reconciliation_duration_seconds",
    "Duration of data source reconciliation operations",
    ["tenant_id", "source_a", "source_b"],
)
mismatches_gauge = Gauge(
    "mismatches_gauge",
    "Current number of unresolved data mismatches",
    ["tenant_id", "source_a", "source_b", "entity_type"],
)

TOPIC = "platform.reconcile_data_sources"


class ReconciliationException(DomainException):
    """Exceção de reconciliação de dados."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="RECONCILIATION_ERROR",
            details=details or {},
        )


class ReconcileDataSourcesInput(BaseModel):
    """Input para reconciliação de fontes de dados."""

    source_a: str = Field(..., description=_("Sistema fonte A (ex: tasy, fhir)"))
    source_b: str = Field(..., description=_("Sistema fonte B (ex: mv_soul, ans)"))
    entity_type: str = Field(..., description=_("Tipo de entidade a reconciliar (patient, encounter, claim)"))
    reconciliation_mode: str = Field(
        default="incremental",
        description=_("Modo: incremental (últimas 24h) ou full (todos registros)"),
    )
    date_start: datetime | None = Field(None, description=_("Data inicial para reconciliação incremental"))
    date_end: datetime | None = Field(None, description=_("Data final para reconciliação incremental"))
    auto_resolve: bool = Field(
        default=False,
        description=_("Se True, aplica regras de resolução automática de conflitos"),
    )
    priority_source: str | None = Field(
        None,
        description=_("Sistema com prioridade na resolução automática (source_a ou source_b)"),
    )


class MismatchDetail(BaseModel):
    """Detalhe de inconsistência entre fontes."""

    entity_id_source_a: str = Field(..., description=_("ID da entidade no sistema A"))
    entity_id_source_b: str | None = Field(None, description=_("ID da entidade no sistema B (se encontrado)"))
    mismatch_type: str = Field(..., description=_("Tipo: missing, field_mismatch, duplicate"))
    field_name: str | None = Field(None, description=_("Campo inconsistente (se field_mismatch)"))
    value_source_a: Any = Field(None, description=_("Valor no sistema A"))
    value_source_b: Any = Field(None, description=_("Valor no sistema B"))
    severity: str = Field(..., description=_("Severidade: low, medium, high, critical"))
    auto_resolved: bool = Field(default=False, description=_("Se foi resolvido automaticamente"))
    resolution_action: str | None = Field(None, description=_("Ação aplicada na resolução automática"))


class ReconcileDataSourcesOutput(BaseModel):
    """Output da reconciliação de fontes de dados."""

    reconciliation_id: str = Field(..., description=_("ID único da reconciliação"))
    source_a: str = Field(..., description=_("Sistema fonte A"))
    source_b: str = Field(..., description=_("Sistema fonte B"))
    entity_type: str = Field(..., description=_("Tipo de entidade reconciliada"))
    total_records_a: int = Field(..., description=_("Total de registros no sistema A"))
    total_records_b: int = Field(..., description=_("Total de registros no sistema B"))
    matched_records: int = Field(..., description=_("Registros consistentes"))
    mismatches: list[MismatchDetail] = Field(default_factory=list, description=_("Inconsistências detectadas"))
    auto_resolved_count: int = Field(default=0, description=_("Inconsistências resolvidas automaticamente"))
    unresolved_count: int = Field(..., description=_("Inconsistências não resolvidas"))
    reconciliation_report_url: str | None = Field(None, description=_("URL do relatório detalhado (S3/GCS)"))
    executed_at: datetime = Field(default_factory=datetime.utcnow, description=_("Timestamp de execução"))
    duration_seconds: float = Field(..., description=_("Duração da reconciliação em segundos"))


class ReconcileDataSourcesProtocol(ABC):
    """Protocol para reconciliação de fontes de dados heterogêneas."""

    @abstractmethod
    async def execute(self, input_data: ReconcileDataSourcesInput) -> ReconcileDataSourcesOutput:
        """
        Reconcilia registros entre dois sistemas.

        Args:
            input_data: Parâmetros da reconciliação

        Returns:
            ReconcileDataSourcesOutput com inconsistências detectadas

        Raises:
            ReconciliationException: Erro na reconciliação
        """
        pass


class ReconcileDataSourcesStub(ReconcileDataSourcesProtocol):
    """Stub implementation para reconciliação de fontes de dados."""

    def __init__(
        self,
        fhir_client: FHIRClientProtocol | None = None,
    ):
        """
        Inicializa o worker de reconciliação.

        Args:
            fhir_client: Cliente FHIR para acesso aos dados
        """
        self.fhir_client = fhir_client
        self._dmn = get_dmn_service()

    @require_tenant
    @track_task_execution
    async def execute(self, input_data: ReconcileDataSourcesInput) -> ReconcileDataSourcesOutput:
        """
        Reconcilia registros entre dois sistemas.

        Fluxo:
        1. Extrai registros de ambos os sistemas (janela de tempo se incremental)
        2. Mapeia IDs entre sistemas (via correlation keys)
        3. Compara campos críticos
        4. Classifica inconsistências (missing, field_mismatch, duplicate)
        5. Se auto_resolve=True, aplica regras de resolução
        6. Gera relatório detalhado e armazena em object storage
        7. Atualiza métricas Prometheus

        LGPD: Hash de patient_id antes de logar.
        """
        tenant = get_required_tenant()
        try:
            _dmn_result = self._dmn.evaluate(
                tenant_id=tenant.tenant_code,
                category='infrastructure',
                table_name='config/infra_002',
                inputs={'entity_type': input_data.entity_type},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        start_time = datetime.utcnow()

        logger.info(
            _("Iniciando reconciliação entre {source_a} e {source_b}").format(
                source_a=input_data.source_a,
                source_b=input_data.source_b,
            ),
            extra={
                "tenant_id": tenant.tenant_code,
                "entity_type": input_data.entity_type,
                "mode": input_data.reconciliation_mode,
            },
        )

        try:
            # Simula extração de registros de ambos os sistemas
            records_a = await self._extract_records(
                source=input_data.source_a,
                entity_type=input_data.entity_type,
                date_start=input_data.date_start,
                date_end=input_data.date_end,
                mode=input_data.reconciliation_mode,
            )

            records_b = await self._extract_records(
                source=input_data.source_b,
                entity_type=input_data.entity_type,
                date_start=input_data.date_start,
                date_end=input_data.date_end,
                mode=input_data.reconciliation_mode,
            )

            logger.info(
                _("Extraídos {count_a} registros de {source_a}, {count_b} de {source_b}").format(
                    count_a=len(records_a),
                    source_a=input_data.source_a,
                    count_b=len(records_b),
                    source_b=input_data.source_b,
                )
            )

            # Mapeia IDs entre sistemas (correlation keys)
            correlation_map = await self._build_correlation_map(records_a, records_b, input_data.entity_type)

            # Compara registros e detecta inconsistências
            mismatches = await self._detect_mismatches(
                records_a=records_a,
                records_b=records_b,
                correlation_map=correlation_map,
                entity_type=input_data.entity_type,
            )

            matched_count = len(records_a) - len([m for m in mismatches if m.mismatch_type == "missing"])

            # Resolução automática (se habilitada)
            auto_resolved_count = 0
            if input_data.auto_resolve and input_data.priority_source:
                auto_resolved_count = await self._auto_resolve_mismatches(
                    mismatches=mismatches,
                    priority_source=input_data.priority_source,
                    source_a=input_data.source_a,
                    source_b=input_data.source_b,
                )

            unresolved_count = len([m for m in mismatches if not m.auto_resolved])

            # Gera relatório detalhado (simulado)
            reconciliation_id = f"REC-{tenant.tenant_code}-{int(start_time.timestamp())}"
            report_url = await self._generate_reconciliation_report(
                reconciliation_id=reconciliation_id,
                mismatches=mismatches,
                input_data=input_data,
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Atualiza métricas Prometheus
            reconciliations_total.labels(
                tenant_id=tenant.tenant_code,
                source_a=input_data.source_a,
                source_b=input_data.source_b,
                status="success",
            ).inc()

            reconciliation_duration_seconds.labels(
                tenant_id=tenant.tenant_code,
                source_a=input_data.source_a,
                source_b=input_data.source_b,
            ).observe(duration)

            mismatches_gauge.labels(
                tenant_id=tenant.tenant_code,
                source_a=input_data.source_a,
                source_b=input_data.source_b,
                entity_type=input_data.entity_type,
            ).set(unresolved_count)

            output = ReconcileDataSourcesOutput(
                reconciliation_id=reconciliation_id,
                source_a=input_data.source_a,
                source_b=input_data.source_b,
                entity_type=input_data.entity_type,
                total_records_a=len(records_a),
                total_records_b=len(records_b),
                matched_records=matched_count,
                mismatches=mismatches[:50],  # Primeiros 50 para output compacto
                auto_resolved_count=auto_resolved_count,
                unresolved_count=unresolved_count,
                reconciliation_report_url=report_url,
                duration_seconds=duration,
            )

            logger.info(
                _("Reconciliação concluída: {matched} consistentes, {unresolved} inconsistências").format(
                    matched=matched_count,
                    unresolved=unresolved_count,
                ),
                extra={
                    "tenant_id": tenant.tenant_code,
                    "reconciliation_id": reconciliation_id,
                },
            )

            return output

        except Exception as e:
            reconciliations_total.labels(
                tenant_id=tenant.tenant_code,
                source_a=input_data.source_a,
                source_b=input_data.source_b,
                status="error",
            ).inc()
            logger.error(_("Erro na reconciliação: {error}").format(error=str(e)))
            raise ReconciliationException(
                message=_("Falha ao reconciliar fontes de dados"),
                details={"error": str(e)},
            )

    async def _extract_records(
        self,
        source: str,
        entity_type: str,
        date_start: datetime | None,
        date_end: datetime | None,
        mode: str,
    ) -> list[dict[str, Any]]:
        """Extrai registros de um sistema fonte (stub)."""
        # Stub: retorna dados simulados
        if mode == "incremental":
            count = 150
        else:
            count = 5000

        return [
            {
                "id": f"{source}-{entity_type}-{i}",
                "entity_type": entity_type,
                "patient_id": f"PAT-{i % 100}",
                "name": f"Patient {i}",
                "status": "active" if i % 10 != 0 else "inactive",
                "last_updated": datetime.utcnow(),
            }
            for i in range(count)
        ]

    async def _build_correlation_map(
        self,
        records_a: list[dict[str, Any]],
        records_b: list[dict[str, Any]],
        entity_type: str,
    ) -> dict[str, str]:
        """Mapeia IDs entre sistemas usando correlation keys (CPF, prontuário, etc)."""
        # Stub: mapeia por patient_id
        map_a = {rec["patient_id"]: rec["id"] for rec in records_a}
        map_b = {rec["patient_id"]: rec["id"] for rec in records_b}

        correlation = {}
        for patient_id, id_a in map_a.items():
            if patient_id in map_b:
                correlation[id_a] = map_b[patient_id]

        return correlation

    async def _detect_mismatches(
        self,
        records_a: list[dict[str, Any]],
        records_b: list[dict[str, Any]],
        correlation_map: dict[str, str],
        entity_type: str,
    ) -> list[MismatchDetail]:
        """Detecta inconsistências entre registros."""
        mismatches = []

        records_b_map = {rec["id"]: rec for rec in records_b}

        for rec_a in records_a:
            id_b = correlation_map.get(rec_a["id"])

            # Missing em B
            if not id_b:
                mismatches.append(
                    MismatchDetail(
                        entity_id_source_a=rec_a["id"],
                        entity_id_source_b=None,
                        mismatch_type="missing",
                        severity="high",
                    )
                )
                continue

            rec_b = records_b_map.get(id_b)
            if not rec_b:
                continue

            # Field mismatch
            if rec_a.get("status") != rec_b.get("status"):
                mismatches.append(
                    MismatchDetail(
                        entity_id_source_a=rec_a["id"],
                        entity_id_source_b=id_b,
                        mismatch_type="field_mismatch",
                        field_name="status",
                        value_source_a=rec_a.get("status"),
                        value_source_b=rec_b.get("status"),
                        severity="medium",
                    )
                )

        return mismatches

    async def _auto_resolve_mismatches(
        self,
        mismatches: list[MismatchDetail],
        priority_source: str,
        source_a: str,
        source_b: str,
    ) -> int:
        """Resolve inconsistências automaticamente com base no sistema prioritário."""
        resolved = 0
        for mismatch in mismatches:
            if mismatch.mismatch_type == "field_mismatch" and mismatch.severity in ["low", "medium"]:
                # Simula resolução: copia valor do sistema prioritário para o outro
                if priority_source == "source_a":
                    mismatch.resolution_action = f"update_{source_b}_field_{mismatch.field_name}"
                else:
                    mismatch.resolution_action = f"update_{source_a}_field_{mismatch.field_name}"

                mismatch.auto_resolved = True
                resolved += 1

        return resolved

    async def _generate_reconciliation_report(
        self,
        reconciliation_id: str,
        mismatches: list[MismatchDetail],
        input_data: ReconcileDataSourcesInput,
    ) -> str:
        """Gera relatório detalhado em CSV/JSON e armazena em object storage."""
        # Stub: retorna URL simulada
        return f"s3://healthcare-reports/reconciliation/{reconciliation_id}.csv"
