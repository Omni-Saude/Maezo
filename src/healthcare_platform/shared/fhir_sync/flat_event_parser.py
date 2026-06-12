"""Parser for Debezium flat CDC events (ExtractNewRecordState SMT).

Unlike the envelope format used by cdc_bridge (where data is in `after`),
flat records have the business data directly at the root, with Debezium
metadata prefixed with `__`:

  {
    "NR_SEQ_INTERNO": 1073,
    "CD_CONVENIO": 27,
    ...
    "__op": "c",
    "__ts_ms": 1729847234000,
    "__source_table": "ATEND_CATEGORIA_CONVENIO",
    "__source_scn": "6764953663465"
  }

Tombstones (deletes) have __deleted="true" and "value":null in some cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class OperationType(str, Enum):
    CREATE = "c"
    UPDATE = "u"
    DELETE = "d"
    READ = "r"  # snapshot


@dataclass(frozen=True)
class FlatCDCEvent:
    """Normalized CDC event from flat (ExtractNewRecordState) format."""

    table_name: str
    operation: OperationType
    record_data: dict[str, Any]
    before_data: dict[str, Any] | None
    timestamp_ms: int


# Metadata keys added by ExtractNewRecordState
_METADATA_KEYS = {
    "__op", "__ts_ms", "__source_table", "__source_scn",
    "__source_ts_ms", "__source_db", "__source_schema",
    "__source_name", "__source_connector", "__source_version",
    "__deleted",
}


def parse_flat_cdc_event(raw: dict[str, Any]) -> FlatCDCEvent | None:
    """Parse a flat CDC event (after ExtractNewRecordState SMT).

    Returns None for tombstones or unparseable messages.
    """
    if raw is None:
        return None

    # Tombstone check
    if raw.get("__deleted") == "true":
        operation = OperationType.DELETE
    else:
        op_str = raw.get("__op", "c")
        try:
            operation = OperationType(op_str)
        except ValueError:
            operation = OperationType.CREATE

    # Table name from metadata
    table_name = raw.get("__source_table", "")
    if not table_name:
        return None

    # Timestamp
    ts_ms = raw.get("__ts_ms") or raw.get("__source_ts_ms") or 0

    # Business data = all fields EXCEPT __* metadata
    record_data = {k: v for k, v in raw.items() if k not in _METADATA_KEYS and not k.startswith("__")}

    return FlatCDCEvent(
        table_name=table_name,
        operation=operation,
        record_data=record_data,
        before_data=None,  # ExtractNewRecordState doesn't keep before by default
        timestamp_ms=int(ts_ms) if ts_ms else 0,
    )
