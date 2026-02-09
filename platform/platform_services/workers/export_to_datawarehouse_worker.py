"""
Worker para exportação de dados para Data Warehouse/Data Lake.

Extrai dados transformados do sistema operacional e gera arquivos
Parquet/CSV para ingestão em BI/DW. Suporta full-refresh e incremental.

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

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)

# Prometheus metrics
exports_total = Counter(
    "exports_total",
    "Total data warehouse exports executed",
    ["tenant_id", "entity_type", "format", "status"],
)
export_duration_seconds = Histogram(
    "export_duration_seconds",
    "Duration of data warehouse export operations",
    ["tenant_id", "entity_type", "format"],
)
export_records_gauge = Gauge(
    "export_records_gauge",
    "Number of records in last export",
    ["tenant_id", "entity_type", "format"],
)

TOPIC = "platform.export_to_datawarehouse"


class DataWarehouseExportException(DomainException):
    """Exceção de exportação para Data Warehouse."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="DW_EXPORT_ERROR",
            details=details or {},
        )


class ExportToDataWarehouseInput(BaseModel):
    """Input para exportação de dados para Data Warehouse."""

    entity_type: str = Field(
        ...,
        description=_("Tipo de entidade: patient, encounter, claim, revenue, clinical_event"),
    )
    export_mode: str = Field(
        default="incremental",
        description=_("Modo: incremental (últimas 24h) ou full (todos registros)"),
    )
    date_start: datetime | None = Field(None, description=_("Data inicial para exportação incremental"))
    date_end: datetime | None = Field(None, description=_("Data final para exportação incremental"))
    output_format: str = Field(default="parquet", description=_("Formato de saída: parquet, csv, json"))
    compression: str = Field(default="snappy", description=_("Compressão: snappy, gzip, none"))
    partition_by: list[str] = Field(
        default_factory=lambda: ["year", "month"],
        description=_("Campos para particionamento (year, month, day, tenant_id)"),
    )
    include_deleted: bool = Field(default=False, description=_("Incluir registros soft-deleted"))
    anonymize_pii: bool = Field(default=True, description=_("Aplicar anonimização de PII (LGPD)"))


class ExportToDataWarehouseOutput(BaseModel):
    """Output da exportação para Data Warehouse."""

    export_id: str = Field(..., description=_("ID único da exportação"))
    entity_type: str = Field(..., description=_("Tipo de entidade exportada"))
    total_records: int = Field(..., description=_("Total de registros exportados"))
    output_format: str = Field(..., description=_("Formato de saída"))
    file_paths: list[str] = Field(default_factory=list, description=_("Caminhos dos arquivos gerados (S3/GCS)"))
    file_size_bytes: int = Field(..., description=_("Tamanho total dos arquivos em bytes"))
    partitions: list[dict[str, Any]] = Field(
        default_factory=list,
        description=_("Partições geradas (ex: year=2025/month=02)"),
    )
    anonymized_fields: list[str] = Field(
        default_factory=list,
        description=_("Campos anonimizados para LGPD"),
    )
    executed_at: datetime = Field(default_factory=datetime.utcnow, description=_("Timestamp de execução"))
    duration_seconds: float = Field(..., description=_("Duração da exportação em segundos"))


class ExportToDataWarehouseProtocol(ABC):
    """Protocol para exportação de dados para Data Warehouse/Data Lake."""

    @abstractmethod
    async def execute(self, input_data: ExportToDataWarehouseInput) -> ExportToDataWarehouseOutput:
        """
        Exporta dados transformados para DW/Data Lake.

        Args:
            input_data: Parâmetros da exportação

        Returns:
            ExportToDataWarehouseOutput com caminhos dos arquivos gerados

        Raises:
            DataWarehouseExportException: Erro na exportação
        """
        pass


class ExportToDataWarehouseStub(ExportToDataWarehouseProtocol):
    """Stub implementation para exportação de dados para Data Warehouse."""

    @require_tenant
    @track_task_execution
    async def execute(self, input_data: ExportToDataWarehouseInput) -> ExportToDataWarehouseOutput:
        """
        Exporta dados transformados para DW/Data Lake.

        Fluxo:
        1. Extrai registros do banco operacional (janela de tempo se incremental)
        2. Aplica transformações (flatten nested, cast types)
        3. Anonimiza PII se anonymize_pii=True (hash CPF, nome, etc)
        4. Particiona por campos configurados (year, month, tenant_id)
        5. Gera arquivos Parquet/CSV com compressão
        6. Armazena em object storage (S3/GCS)
        7. Atualiza métricas Prometheus

        LGPD: Anonimiza campos sensíveis antes de exportar.
        """
        tenant = get_required_tenant()
        start_time = datetime.utcnow()

        logger.info(
            _("Iniciando exportação para Data Warehouse: {entity_type}, modo={mode}").format(
                entity_type=input_data.entity_type,
                mode=input_data.export_mode,
            ),
            extra={
                "tenant_id": tenant.id,
                "output_format": input_data.output_format,
            },
        )

        try:
            # Extrai registros do banco operacional
            records = await self._extract_records(
                entity_type=input_data.entity_type,
                date_start=input_data.date_start,
                date_end=input_data.date_end,
                mode=input_data.export_mode,
                include_deleted=input_data.include_deleted,
            )

            logger.info(
                _("Extraídos {count} registros de {entity_type}").format(
                    count=len(records),
                    entity_type=input_data.entity_type,
                )
            )

            # Aplica transformações (flatten, cast)
            transformed_records = await self._transform_records(records, input_data.entity_type)

            # Anonimiza PII (LGPD)
            anonymized_fields = []
            if input_data.anonymize_pii:
                anonymized_fields = await self._anonymize_pii(transformed_records, input_data.entity_type)

            # Particiona registros
            partitions = await self._partition_records(
                records=transformed_records,
                partition_by=input_data.partition_by,
            )

            # Gera arquivos Parquet/CSV
            file_paths = []
            total_size = 0

            for partition_key, partition_records in partitions.items():
                file_path, file_size = await self._write_partition_file(
                    records=partition_records,
                    partition_key=partition_key,
                    entity_type=input_data.entity_type,
                    output_format=input_data.output_format,
                    compression=input_data.compression,
                )
                file_paths.append(file_path)
                total_size += file_size

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Atualiza métricas Prometheus
            exports_total.labels(
                tenant_id=tenant.id,
                entity_type=input_data.entity_type,
                format=input_data.output_format,
                status="success",
            ).inc()

            export_duration_seconds.labels(
                tenant_id=tenant.id,
                entity_type=input_data.entity_type,
                format=input_data.output_format,
            ).observe(duration)

            export_records_gauge.labels(
                tenant_id=tenant.id,
                entity_type=input_data.entity_type,
                format=input_data.output_format,
            ).set(len(records))

            export_id = f"EXP-{tenant.id}-{int(start_time.timestamp())}"

            output = ExportToDataWarehouseOutput(
                export_id=export_id,
                entity_type=input_data.entity_type,
                total_records=len(records),
                output_format=input_data.output_format,
                file_paths=file_paths,
                file_size_bytes=total_size,
                partitions=[{"key": k, "records": len(v)} for k, v in partitions.items()],
                anonymized_fields=anonymized_fields,
                duration_seconds=duration,
            )

            logger.info(
                _("Exportação concluída: {records} registros, {files} arquivos, {size_mb} MB").format(
                    records=len(records),
                    files=len(file_paths),
                    size_mb=round(total_size / 1024 / 1024, 2),
                ),
                extra={
                    "tenant_id": tenant.id,
                    "export_id": export_id,
                },
            )

            return output

        except Exception as e:
            exports_total.labels(
                tenant_id=tenant.id,
                entity_type=input_data.entity_type,
                format=input_data.output_format,
                status="error",
            ).inc()
            logger.error(_("Erro na exportação: {error}").format(error=str(e)))
            raise DataWarehouseExportException(
                message=_("Falha ao exportar dados para Data Warehouse"),
                details={"error": str(e)},
            )

    async def _extract_records(
        self,
        entity_type: str,
        date_start: datetime | None,
        date_end: datetime | None,
        mode: str,
        include_deleted: bool,
    ) -> list[dict[str, Any]]:
        """Extrai registros do banco operacional (stub)."""
        if mode == "incremental":
            count = 5000
        else:
            count = 100000

        return [
            {
                "id": f"{entity_type}-{i}",
                "entity_type": entity_type,
                "patient_id": f"PAT-{i % 1000}",
                "tenant_id": "TENANT-001",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "status": "active",
                "data": {"key": f"value-{i}"},
            }
            for i in range(count)
        ]

    async def _transform_records(
        self,
        records: list[dict[str, Any]],
        entity_type: str,
    ) -> list[dict[str, Any]]:
        """Aplica transformações: flatten nested objects, cast types."""
        # Stub: retorna registros sem transformação
        return records

    async def _anonymize_pii(
        self,
        records: list[dict[str, Any]],
        entity_type: str,
    ) -> list[str]:
        """Anonimiza campos PII (hash SHA256) para LGPD."""
        anonymized_fields = []

        # Campos PII por entity_type
        pii_fields_map = {
            "patient": ["patient_id", "cpf", "name", "email", "phone"],
            "encounter": ["patient_id"],
            "claim": ["patient_id", "beneficiary_name"],
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

    async def _partition_records(
        self,
        records: list[dict[str, Any]],
        partition_by: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Particiona registros por campos (year, month, tenant_id)."""
        partitions: dict[str, list[dict[str, Any]]] = {}

        for record in records:
            partition_key_parts = []
            for field in partition_by:
                if field == "year":
                    partition_key_parts.append(f"year={record['created_at'].year}")
                elif field == "month":
                    partition_key_parts.append(f"month={record['created_at'].month:02d}")
                elif field == "day":
                    partition_key_parts.append(f"day={record['created_at'].day:02d}")
                elif field == "tenant_id":
                    partition_key_parts.append(f"tenant_id={record['tenant_id']}")

            partition_key = "/".join(partition_key_parts)

            if partition_key not in partitions:
                partitions[partition_key] = []

            partitions[partition_key].append(record)

        return partitions

    async def _write_partition_file(
        self,
        records: list[dict[str, Any]],
        partition_key: str,
        entity_type: str,
        output_format: str,
        compression: str,
    ) -> tuple[str, int]:
        """Gera arquivo Parquet/CSV para partição e retorna (path, size)."""
        # Stub: simula escrita de arquivo
        file_name = f"{entity_type}.{output_format}"
        if compression != "none":
            file_name += f".{compression}"

        file_path = f"s3://healthcare-datalake/{partition_key}/{file_name}"
        file_size = len(records) * 512  # Simula tamanho médio de 512 bytes/record

        return file_path, file_size
