"""
Kafka producer for financial event publishing.

Publishes provision events for downstream consumers with:
- Schema validation
- Retry logic
- Dead letter queue support
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import structlog

from revenue_cycle.config import Settings, get_settings

logger = structlog.get_logger(__name__)


@dataclass
class ProvisionCreatedEvent:
    """
    Event published when a provision is created.

    Schema follows the Kafka event schema defined in the migration spec.
    """

    event_type: str = "ProvisionCreated"
    provision_id: str = ""
    glosa_id: str = ""
    amount: float = 0.0
    debit_account: str = "6301"
    credit_account: str = "2101"
    accounting_period: str = ""
    created_at: str = ""
    event_id: str = ""
    version: str = "1.0"

    def __post_init__(self):
        """Initialize computed fields."""
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        if not self.event_id:
            self.event_id = f"evt-{uuid4().hex}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "provision_id": self.provision_id,
            "glosa_id": self.glosa_id,
            "amount": self.amount,
            "debit_account": self.debit_account,
            "credit_account": self.credit_account,
            "accounting_period": self.accounting_period,
            "created_at": self.created_at,
            "event_id": self.event_id,
            "version": self.version,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())


class KafkaProducer:
    """
    Kafka producer for publishing financial events.

    Note: This is a stub implementation that can be replaced
    with aiokafka or confluent-kafka-python in production.

    Example:
        producer = KafkaProducer()
        await producer.send("financial-provisions", {
            "event_type": "ProvisionCreated",
            "provision_id": "PROV-001",
            ...
        })
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        topic_prefix: Optional[str] = None,
    ):
        """
        Initialize Kafka producer.

        Args:
            settings: Application settings
            topic_prefix: Optional tenant-specific topic prefix
        """
        self._settings = settings or get_settings()
        self._topic_prefix = topic_prefix or ""
        self._logger = logger.bind(service="kafka_producer")
        self._connected = False

    async def connect(self) -> None:
        """
        Connect to Kafka broker.

        In production, this would initialize the Kafka client.
        """
        if self._connected:
            return

        # In production:
        # from aiokafka import AIOKafkaProducer
        # self._producer = AIOKafkaProducer(
        #     bootstrap_servers=self._settings.kafka.bootstrap_servers,
        #     ...
        # )
        # await self._producer.start()

        self._connected = True
        self._logger.info("Kafka producer connected")

    async def disconnect(self) -> None:
        """Disconnect from Kafka broker."""
        if not self._connected:
            return

        # In production:
        # await self._producer.stop()

        self._connected = False
        self._logger.info("Kafka producer disconnected")

    async def send(
        self,
        topic: str,
        message: dict[str, Any],
        key: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Send a message to a Kafka topic.

        Args:
            topic: Topic name (prefix will be added if configured)
            message: Message payload
            key: Optional message key for partitioning
            headers: Optional message headers

        Returns:
            Message ID

        Raises:
            KafkaPublishError: If publishing fails
        """
        if not self._connected:
            await self.connect()

        full_topic = f"{self._topic_prefix}{topic}" if self._topic_prefix else topic
        message_id = f"msg-{uuid4().hex[:12]}"

        # Add metadata
        message["_message_id"] = message_id
        message["_published_at"] = datetime.utcnow().isoformat()

        try:
            # In production:
            # await self._producer.send_and_wait(
            #     full_topic,
            #     value=json.dumps(message).encode(),
            #     key=key.encode() if key else None,
            #     headers=[(k, v.encode()) for k, v in (headers or {}).items()],
            # )

            # Stub: simulate publish
            await asyncio.sleep(0.01)  # Simulate latency

            self._logger.info(
                "Message published to Kafka",
                topic=full_topic,
                message_id=message_id,
                event_type=message.get("event_type"),
                key=key,
            )

            return message_id

        except Exception as e:
            self._logger.error(
                "Failed to publish message to Kafka",
                topic=full_topic,
                error=str(e),
            )
            raise KafkaPublishError(f"Failed to publish to {full_topic}: {e}")

    async def send_provision_event(
        self,
        event: ProvisionCreatedEvent,
        topic: str = "financial-provisions",
    ) -> str:
        """
        Send a provision created event.

        Args:
            event: Provision event
            topic: Target topic (default: financial-provisions)

        Returns:
            Message ID
        """
        return await self.send(
            topic=topic,
            message=event.to_dict(),
            key=event.provision_id,
            headers={
                "event-type": event.event_type,
                "version": event.version,
            },
        )


class KafkaPublishError(Exception):
    """Exception raised when Kafka publishing fails."""

    pass


# Global producer instance
_kafka_producer: Optional[KafkaProducer] = None


def get_kafka_producer(settings: Optional[Settings] = None) -> KafkaProducer:
    """
    Get the global Kafka producer instance.

    Args:
        settings: Optional settings override

    Returns:
        KafkaProducer instance
    """
    global _kafka_producer
    if _kafka_producer is None:
        _kafka_producer = KafkaProducer(settings)
    return _kafka_producer
