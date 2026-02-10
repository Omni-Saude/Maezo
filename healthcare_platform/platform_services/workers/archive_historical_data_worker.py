"""
Worker para arquivamento de dados históricos (cold storage).

Move registros antigos para storage de baixo custo:
- Mantém integridade referencial
- Conformidade com LGPD (retenção de dados)
- Soft delete → Hard delete após período de retenção
- Compressão e particionamento por ano/mês

Padrão: Protocol ABC + Stub implementation
Decorators: @require_tenant, @track_task_execution
Métricas: Prometheus Counter, Histogram, Gauge
LGPD: Respeita políticas de retenção e anonimização
i18n: Todas strings user-facing via _()
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Prometheus metrics
archive_operations_total = Counter(
    "archive_operations_total",
    "Total data archival operations executed",
    ["tenant_id", "entity_type", "status"],
)
archive_duration_seconds = Histogram(
    "archive_duration_seconds",
    "Duration of data archival operation",
    ["tenant_id", "entity_type"],
)
archived_records_gauge = Gauge(
    "archived_records_gauge",
    "Number of records archived in last operation",
    ["tenant_id", "entity_type"],
)

TOPIC = "platform.archive_historical_data"


class ArchivalException(DomainException):
    """Exceção de arquivamento de dados."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="ARCHIVAL_ERROR",
            details=details or {},
        )


class ArchiveHistoricalDataInput(BaseModel):
    """Input para arquivamento de dados históricos."""

    entity_type: str = Field(
        ...,
        description=_("Tipo de entidade: patient, encounter, claim, audit_log"),
    )
    retention_days: int = Field(
        default=2555,
        description=_("Período de retenção no storage ativo (7 anos = 2555 dias)"),
    )
    archive_mode: str = Field(
        default="soft_delete",
        description=_("Modo: soft_delete (marca deleted_at), hard_delete (remove físico)"),
    )
    compression: str = Field(default="gzip", description=_("Compressão: gzip, snappy, none"))
    verify_referential_integrity: bool = Field(
        default=True,
        description=_("Verificar integridade referencial antes de arquivar"),
    )
    anonymize_on_archive: bool = Field(
        default=True,
        description=_("Aplicar anonimização de PII antes de mover para cold storage (LGPD)"),
    )


class ArchiveHistoricalDataOutput(BaseModel):
    """Output do arquivamento de dados históricos."""

    archive_id: str = Field(..., description=_("ID único da operação de arquivamento"))
    entity_type: str = Field(..., description=_("Tipo de entidade arquivada"))
    total_records_archived: int = Field(..., description=_("Total de registros arquivados"))
    total_records_deleted: int = Field(default=0, description=_("Total de registros deletados (hard delete)"))
    archive_storage_path: str = Field(..., description=_("Caminho do storage de arquivamento (S3/GCS)"))
    archive_size_bytes: int = Field(..., description=_("Tamanho total do arquivamento em bytes"))
    compression: str = Field(..., description=_("Método de compressão usado"))
    anonymized_fields: list[str] = Field(
        default_factory=list,
        description=_("Campos anonimizados (LGPD)"),
    )
    referential_integrity_verified: bool = Field(
        default=False,
        description=_("Se integridade referencial foi verificada"),
    )
    archived_at: datetime = Field(default_factory=datetime.utcnow, description=_("Timestamp do arquivamento"))
    duration_seconds: float = Field(..., description=_("Duração da operação em segundos"))


class ArchiveHistoricalDataProtocol(ABC):
    """Protocol para arquivamento de dados históricos."""

    @abstractmethod
    async def execute(self, input_data: ArchiveHistoricalDataInput) -> ArchiveHistoricalDataOutput:
        """
        Arquiva dados históricos para cold storage.

        Args:
            input_data: Parâmetros do arquivamento

        Returns:
            ArchiveHistoricalDataOutput com estatísticas

        Raises:
            ArchivalException: Erro no arquivamento
        """
        pass


class ArchiveHistoricalDataStub(ArchiveHistoricalDataProtocol):
    """Stub implementation para arquivamento de dados históricos."""

    @require_tenant
    @track_task_execution
    async def execute(self, input_data: ArchiveHistoricalDataInput) -> ArchiveHistoricalDataOutput:
        """
        Arquiva dados históricos para cold storage.

        Fluxo:
        1. Identifica registros com data de criação > retention_days
        2. Verifica integridade referencial (se habilitado)
        3. Anonimiza PII (se anonymize_on_archive=True)
        4. Move para cold storage (S3 Glacier, GCS Coldline)
        5. Se soft_delete: marca deleted_at
        6. Se hard_delete: remove fisicamente após backup
        7. Atualiza métricas Prometheus

        LGPD:
        - Respeita políticas de retenção (default 7 anos para dados de saúde)
        - Anonimiza PII antes de arquivamento
        - Hard delete após período de retenção legal

        Integridade referencial:
        - Verifica dependências antes de deletar (ex: claims → encounters → patients)
        """
        tenant = get_required_tenant()
        _dmn = get_dmn_service()
        try:
            _dmn_result = _dmn.evaluate(
                tenant_id=tenant.id,
                category='compliance',
                table_name='lgpd/comp_lgpd_001',
                inputs={'entity_type': input_data.entity_type, 'retention_policy': input_data.retention_policy},
            )
        except (FileNotFoundError, ValueError):
            _dmn_result = {}

        start_time = datetime.utcnow()

        logger.info(
            _("Iniciando arquivamento: {entity_type}, retenção={days} dias").format(
                entity_type=input_data.entity_type,
                days=input_data.retention_days,
            ),
            extra={
                "tenant_id": tenant.id,
                "archive_mode": input_data.archive_mode,
            },
        )

        try:
            # Identifica registros elegíveis para arquivamento
            cutoff_date = datetime.utcnow() - timedelta(days=input_data.retention_days)
            records_to_archive = await self._identify_archival_candidates(
                entity_type=input_data.entity_type,
                cutoff_date=cutoff_date,
            )

            logger.info(
                _("Identificados {count} registros para arquivamento").format(
                    count=len(records_to_archive)
                )
            )

            # Verifica integridade referencial
            referential_integrity_verified = False
            if input_data.verify_referential_integrity:
                referential_integrity_verified = await self._verify_referential_integrity(
                    entity_type=input_data.entity_type,
                    records=records_to_archive,
                )

            # Anonimiza PII
            anonymized_fields = []
            if input_data.anonymize_on_archive:
                anonymized_fields = await self._anonymize_records(
                    records=records_to_archive,
                    entity_type=input_data.entity_type,
                )

            # Move para cold storage
            archive_path, archive_size = await self._move_to_cold_storage(
                records=records_to_archive,
                entity_type=input_data.entity_type,
                compression=input_data.compression,
            )

            # Soft delete ou hard delete
            deleted_count = 0
            if input_data.archive_mode == "soft_delete":
                await self._soft_delete_records(records_to_archive)
            elif input_data.archive_mode == "hard_delete":
                deleted_count = await self._hard_delete_records(records_to_archive)

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Atualiza métricas Prometheus
            archive_operations_total.labels(
                tenant_id=tenant.id,
                entity_type=input_data.entity_type,
                status="success",
            ).inc()

            archive_duration_seconds.labels(
                tenant_id=tenant.id,
                entity_type=input_data.entity_type,
            ).observe(duration)

            archived_records_gauge.labels(
                tenant_id=tenant.id,
                entity_type=input_data.entity_type,
            ).set(len(records_to_archive))

            archive_id = f"ARCH-{tenant.id}-{int(start_time.timestamp())}"

            output = ArchiveHistoricalDataOutput(
                archive_id=archive_id,
                entity_type=input_data.entity_type,
                total_records_archived=len(records_to_archive),
                total_records_deleted=deleted_count,
                archive_storage_path=archive_path,
                archive_size_bytes=archive_size,
                compression=input_data.compression,
                anonymized_fields=anonymized_fields,
                referential_integrity_verified=referential_integrity_verified,
                duration_seconds=duration,
            )

            logger.info(
                _("Arquivamento concluído: {count} registros, {size_mb} MB").format(
                    count=len(records_to_archive),
                    size_mb=round(archive_size / 1024 / 1024, 2),
                ),
                extra={
                    "tenant_id": tenant.id,
                    "archive_id": archive_id,
                },
            )

            return output

        except Exception as e:
            archive_operations_total.labels(
                tenant_id=tenant.id,
                entity_type=input_data.entity_type,
                status="error",
            ).inc()
            logger.error(_("Erro no arquivamento: {error}").format(error=str(e)))
            raise ArchivalException(
                message=_("Falha ao arquivar dados históricos"),
                details={"error": str(e)},
            )

    async def _identify_archival_candidates(
        self,
        entity_type: str,
        cutoff_date: datetime,
    ) -> list[dict[str, Any]]:
        """Identifica registros elegíveis para arquivamento (stub)."""
        # Stub: retorna registros simulados
        return [
            {
                "id": f"{entity_type}-{i}",
                "entity_type": entity_type,
                "created_at": cutoff_date - timedelta(days=i),
                "data": {"key": f"value-{i}"},
            }
            for i in range(10000)
        ]

    async def _verify_referential_integrity(
        self,
        entity_type: str,
        records: list[dict[str, Any]],
    ) -> bool:
        """Verifica integridade referencial antes de arquivar (stub)."""
        # Stub: sempre retorna True
        logger.info(
            _("Integridade referencial verificada para {count} registros").format(
                count=len(records)
            )
        )
        return True

    async def _anonymize_records(
        self,
        records: list[dict[str, Any]],
        entity_type: str,
    ) -> list[str]:
        """Anonimiza PII antes de arquivar (LGPD)."""
        anonymized_fields = []

        # Campos PII por entity_type
        pii_fields_map = {
            "patient": ["cpf", "name", "email", "phone"],
            "encounter": ["patient_id"],
            "claim": ["beneficiary_name"],
        }

        pii_fields = pii_fields_map.get(entity_type, [])

        for record in records:
            for field in pii_fields:
                if field in record and record[field]:
                    original_value = str(record[field])
                    record[field] = hashlib.sha256(original_value.encode()).hexdigest()[:16]
                    if field not in anonymized_fields:
                        anonymized_fields.append(field)

        return anonymized_fields

    async def _move_to_cold_storage(
        self,
        records: list[dict[str, Any]],
        entity_type: str,
        compression: str,
    ) -> tuple[str, int]:
        """Move registros para cold storage (S3 Glacier, GCS Coldline) - stub."""
        # Stub: simula escrita
        archive_path = f"s3://healthcare-archive/{entity_type}/archive-{datetime.utcnow().isoformat()}.json.{compression}"
        archive_size = len(records) * 1024  # Simula 1KB/record

        return archive_path, archive_size

    async def _soft_delete_records(self, records: list[dict[str, Any]]) -> None:
        """Marca registros com deleted_at (soft delete) - stub."""
        for record in records:
            record["deleted_at"] = datetime.utcnow()

    async def _hard_delete_records(self, records: list[dict[str, Any]]) -> int:
        """Remove registros fisicamente após backup (hard delete) - stub."""
        # Stub: simula deleção física
        return len(records)
