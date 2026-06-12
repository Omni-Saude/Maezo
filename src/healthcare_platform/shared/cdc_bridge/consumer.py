"""Kafka consumer for Debezium CDC events."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer

from healthcare_platform.shared.cdc_bridge.config import BridgeConfig
from healthcare_platform.shared.cdc_bridge.dead_letter import DeadLetterHandler
from healthcare_platform.shared.cdc_bridge.event_parser import (
    map_to_process_action,
    parse_cdc_event,
)
from healthcare_platform.shared.cdc_bridge.health import inc
from healthcare_platform.shared.cdc_bridge.process_starter import ProcessStarter

logger = logging.getLogger(__name__)


class EventConsumer:
    """Consumes CDC events from Kafka and dispatches BPM actions."""

    def __init__(
        self,
        config: BridgeConfig,
        process_starter: ProcessStarter,
        dead_letter: DeadLetterHandler,
    ) -> None:
        self._config = config
        self._starter = process_starter
        self._dlh = dead_letter
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

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
            value_deserializer=lambda v: json.loads(v) if v else None,
        )
        await self._consumer.start()
        self._running = True
        logger.info(
            "Kafka consumer started, subscribed to %s", kafka.topics
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
        tenant = self._config.cib7.tenant_id

        async for msg in self._consumer:
            if not self._running:
                break

            raw: dict[str, Any] | None = msg.value
            if raw is None:
                await self._consumer.commit()
                continue

            inc("messages_consumed_total")
            logger.debug(
                "CDC event from %s partition=%d offset=%d",
                msg.topic,
                msg.partition,
                msg.offset,
            )

            try:
                await self._process_message(raw, tenant)
            except Exception:
                inc("processing_errors_total")
                logger.exception("Error processing CDC event")
                await self._dlh.send(raw, "processing_error")

            await self._consumer.commit()

    async def _process_message(
        self, raw: dict[str, Any], tenant: str
    ) -> None:
        event = parse_cdc_event(raw)
        if event is None:
            return

        action = map_to_process_action(event, tenant_id=tenant)
        if action is None:
            return

        if action.action_type == "start":
            assert action.process_key is not None
            await self._starter.start_process(
                process_key=action.process_key,
                variables=action.variables,
                business_key=action.business_key,
                tenant_id=action.tenant_id,
            )
            inc("process_starts_total")
            logger.info(
                "Started process %s for business_key=%s",
                action.process_key,
                action.business_key,
            )
        elif action.action_type == "correlate":
            assert action.message_name is not None
            await self._starter.correlate_message(
                message_name=action.message_name,
                correlation_keys={"businessKey": action.business_key},
                variables=action.variables,
            )
            inc("message_correlations_total")
            logger.info(
                "Correlated message %s for business_key=%s",
                action.message_name,
                action.business_key,
            )
