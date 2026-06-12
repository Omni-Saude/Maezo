"""CDC-to-BPM Bridge — main entry point.

Consumes Debezium CDC events from Tasy ERP Kafka topics and starts/correlates
CIB Seven process instances (ADR-004, ADR-006).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import structlog

from healthcare_platform.shared.cdc_bridge.config import load_config
from healthcare_platform.shared.cdc_bridge.consumer import EventConsumer
from healthcare_platform.shared.cdc_bridge.dead_letter import DeadLetterHandler
from healthcare_platform.shared.cdc_bridge.health import HealthServer
from healthcare_platform.shared.cdc_bridge.process_starter import ProcessStarter


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


class CDCBridgeApp:
    """Orchestrates consumer, process starter, dead-letter, and health."""

    def __init__(self) -> None:
        self._config = load_config()
        self._starter = ProcessStarter(self._config.cib7)
        self._dlh = DeadLetterHandler(
            self._config.kafka, self._config.dead_letter
        )
        self._consumer = EventConsumer(
            self._config, self._starter, self._dlh
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

        log.info("cdc_bridge.starting")

        await self._starter.start()
        await self._dlh.start()
        await self._consumer.start()
        await self._health.start()

        log.info("cdc_bridge.running")

        consume_task = asyncio.create_task(self._consumer.consume_loop())
        shutdown_task = asyncio.create_task(self._shutdown_event.wait())

        done, _ = await asyncio.wait(
            {consume_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED
        )

        log.info("cdc_bridge.shutting_down")
        await self._consumer.close()
        await self._dlh.close()
        await self._starter.close()
        await self._health.close()
        log.info("cdc_bridge.stopped")


def main() -> None:
    app = CDCBridgeApp()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
