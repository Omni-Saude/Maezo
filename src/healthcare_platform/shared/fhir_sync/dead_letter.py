"""Dead-letter handler for failed FHIR sync events."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from aiokafka import AIOKafkaProducer

from healthcare_platform.shared.fhir_sync.config import DeadLetterSettings, KafkaSettings

logger = logging.getLogger(__name__)


class DeadLetterHandler:
    """Publishes failed events to the dead-letter topic for later inspection."""

    def __init__(
        self, kafka: KafkaSettings, dlq: DeadLetterSettings
    ) -> None:
        self._kafka = kafka
        self._dlq = dlq
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._kafka.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()

    async def close(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def send(
        self,
        original_event: dict[str, Any],
        error_message: str,
        retry_count: int = 0,
    ) -> None:
        """Publish a failed event to the dead-letter topic."""
        if not self._producer:
            logger.error("Dead-letter producer not started")
            return

        envelope = {
            "original_event": original_event,
            "error_message": error_message,
            "retry_count": retry_count,
            "timestamp": time.time(),
        }
        try:
            await self._producer.send_and_wait(self._dlq.topic, envelope)
            logger.info("Sent event to dead-letter topic: %s", error_message)
        except Exception:
            logger.exception("Failed to publish to dead-letter topic")
