"""Parse Debezium CDC events and map to BPM process actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OperationType(str, Enum):
    CREATE = "c"
    UPDATE = "u"
    DELETE = "d"
    READ = "r"  # snapshot


@dataclass(frozen=True)
class CDCEvent:
    """Parsed CDC event from Debezium."""

    operation: OperationType
    table_name: str
    record_data: dict[str, Any]
    before_data: dict[str, Any] | None
    timestamp_ms: int
    source_db: str


@dataclass(frozen=True)
class ProcessAction:
    """Action to perform on the BPM engine."""

    action_type: str  # "start" or "correlate"
    process_key: str | None  # for start
    message_name: str | None  # for correlate
    business_key: str
    variables: dict[str, Any]
    tenant_id: str


# Table -> (action_type, process_key_or_message, business_key_field)
# Real Tasy table names (ATENDIMENTO_PACIENTE, CONTA_PACIENTE, PROCEDIMENTO_PACIENTE)
TABLE_PROCESS_MAP: dict[str, dict[str, tuple[str, str, str]]] = {
    # Admissão do paciente → inicia processo de agendamento/registro (SP_RC_001)
    "ATENDIMENTO_PACIENTE": {
        "c": ("start", "SP_RC_001_Scheduling_Registration", "nr_atendimento"),
    },
    # Conta hospitalar → inicia orquestrador do ciclo de receita (SP_RC_000)
    "CONTA_PACIENTE": {
        "c": ("start", "SP_RC_000", "nr_conta"),
    },
    # Procedimento/item faturável → correlaciona com processo de RC em andamento
    "PROCEDIMENTO_PACIENTE": {
        "c": ("correlate", "MSG_CHARGE_CAPTURED", "nr_conta"),
    },
}


def parse_cdc_event(raw: dict[str, Any]) -> CDCEvent | None:
    """Parse a raw Debezium CDC message value into a CDCEvent."""
    op = raw.get("op")
    if op is None:
        logger.warning("CDC message missing 'op' field, skipping")
        return None

    try:
        operation = OperationType(op)
    except ValueError:
        logger.warning("Unknown CDC operation type: %s", op)
        return None

    source = raw.get("source", {})
    table_name = source.get("table", "UNKNOWN")
    timestamp_ms = source.get("ts_ms", 0)
    source_db = source.get("db", "")

    record_data = raw.get("after") or {}
    before_data = raw.get("before")

    return CDCEvent(
        operation=operation,
        table_name=table_name,
        record_data=record_data,
        before_data=before_data,
        timestamp_ms=timestamp_ms,
        source_db=source_db,
    )


def map_to_process_action(
    event: CDCEvent, tenant_id: str = "austa"
) -> ProcessAction | None:
    """Map a CDC event to a BPM process action, or None if no mapping exists."""
    table_ops = TABLE_PROCESS_MAP.get(event.table_name)
    if not table_ops:
        logger.debug("No process mapping for table %s", event.table_name)
        return None

    mapping = table_ops.get(event.operation.value)
    if not mapping:
        logger.debug(
            "No mapping for %s.%s", event.table_name, event.operation.value
        )
        return None

    action_type, key_or_msg, bk_field = mapping
    business_key = str(event.record_data.get(bk_field, ""))
    if not business_key:
        logger.warning(
            "Missing business key field %s in %s record",
            bk_field,
            event.table_name,
        )
        return None

    variables = {
        "cdc_table": event.table_name,
        "cdc_operation": event.operation.value,
        "cdc_timestamp_ms": event.timestamp_ms,
        **{k: v for k, v in event.record_data.items() if v is not None},
    }

    return ProcessAction(
        action_type=action_type,
        process_key=key_or_msg if action_type == "start" else None,
        message_name=key_or_msg if action_type == "correlate" else None,
        business_key=business_key,
        variables=variables,
        tenant_id=tenant_id,
    )
