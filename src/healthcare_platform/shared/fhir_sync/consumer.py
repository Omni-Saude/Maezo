"""Kafka consumer for FHIR Sync — routes CDC events to adapters and HAPI FHIR."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer

logger = logging.getLogger(__name__)

from healthcare_platform.shared.fhir_sync.avro_deserializer import deserialize_avro

from healthcare_platform.shared.cdc_bridge.event_parser import (
    OperationType as EnvelopeOpType,
    parse_cdc_event,
)
from healthcare_platform.shared.fhir_sync.config import FHIRSyncConfig
from healthcare_platform.shared.fhir_sync.dead_letter import DeadLetterHandler
from healthcare_platform.shared.fhir_sync.fhir_writer import FHIRWriter
from healthcare_platform.shared.fhir_sync.health import inc
from healthcare_platform.shared.fhir_sync.avro_deserializer import _convert_datetimes
from healthcare_platform.shared.fhir_sync.flat_event_parser import (
    OperationType,
    parse_flat_cdc_event,
)
from healthcare_platform.shared.fhir_sync.router import TableAdapterRouter, apply_column_map
from healthcare_platform.shared.integrations.fhir_client import FHIRClient


def _parse_event(raw: dict[str, Any], topic: str | None = None):
    """Parse either flat (ExtractNewRecordState) or envelope Debezium format.

    Flat: record data at root with __op, __ts_ms, __source_table fields.
    Envelope: data under 'after' with 'op', 'ts_ms', 'source.table' fields.
    """
    # Detect flat format by presence of __source_table or __op
    if "__source_table" in raw or "__op" in raw:
        event = parse_flat_cdc_event(raw)
        return event
    # Fall back to envelope format
    event = parse_cdc_event(raw)
    return event

logger = logging.getLogger(__name__)


class FHIRSyncConsumer:
    """Consumes CDC events from Kafka and writes FHIR resources."""

    def __init__(
        self,
        config: FHIRSyncConfig,
        router: TableAdapterRouter,
        fhir_writer: FHIRWriter,
        dead_letter: DeadLetterHandler,
    ) -> None:
        self._config = config
        self._router = router
        self._writer = fhir_writer
        self._dlh = dead_letter
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False
        self._fhir_client: FHIRClient | None = None

    async def start(self) -> None:
        kafka = self._config.kafka
        self._consumer = AIOKafkaConsumer(
            *kafka.topics,
            bootstrap_servers=kafka.bootstrap_servers,
            group_id=kafka.consumer_group,
            auto_offset_reset=kafka.auto_offset_reset,
            enable_auto_commit=kafka.enable_auto_commit,
            max_poll_interval_ms=kafka.max_poll_interval_ms,
            session_timeout_ms=kafka.session_timeout_ms,
            # No deserializer — raw bytes handled in consume_loop
            # because Avro needs Schema Registry access
        )
        await self._consumer.start()
        self._running = True

        fhir = self._config.fhir
        self._fhir_client = FHIRClient(
            base_url=fhir.base_url,
            timeout=fhir.timeout,
            max_retries=fhir.max_retries,
            api_key=fhir.api_key,
        )

        logger.info(
            "FHIR Sync consumer started, subscribed to %s", kafka.topics
        )

    async def close(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()

    async def is_connected(self) -> bool:
        """Check whether the consumer has active Kafka connections."""
        if not self._consumer:
            return False
        try:
            partitions = self._consumer.assignment()
            return len(partitions) > 0
        except Exception:
            return False

    async def consume_loop(self) -> None:
        """Main consume loop — runs until stopped."""
        assert self._consumer is not None
        tenant = self._config.tenant_id

        async for msg in self._consumer:
            if not self._running:
                break

            raw_bytes: bytes | None = msg.value
            if raw_bytes is None:
                await self._consumer.commit()
                continue

            raw = deserialize_avro(
                raw_bytes,
                schema_registry_url=self._config.schema_registry.url,
            )
            if raw is None:
                await self._consumer.commit()
                continue

            inc("messages_consumed_total")
            logger.debug(
                "CDC event from %s partition=%d offset=%d",
                msg.topic, msg.partition, msg.offset,
            )

            try:
                await self._process_message(raw, tenant)
            except Exception:
                inc("processing_errors_total")
                logger.exception("Error processing CDC event for FHIR sync")
                await self._dlh.send(raw, "processing_error")

            await self._consumer.commit()

    async def _process_message(
        self, raw: dict[str, Any], tenant: str
    ) -> None:
        event = _parse_event(raw)
        if event is None:
            return

        # Normalize operation type string (both formats use single-char codes)
        op_value = event.operation.value if hasattr(event.operation, "value") else str(event.operation)

        # Skip delete events for now (soft-delete not yet implemented)
        if op_value == "d":
            inc("fhir_deletes_total")
            logger.debug("Skipping delete event for %s", event.table_name)
            return

        routes = self._router.resolve(
            event.table_name, op_value
        )
        if routes is None:
            inc("events_skipped_no_route")
            return

        # Ensure all epoch millis in record_data are converted to ISO dates
        record_data = _convert_datetimes(event.record_data)
        assert self._fhir_client is not None

        fhir_resources: list[tuple[Any, dict[str, Any], str]] = []

        for route in routes:
            try:
                adapter = route.adapter_class(
                    fhir_client=self._fhir_client, tenant_id=tenant,
                )
                mapped_data = apply_column_map(record_data, route.column_map)
                fhir_resource = await adapter.adapt(mapped_data)
                # identifier_field may reference the adapter field name (mapped)
                identifier_value = str(
                    mapped_data.get(route.identifier_field, "")
                    or record_data.get(route.identifier_field, "")
                )
                fhir_resources.append(
                    (route, fhir_resource, identifier_value)
                )
            except Exception:
                inc("adapter_errors_total")
                logger.exception(
                    "Adapter %s failed for table %s",
                    route.adapter_class.__name__, event.table_name,
                )
                raise

        # Write: bundle if needed, otherwise individual conditional upserts
        if any(r.use_bundle for r, _, _ in fhir_resources):
            entries = []
            for route, resource, id_val in fhir_resources:
                entries.append({
                    "resource": resource,
                    "request": {
                        "method": "PUT",
                        "url": (
                            f"{route.fhir_resource_type}"
                            f"?identifier={route.identifier_system}|{id_val}"
                        ),
                    },
                })
            await self._writer.execute_bundle(entries)
            inc("fhir_bundles_total")
            logger.info(
                "Bundle executed: %d entries for %s",
                len(entries), event.table_name,
            )
        else:
            for route, resource, id_val in fhir_resources:
                await self._writer.conditional_update(
                    route.fhir_resource_type, resource,
                    route.identifier_system, id_val,
                )
            inc("fhir_upserts_total")
            logger.info(
                "Upserted %s from %s (id=%s)",
                routes[0].fhir_resource_type,
                event.table_name,
                fhir_resources[0][2] if fhir_resources else "?",
            )
