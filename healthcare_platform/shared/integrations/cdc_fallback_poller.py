"""CDC Fallback Poller (ADR-004).

Provides polling-based change detection when Debezium CDC is unavailable.
Queries Tasy tables periodically via TasyApiClient and produces synthetic CDC events.

This module:
- Polls Tasy tables on configurable intervals
- Tracks last_processed_timestamp per table per tenant
- Detects deltas via LAST_UPDATE_DATE comparison
- Produces TasyCDCEvent-compatible events
- Pushes to Kafka or configurable event sink
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

from aiokafka import AIOKafkaProducer
from prometheus_client import Counter, Gauge
from pydantic import BaseModel, ConfigDict

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_client import TasyCDCEvent
from healthcare_platform.shared.multi_tenant.context import get_current_tenant
from healthcare_platform.shared.observability.correlation import get_current_context
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------------

CDC_FALLBACK_POLLS_TOTAL = Counter(
    "cdc_fallback_polls_total",
    "Total polling attempts",
    labelnames=["table_name", "tenant_id", "status"],
)

CDC_FALLBACK_RECORDS_DETECTED = Counter(
    "cdc_fallback_records_detected",
    "Records detected with changes",
    labelnames=["table_name", "tenant_id"],
)

CDC_FALLBACK_LAG_SECONDS = Gauge(
    "cdc_fallback_lag_seconds",
    "Time since last successful poll",
    labelnames=["table_name"],
)

CDC_FALLBACK_ERRORS_TOTAL = Counter(
    "cdc_fallback_errors_total",
    "Total polling errors",
    labelnames=["table_name", "error_type"],
)


# ---------------------------------------------------------------------------
# Configuration Models
# ---------------------------------------------------------------------------


class PollingTableConfig(BaseModel):
    """Configuration for polling a single table."""

    model_config = ConfigDict(frozen=True)

    table_name: str
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    interval_seconds: int
    api_endpoint: str
    timestamp_field: str = "LAST_UPDATE_DATE"
    kafka_topic: str


# Default configurations per ADR-004
DEFAULT_TABLE_CONFIGS: list[PollingTableConfig] = [
    PollingTableConfig(
        table_name="ATENDIMENTO",
        priority="HIGH",
        interval_seconds=60,
        api_endpoint="/api/v1/encounters/changes",
        kafka_topic="tasy.AUSTA.ATENDIMENTO",
    ),
    PollingTableConfig(
        table_name="CONTA_MEDICA",
        priority="HIGH",
        interval_seconds=120,
        api_endpoint="/api/v1/billing/accounts/changes",
        kafka_topic="tasy.AUSTA.CONTA_MEDICA",
    ),
    PollingTableConfig(
        table_name="ITEM_CONTA",
        priority="MEDIUM",
        interval_seconds=300,
        api_endpoint="/api/v1/billing/items/changes",
        kafka_topic="tasy.AUSTA.ITEM_CONTA",
    ),
    PollingTableConfig(
        table_name="PRESCRICAO",
        priority="MEDIUM",
        interval_seconds=300,
        api_endpoint="/api/v1/prescriptions/changes",
        kafka_topic="tasy.AUSTA.PRESCRICAO",
    ),
    PollingTableConfig(
        table_name="SINAL_VITAL",
        priority="LOW",
        interval_seconds=300,
        api_endpoint="/api/v1/vitals/changes",
        kafka_topic="tasy.AUSTA.SINAL_VITAL",
    ),
]


class PollingState(BaseModel):
    """State tracking for a polled table."""

    table_name: str
    tenant_id: str
    last_processed_timestamp: datetime
    last_poll_at: datetime
    records_processed: int = 0
    consecutive_errors: int = 0


# ---------------------------------------------------------------------------
# Event Sink Protocol
# ---------------------------------------------------------------------------


class EventSinkProtocol(Protocol):
    """Protocol for publishing CDC events."""

    async def publish(self, topic: str, event: TasyCDCEvent) -> None:
        """Publish a CDC event to the given topic."""
        ...


# ---------------------------------------------------------------------------
# Kafka Event Sink
# ---------------------------------------------------------------------------


class KafkaEventSink:
    """Kafka-based event sink for CDC events."""

    def __init__(
        self,
        bootstrap_servers: str | list[str] = "localhost:9092",
        **producer_kwargs: Any,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer_kwargs = producer_kwargs
        self._producer: AIOKafkaProducer | None = None
        self._logger = get_logger(__name__)

    async def start(self) -> None:
        """Initialize Kafka producer."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            **self._producer_kwargs,
        )
        await self._producer.start()
        self._logger.info("kafka_sink_started", bootstrap_servers=self._bootstrap_servers)

    async def stop(self) -> None:
        """Stop Kafka producer."""
        if self._producer:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, event: TasyCDCEvent) -> None:
        """Publish CDC event to Kafka."""
        if not self._producer:
            raise RuntimeError(_("Produtor Kafka não inicializado"))

        ctx = get_current_context()
        headers = [
            ("correlation_id", ctx.correlation_id.encode("utf-8") if ctx.correlation_id else b""),
            ("tenant_id", event.tenant_id.encode("utf-8")),
        ]

        payload = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "table_name": event.table_name,
            "timestamp": event.timestamp.isoformat(),
            "payload": event.payload,
            "tenant_id": event.tenant_id,
        }

        await self._producer.send(topic, value=payload, headers=headers)
        self._logger.debug(
            "event_published",
            topic=topic,
            event_id=event.event_id,
            table=event.table_name,
        )


# ---------------------------------------------------------------------------
# In-Memory Event Sink (Testing)
# ---------------------------------------------------------------------------


class InMemoryEventSink:
    """In-memory event sink for testing."""

    def __init__(self) -> None:
        self.events: list[tuple[str, TasyCDCEvent]] = []

    async def publish(self, topic: str, event: TasyCDCEvent) -> None:
        """Store event in memory."""
        self.events.append((topic, event))

    def get_events(self, topic: str | None = None) -> list[TasyCDCEvent]:
        """Get all events, optionally filtered by topic."""
        if topic is None:
            return [e for _, e in self.events]
        return [e for t, e in self.events if t == topic]

    def clear(self) -> None:
        """Clear all stored events."""
        self.events.clear()


# ---------------------------------------------------------------------------
# CDC Fallback Poller
# ---------------------------------------------------------------------------


@dataclass
class CDCFallbackPoller:
    """Polling-based CDC fallback for Tasy integration.

    Queries Tasy tables periodically and produces synthetic CDC events
    compatible with TasyCDCEvent format. Gracefully handles per-table errors
    with exponential backoff.
    """

    tasy_api_client: Any  # TasyApiClient or compatible
    event_sink: EventSinkProtocol
    table_configs: list[PollingTableConfig] = field(default_factory=lambda: DEFAULT_TABLE_CONFIGS)

    _states: dict[str, PollingState] = field(default_factory=dict, init=False)
    _tasks: list[asyncio.Task[None]] = field(default_factory=list, init=False)
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _logger: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._logger = get_logger("cdc_fallback_poller")

    async def start(self) -> None:
        """Start polling tasks for all configured tables."""
        tenant = get_current_tenant()
        if tenant is None:
            raise ExternalServiceException(
                _("Contexto de tenant obrigatório para CDC fallback"),
                service_name="cdc_fallback_poller",
                operation="start",
            )

        self._shutdown_event.clear()

        # Initialize state for each table
        now = datetime.utcnow()
        for config in self.table_configs:
            state_key = f"{tenant.tenant_id}:{config.table_name}"
            if state_key not in self._states:
                self._states[state_key] = PollingState(
                    table_name=config.table_name,
                    tenant_id=tenant.tenant_id,
                    last_processed_timestamp=now - timedelta(seconds=config.interval_seconds),
                    last_poll_at=now,
                )

        # Spawn polling tasks
        for config in self.table_configs:
            task = asyncio.create_task(self._poll_table_loop(config))
            self._tasks.append(task)

        self._logger.info(
            "cdc_fallback_started",
            tenant_id=tenant.tenant_id,
            tables=[c.table_name for c in self.table_configs],
        )

    async def stop(self) -> None:
        """Stop all polling tasks gracefully."""
        self._shutdown_event.set()

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for cancellation
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        self._logger.info("cdc_fallback_stopped")

    async def _poll_table_loop(self, config: PollingTableConfig) -> None:
        """Main polling loop for a single table."""
        while not self._shutdown_event.is_set():
            try:
                await self._poll_table(config)
                status = "success"
            except Exception as exc:
                status = "error"
                error_type = type(exc).__name__
                CDC_FALLBACK_ERRORS_TOTAL.labels(
                    table_name=config.table_name, error_type=error_type
                ).inc()
                self._logger.error(
                    "polling_error",
                    table=config.table_name,
                    error=str(exc),
                    error_type=error_type,
                )
                await self._handle_polling_error(config)
            finally:
                tenant = get_current_tenant()
                tenant_id = tenant.tenant_id if tenant else "unknown"
                CDC_FALLBACK_POLLS_TOTAL.labels(
                    table_name=config.table_name,
                    tenant_id=tenant_id,
                    status=status,
                ).inc()

            # Sleep until next poll (or shutdown)
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=config.interval_seconds,
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                continue  # Next poll cycle

    async def _poll_table(self, config: PollingTableConfig) -> None:
        """Poll a single table for changes."""
        tenant = get_current_tenant()
        if tenant is None:
            raise ExternalServiceException(
                _("Contexto de tenant perdido durante polling"),
                service_name="cdc_fallback_poller",
                operation="poll_table",
            )

        state_key = f"{tenant.tenant_id}:{config.table_name}"
        state = self._states[state_key]

        # Query API for changes since last poll
        try:
            response = await self.tasy_api_client._request(
                "GET",
                config.api_endpoint,
                params={
                    "since": state.last_processed_timestamp.isoformat(),
                    "timestamp_field": config.timestamp_field,
                },
            )
            data = response.json()
        except Exception as exc:
            raise ExternalServiceException(
                _("Falha ao consultar endpoint {}").format(config.api_endpoint),
                service_name="tasy_api",
                operation=config.api_endpoint,
            ) from exc

        records = data.get("records", [])
        if not records:
            self._logger.debug(
                "no_changes_detected",
                table=config.table_name,
                since=state.last_processed_timestamp.isoformat(),
            )
            self._update_poll_time(state_key)
            CDC_FALLBACK_LAG_SECONDS.labels(table_name=config.table_name).set(
                (datetime.utcnow() - state.last_poll_at).total_seconds()
            )
            return

        # Process and publish events
        max_timestamp = state.last_processed_timestamp
        for record in records:
            event = self._build_cdc_event(config.table_name, record, event_type="u")
            await self.event_sink.publish(config.kafka_topic, event)

            # Track latest timestamp
            record_ts = datetime.fromisoformat(record.get(config.timestamp_field))
            if record_ts > max_timestamp:
                max_timestamp = record_ts

            CDC_FALLBACK_RECORDS_DETECTED.labels(
                table_name=config.table_name, tenant_id=tenant.tenant_id
            ).inc()

        # Update state
        self._update_state(state_key, max_timestamp, len(records))

        self._logger.info(
            "polling_completed",
            table=config.table_name,
            records_processed=len(records),
            last_timestamp=max_timestamp.isoformat(),
        )

        CDC_FALLBACK_LAG_SECONDS.labels(table_name=config.table_name).set(0)

    def _build_cdc_event(
        self, table_name: str, record: dict[str, Any], event_type: str
    ) -> TasyCDCEvent:
        """Build synthetic CDC event from polled record."""
        tenant = get_current_tenant()
        if tenant is None:
            raise ExternalServiceException(
                _("Contexto de tenant perdido durante construção de evento"),
                service_name="cdc_fallback_poller",
                operation="build_cdc_event",
            )

        ctx = get_current_context()
        event_id = f"fallback-{table_name}-{record.get('id', 'unknown')}-{int(time.time() * 1000)}"

        return TasyCDCEvent(
            event_id=event_id,
            event_type=event_type,
            table_name=table_name,
            timestamp=datetime.utcnow(),
            payload=record,
            tenant_id=tenant.tenant_id,
        )

    def _update_state(self, state_key: str, timestamp: datetime, records_count: int) -> None:
        """Update polling state after successful poll."""
        state = self._states[state_key]
        self._states[state_key] = PollingState(
            table_name=state.table_name,
            tenant_id=state.tenant_id,
            last_processed_timestamp=timestamp,
            last_poll_at=datetime.utcnow(),
            records_processed=state.records_processed + records_count,
            consecutive_errors=0,  # Reset error count on success
        )

    def _update_poll_time(self, state_key: str) -> None:
        """Update only the last poll time (no new records)."""
        state = self._states[state_key]
        self._states[state_key] = PollingState(
            table_name=state.table_name,
            tenant_id=state.tenant_id,
            last_processed_timestamp=state.last_processed_timestamp,
            last_poll_at=datetime.utcnow(),
            records_processed=state.records_processed,
            consecutive_errors=0,
        )

    async def _handle_polling_error(self, config: PollingTableConfig) -> None:
        """Handle polling error with exponential backoff."""
        tenant = get_current_tenant()
        if tenant is None:
            return

        state_key = f"{tenant.tenant_id}:{config.table_name}"
        state = self._states[state_key]

        # Increment error count
        self._states[state_key] = PollingState(
            table_name=state.table_name,
            tenant_id=state.tenant_id,
            last_processed_timestamp=state.last_processed_timestamp,
            last_poll_at=datetime.utcnow(),
            records_processed=state.records_processed,
            consecutive_errors=state.consecutive_errors + 1,
        )

        # Exponential backoff (max 5 minutes)
        backoff_seconds = min(2 ** state.consecutive_errors, 300)
        self._logger.warning(
            "polling_backoff",
            table=config.table_name,
            consecutive_errors=state.consecutive_errors + 1,
            backoff_seconds=backoff_seconds,
        )

        try:
            await asyncio.wait_for(
                self._shutdown_event.wait(),
                timeout=backoff_seconds,
            )
        except asyncio.TimeoutError:
            pass  # Backoff complete

    def get_state(self) -> dict[str, PollingState]:
        """Get current polling state for all tables."""
        return dict(self._states)

    def health_check(self) -> dict[str, Any]:
        """Get health status with lag and error metrics."""
        now = datetime.utcnow()
        health: dict[str, Any] = {
            "status": "healthy",
            "tables": {},
        }

        for state_key, state in self._states.items():
            lag_seconds = (now - state.last_poll_at).total_seconds()
            table_health = {
                "lag_seconds": lag_seconds,
                "last_poll_at": state.last_poll_at.isoformat(),
                "records_processed": state.records_processed,
                "consecutive_errors": state.consecutive_errors,
            }

            # Mark unhealthy if lag > 10 minutes or errors > 5
            if lag_seconds > 600 or state.consecutive_errors > 5:
                health["status"] = "degraded"
                table_health["status"] = "unhealthy"
            else:
                table_health["status"] = "healthy"

            health["tables"][state_key] = table_health

        return health
