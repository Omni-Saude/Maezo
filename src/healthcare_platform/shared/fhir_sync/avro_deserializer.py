"""Avro deserializer using Schema Registry REST API.

Confluent Avro wire format:
  byte 0    : magic byte (0x00)
  bytes 1-4 : schema ID (big-endian int32)
  bytes 5+  : Avro binary payload

This module fetches the Avro schema from Schema Registry by ID,
caches it, and deserializes the payload using fastavro.
"""

from __future__ import annotations

import datetime
import io
import logging
import struct
from typing import Any

import fastavro
import httpx

logger = logging.getLogger(__name__)

# Schema cache: schema_id -> parsed avro schema
_schema_cache: dict[int, dict] = {}


def _fetch_schema(schema_registry_url: str, schema_id: int) -> dict:
    """Fetch Avro schema from Confluent Schema Registry."""
    if schema_id in _schema_cache:
        return _schema_cache[schema_id]

    url = f"{schema_registry_url}/schemas/ids/{schema_id}"
    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    import json
    schema = json.loads(resp.json()["schema"])
    parsed = fastavro.parse_schema(schema)
    _schema_cache[schema_id] = parsed
    logger.info("Cached Avro schema id=%d", schema_id)
    return parsed


def deserialize_avro(
    raw_bytes: bytes | None,
    schema_registry_url: str = "http://schema_registry:8081",
) -> dict[str, Any] | None:
    """Deserialize a Confluent Avro-encoded Kafka message value.

    Returns None for null, tombstone, or unparseable messages.
    """
    if not raw_bytes or len(raw_bytes) < 5:
        return None

    # Check magic byte
    if raw_bytes[0] != 0x00:
        # Not Avro wire format — try JSON fallback
        try:
            import json
            return json.loads(raw_bytes)
        except (ValueError, UnicodeDecodeError):
            logger.debug("Skipping non-Avro/non-JSON message (%d bytes)", len(raw_bytes))
            return None

    # Extract schema ID (bytes 1-4, big-endian)
    schema_id = struct.unpack(">I", raw_bytes[1:5])[0]

    try:
        schema = _fetch_schema(schema_registry_url, schema_id)
    except Exception:
        logger.exception("Failed to fetch schema id=%d", schema_id)
        return None

    # Deserialize Avro payload (bytes 5+)
    try:
        reader = io.BytesIO(raw_bytes[5:])
        record = fastavro.schemaless_reader(reader, schema)
        return _convert_datetimes(record)
    except Exception:
        logger.exception("Failed to deserialize Avro payload (schema_id=%d)", schema_id)
        return None


def _convert_datetimes(obj: Any) -> Any:
    """Recursively convert datetime/date objects and epoch millis to ISO 8601 strings."""
    if isinstance(obj, dict):
        return {k: _convert_datetimes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_datetimes(item) for item in obj]
    if isinstance(obj, datetime.datetime):
        return obj.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    # Detect epoch millis (int > 1_000_000_000_000 = year ~2001+)
    if isinstance(obj, int) and obj > 1_000_000_000_000:
        try:
            dt = datetime.datetime.fromtimestamp(obj / 1000, tz=datetime.timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, OSError, OverflowError):
            pass
    return obj
