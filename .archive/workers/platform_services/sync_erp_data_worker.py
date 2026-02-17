"""
Worker para sincronização bidirecional de dados ERP via CDC.

Processa eventos CDC (Change Data Capture) do Debezium, sincroniza dados
demográficos de pacientes, procedimentos e atendimentos entre Tasy/MV Soul
e o data lake centralizado.

Padrões:
- Protocolo ABC + Stub implementation
- Modelos Pydantic com i18n
- Decoradores @require_tenant e @track_task_execution
- Conformidade LGPD com hash de identificadores
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_client import TasyClientProtocol
from healthcare_platform.shared.integrations.mv_soul_client import MvSoulClientProtocol as MVSoulClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)

# Métricas Prometheus
sync_operations_total = Counter(
    "sync_erp_operations_total",
    "Total de operações de sincronização ERP",
    ["tenant_id", "source_system", "operation_type", "status"],
)

sync_duration_seconds = Histogram(
    "sync_erp_duration_seconds",
    "Duração das operações de sincronização ERP",
    ["tenant_id", "source_system", "operation_type"],
)

sync_errors_total = Counter(
    "sync_erp_errors_total",
    "Total de erros de sincronização ERP",
    ["tenant_id", "source_system", "error_type"],
)

sync_records_gauge = Gauge(
    "sync_erp_records_pending",
    "Registros pendentes de sincronização",
    ["tenant_id", "source_system", "entity_type"],
)


class ERPSyncException(DomainException):
    """Exceção lançada quando ocorrem erros na sincronização ERP."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            bpmn_error_code="ERPSyncError",
            details=details or {},
        )
        self.error_code = "ERP_SYNC_ERROR"


# ============================================================================
# Modelos Pydantic
# ============================================================================


class SyncERPDataInput(BaseModel):
    """Input para sincronização de dados ERP."""

    source_system: Literal["tasy", "mv_soul"] = Field(
        ..., description=_("Sistema ERP de origem (tasy ou mv_soul)")
    )
    entity_type: Literal["patient", "procedure", "encounter"] = Field(
        ..., description=_("Tipo de entidade a sincronizar")
    )
    cdc_event: dict[str, Any] = Field(
        ..., description=_("Evento CDC do Debezium com payload")
    )
    operation: Literal["create", "update", "delete"] = Field(
        ..., description=_("Operação CDC (create/update/delete)")
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp do evento CDC"),
    )
    force_sync: bool = Field(
        False, description=_("Forçar sincronização mesmo se não houver mudanças")
    )


class SyncERPDataOutput(BaseModel):
    """Output da sincronização de dados ERP."""

    sync_id: str = Field(..., description=_("ID único da sincronização"))
    source_system: str = Field(..., description=_("Sistema de origem"))
    entity_type: str = Field(..., description=_("Tipo de entidade"))
    operation: str = Field(..., description=_("Operação realizada"))
    records_processed: int = Field(..., description=_("Registros processados"))
    records_synced: int = Field(..., description=_("Registros sincronizados"))
    records_failed: int = Field(..., description=_("Registros com falha"))
    sync_status: Literal["success", "partial", "failed"] = Field(
        ..., description=_("Status geral da sincronização")
    )
    conflicts_detected: int = Field(
        0, description=_("Conflitos de dados detectados")
    )
    duration_ms: int = Field(..., description=_("Duração em milissegundos"))
    synced_at: datetime = Field(
        default_factory=datetime.utcnow,
        description=_("Timestamp da sincronização"),
    )
    error_details: str | None = Field(
        None, description=_("Detalhes de erro se houver")
    )


# ============================================================================
# Protocol e Implementação
# ============================================================================


class SyncERPDataProtocol(ABC):
    """Protocolo para sincronização de dados ERP."""

    @abstractmethod
    async def sync_patient_data(
        self,
        cdc_event: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        """
        Sincroniza dados demográficos de pacientes.

        Args:
            cdc_event: Evento CDC do Debezium
            operation: Operação (create/update/delete)

        Returns:
            Dados sincronizados
        """
        pass

    @abstractmethod
    async def sync_procedure_data(
        self,
        cdc_event: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        """
        Sincroniza dados de procedimentos realizados.

        Args:
            cdc_event: Evento CDC do Debezium
            operation: Operação (create/update/delete)

        Returns:
            Dados sincronizados
        """
        pass

    @abstractmethod
    async def sync_encounter_data(
        self,
        cdc_event: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        """
        Sincroniza dados de atendimentos/internações.

        Args:
            cdc_event: Evento CDC do Debezium
            operation: Operação (create/update/delete)

        Returns:
            Dados sincronizados
        """
        pass

    @abstractmethod
    async def detect_conflicts(
        self,
        source_data: dict[str, Any],
        target_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Detecta conflitos entre dados de origem e destino.

        Args:
            source_data: Dados do sistema de origem
            target_data: Dados do data lake

        Returns:
            Lista de conflitos detectados
        """
        pass


class SyncERPDataStub(SyncERPDataProtocol):
    """Implementação stub para sincronização ERP."""

    def __init__(
        self,
        tasy_client: TasyClientProtocol,
        mv_soul_client: MVSoulClientProtocol,
    ):
        self.tasy_client = tasy_client
        self.mv_soul_client = mv_soul_client
        self._dmn = get_dmn_service()

    async def sync_patient_data(
        self,
        cdc_event: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        """Sincroniza dados demográficos de pacientes."""
        payload = cdc_event.get("payload", {})
        after = payload.get("after", {})

        patient_data = {
            "patient_id": after.get("patient_id"),
            "name": after.get("name"),
            "birth_date": after.get("birth_date"),
            "gender": after.get("gender"),
            "cpf": after.get("cpf"),
            "address": after.get("address"),
            "phone": after.get("phone"),
            "email": after.get("email"),
            "operation": operation,
            "synced_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            _("Dados demográficos sincronizados"),
            extra={
                "patient_id_hash": hashlib.sha256(
                    str(after.get("patient_id", "")).encode()
                ).hexdigest()[:16],
                "operation": operation,
            },
        )

        return patient_data

    async def sync_procedure_data(
        self,
        cdc_event: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        """Sincroniza dados de procedimentos."""
        payload = cdc_event.get("payload", {})
        after = payload.get("after", {})

        procedure_data = {
            "procedure_id": after.get("procedure_id"),
            "patient_id": after.get("patient_id"),
            "code": after.get("code"),
            "description": after.get("description"),
            "performed_date": after.get("performed_date"),
            "performer": after.get("performer"),
            "cost": after.get("cost"),
            "operation": operation,
            "synced_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            _("Procedimento sincronizado"),
            extra={
                "procedure_id": after.get("procedure_id"),
                "operation": operation,
            },
        )

        return procedure_data

    async def sync_encounter_data(
        self,
        cdc_event: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        """Sincroniza dados de atendimentos."""
        payload = cdc_event.get("payload", {})
        after = payload.get("after", {})

        encounter_data = {
            "encounter_id": after.get("encounter_id"),
            "patient_id": after.get("patient_id"),
            "admission_date": after.get("admission_date"),
            "discharge_date": after.get("discharge_date"),
            "encounter_type": after.get("encounter_type"),
            "department": after.get("department"),
            "attending_physician": after.get("attending_physician"),
            "diagnosis": after.get("diagnosis"),
            "operation": operation,
            "synced_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            _("Atendimento sincronizado"),
            extra={
                "encounter_id": after.get("encounter_id"),
                "operation": operation,
            },
        )

        return encounter_data

    async def detect_conflicts(
        self,
        source_data: dict[str, Any],
        target_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Detecta conflitos entre dados de origem e destino."""
        conflicts = []

        # Verificar campos críticos
        critical_fields = ["patient_id", "cpf", "birth_date"]
        for field in critical_fields:
            if source_data.get(field) != target_data.get(field):
                conflicts.append(
                    {
                        "field": field,
                        "source_value": source_data.get(field),
                        "target_value": target_data.get(field),
                        "detected_at": datetime.utcnow().isoformat(),
                    }
                )

        return conflicts


# ============================================================================
# Função de Execução
# ============================================================================


@require_tenant
@track_task_execution
async def execute(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Executa sincronização de dados ERP via CDC.

    Args:
        input_data: Dados de entrada validados

    Returns:
        Resultado da sincronização

    Raises:
        ERPSyncException: Se houver erro na sincronização
    """
    tenant = get_required_tenant()
    parsed_input = SyncERPDataInput(**input_data)


    sync_id = (
        f"sync_{parsed_input.source_system}_{parsed_input.entity_type}_"
        f"{int(parsed_input.timestamp.timestamp())}"
    )

    logger.info(
        _("Iniciando sincronização ERP"),
        extra={
            "tenant_id": tenant.tenant_code,
            "sync_id": sync_id,
            "source_system": parsed_input.source_system,
            "entity_type": parsed_input.entity_type,
            "operation": parsed_input.operation,
        },
    )

    start_time = datetime.utcnow()
    # DMN decision support
    _dmn = get_dmn_service()
    try:
        _dmn_config = _dmn.evaluate(
            tenant_id=tenant.tenant_code,
            category='infrastructure',
            table_name='config/infra_002',
            inputs={'source_system': parsed_input.source_system, 'entity_type': parsed_input.entity_type, 'operation': parsed_input.operation},
        )
    except (FileNotFoundError, ValueError):
        _dmn_config = {}



    try:
        # Inicializar clientes ERP (mock)
        from healthcare_platform.shared.integrations.tasy_client import StubTasyClient
        from healthcare_platform.shared.integrations.mv_soul_client import StubMvSoulClient

        tasy_client = StubTasyClient()
        mv_soul_client = StubMvSoulClient(tenant_context=tenant)

        service = SyncERPDataStub(
            tasy_client=tasy_client,
            mv_soul_client=mv_soul_client,
        )

        # Sincronizar dados conforme tipo de entidade
        synced_data = None
        if parsed_input.entity_type == "patient":
            synced_data = await service.sync_patient_data(
                cdc_event=parsed_input.cdc_event,
                operation=parsed_input.operation,
            )
        elif parsed_input.entity_type == "procedure":
            synced_data = await service.sync_procedure_data(
                cdc_event=parsed_input.cdc_event,
                operation=parsed_input.operation,
            )
        elif parsed_input.entity_type == "encounter":
            synced_data = await service.sync_encounter_data(
                cdc_event=parsed_input.cdc_event,
                operation=parsed_input.operation,
            )

        # Detectar conflitos
        conflicts = await service.detect_conflicts(
            source_data=synced_data or {},
            target_data={},  # Simular dados do data lake
        )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        output = SyncERPDataOutput(
            sync_id=sync_id,
            source_system=parsed_input.source_system,
            entity_type=parsed_input.entity_type,
            operation=parsed_input.operation,
            records_processed=1,
            records_synced=1 if synced_data else 0,
            records_failed=0,
            sync_status="success",
            conflicts_detected=len(conflicts),
            duration_ms=duration_ms,
        )

        # Métricas
        sync_operations_total.labels(
            tenant_id=tenant.tenant_code,
            source_system=parsed_input.source_system,
            operation_type=parsed_input.operation,
            status="success",
        ).inc()

        sync_duration_seconds.labels(
            tenant_id=tenant.tenant_code,
            source_system=parsed_input.source_system,
            operation_type=parsed_input.operation,
        ).observe(duration_ms / 1000.0)

        sync_records_gauge.labels(
            tenant_id=tenant.tenant_code,
            source_system=parsed_input.source_system,
            entity_type=parsed_input.entity_type,
        ).set(0)

        logger.info(
            _("Sincronização ERP concluída com sucesso"),
            extra={
                "tenant_id": tenant.tenant_code,
                "sync_id": sync_id,
                "records_synced": output.records_synced,
                "conflicts_detected": output.conflicts_detected,
                "duration_ms": duration_ms,
            },
        )

        return output.model_dump()

    except Exception as e:
        sync_errors_total.labels(
            tenant_id=tenant.tenant_code,
            source_system=parsed_input.source_system,
            error_type=type(e).__name__,
        ).inc()

        logger.error(
            _("Erro na sincronização ERP"),
            extra={
                "tenant_id": tenant.tenant_code,
                "sync_id": sync_id,
                "error": str(e),
            },
            exc_info=True,
        )
        raise ERPSyncException(
            message=_("Falha ao sincronizar dados ERP"),
            details={"sync_id": sync_id, "error": str(e)},
        )


# Topic Kafka
TOPIC = "platform.services.sync-erp-data"
