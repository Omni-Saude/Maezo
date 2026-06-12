"""FHIR Sync Service — main entry point.

Consumes Debezium CDC events from Tasy ERP Kafka topics, transforms them
via Tasy-to-FHIR adapters, and persists FHIR R4 resources to HAPI FHIR
using conditional upsert (ADR-004, ADR-005).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import structlog

from healthcare_platform.shared.fhir_sync.config import load_config
from healthcare_platform.shared.fhir_sync.consumer import FHIRSyncConsumer
from healthcare_platform.shared.fhir_sync.dead_letter import DeadLetterHandler
from healthcare_platform.shared.fhir_sync.fhir_writer import FHIRWriter
from healthcare_platform.shared.fhir_sync.health import HealthServer
from healthcare_platform.shared.fhir_sync.router import TableAdapterRouter


def _setup_logging(level: str) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


class FHIRSyncApp:
    """Orchestrates consumer, FHIR writer, dead-letter, and health."""

    def __init__(self) -> None:
        self._config = load_config()
        self._writer = FHIRWriter(self._config.fhir)
        self._router = TableAdapterRouter()
        self._dlh = DeadLetterHandler(
            self._config.kafka, self._config.dead_letter
        )
        self._consumer = FHIRSyncConsumer(
            self._config, self._router, self._writer, self._dlh
        )
        self._health = HealthServer(
            self._config.health_port, self._consumer.is_connected
        )
        self._shutdown_event = asyncio.Event()

    async def run(self) -> None:
        _setup_logging(self._config.log_level)
        log = structlog.get_logger()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown_event.set)

        log.info("fhir_sync.starting")

        await self._writer.start()
        await self._dlh.start()
        await self._consumer.start()
        await self._health.start()

        log.info("fhir_sync.running")

        consume_task = asyncio.create_task(self._consumer.consume_loop())
        shutdown_task = asyncio.create_task(self._shutdown_event.wait())

        done, _ = await asyncio.wait(
            {consume_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED
        )

        log.info("fhir_sync.shutting_down")
        await self._consumer.close()
        await self._dlh.close()
        await self._writer.close()
        await self._health.close()
        log.info("fhir_sync.stopped")


def main() -> None:
    app = FHIRSyncApp()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
