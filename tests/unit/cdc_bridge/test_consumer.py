"""Integration tests for CDC Bridge consumer with mock Kafka."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from healthcare_platform.shared.cdc_bridge.config import BridgeConfig
from healthcare_platform.shared.cdc_bridge.consumer import EventConsumer
from healthcare_platform.shared.cdc_bridge.dead_letter import DeadLetterHandler
from healthcare_platform.shared.cdc_bridge.process_starter import ProcessStarter


@pytest.fixture
def bridge_config() -> BridgeConfig:
    return BridgeConfig()


@pytest.fixture
def mock_process_starter() -> ProcessStarter:
    starter = MagicMock(spec=ProcessStarter)
    starter.start_process = AsyncMock(return_value={"id": "test-instance"})
    starter.correlate_message = AsyncMock(return_value={"resultType": "ProcessDefinition"})
    return starter


@pytest.fixture
def mock_dead_letter() -> DeadLetterHandler:
    dlh = MagicMock(spec=DeadLetterHandler)
    dlh.send = AsyncMock()
    return dlh


@pytest.fixture
def consumer(
    bridge_config: BridgeConfig,
    mock_process_starter: ProcessStarter,
    mock_dead_letter: DeadLetterHandler,
) -> EventConsumer:
    return EventConsumer(bridge_config, mock_process_starter, mock_dead_letter)


class TestEventConsumer:
    """Test Kafka consumer integration with CDC event processing."""

    @pytest.mark.asyncio
    async def test_consumer_start_creates_kafka_consumer(
        self, consumer: EventConsumer
    ) -> None:
        with patch("healthcare_platform.shared.cdc_bridge.consumer.AIOKafkaConsumer") as MockConsumer:
            mock_instance = AsyncMock()
            MockConsumer.return_value = mock_instance
            await consumer.start()
            assert consumer._consumer is not None
            mock_instance.start.assert_called_once()
            assert consumer._running is True

    @pytest.mark.asyncio
    async def test_consumer_close_stops_kafka_consumer(
        self, consumer: EventConsumer
    ) -> None:
        mock_kafka = AsyncMock()
        consumer._consumer = mock_kafka
        consumer._running = True
        await consumer.close()
        assert consumer._running is False
        mock_kafka.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_connected_returns_true_when_partitions_assigned(
        self, consumer: EventConsumer
    ) -> None:
        mock_kafka = MagicMock()
        mock_kafka.assignment.return_value = ["partition1", "partition2"]
        consumer._consumer = mock_kafka
        result = await consumer.is_connected()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_connected_returns_false_without_consumer(
        self, consumer: EventConsumer
    ) -> None:
        result = await consumer.is_connected()
        assert result is False

    @pytest.mark.asyncio
    async def test_process_atendimento_create_starts_process(
        self,
        consumer: EventConsumer,
        mock_process_starter: ProcessStarter,
    ) -> None:
        raw_event = {
            "op": "c",
            "source": {"table": "ATENDIMENTO", "ts_ms": 1707696000000, "db": "AUSTA"},
            "after": {"nr_atendimento": "ATD-001", "cd_paciente": "PAC001"},
        }
        await consumer._process_message(raw_event, "austa")
        mock_process_starter.start_process.assert_called_once()
        call_kwargs = mock_process_starter.start_process.call_args[1]
        assert call_kwargs["process_key"] == "encounter-registration"
        assert call_kwargs["business_key"] == "ATD-001"
        assert call_kwargs["tenant_id"] == "austa"
        assert "cd_paciente" in call_kwargs["variables"]

    @pytest.mark.asyncio
    async def test_process_item_conta_create_correlates_message(
        self,
        consumer: EventConsumer,
        mock_process_starter: ProcessStarter,
    ) -> None:
        raw_event = {
            "op": "c",
            "source": {"table": "ITEM_CONTA", "ts_ms": 1707696001000, "db": "AUSTA"},
            "after": {"nr_conta": "C-001", "cd_item": "ITEM123"},
        }
        await consumer._process_message(raw_event, "austa")
        mock_process_starter.correlate_message.assert_called_once()
        call_kwargs = mock_process_starter.correlate_message.call_args[1]
        assert call_kwargs["message_name"] == "MSG_CHARGE_CAPTURED"
        assert call_kwargs["correlation_keys"]["businessKey"] == "C-001"

    @pytest.mark.asyncio
    async def test_process_unmapped_event_does_nothing(
        self,
        consumer: EventConsumer,
        mock_process_starter: ProcessStarter,
    ) -> None:
        raw_event = {
            "op": "c",
            "source": {"table": "UNKNOWN_TABLE", "ts_ms": 0, "db": ""},
            "after": {"id": "123"},
        }
        await consumer._process_message(raw_event, "austa")
        mock_process_starter.start_process.assert_not_called()
        mock_process_starter.correlate_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_invalid_event_skips_silently(
        self,
        consumer: EventConsumer,
        mock_process_starter: ProcessStarter,
    ) -> None:
        raw_event = {"op": "invalid", "source": {}}
        await consumer._process_message(raw_event, "austa")
        mock_process_starter.start_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_consume_loop_processes_messages(
        self,
        consumer: EventConsumer,
        mock_process_starter: ProcessStarter,
    ) -> None:
        mock_msg1 = MagicMock()
        mock_msg1.topic = "tasy.AUSTA.ATENDIMENTO"
        mock_msg1.partition = 0
        mock_msg1.offset = 10
        mock_msg1.value = {
            "op": "c",
            "source": {"table": "ATENDIMENTO", "ts_ms": 0, "db": ""},
            "after": {"nr_atendimento": "ATD-100"},
        }

        mock_msg2 = MagicMock()
        mock_msg2.value = None  # Skip message

        mock_kafka = MagicMock()
        mock_kafka.commit = AsyncMock()
        
        # Create proper async iterator
        messages = [mock_msg1, mock_msg2]
        message_iter = iter(messages)
        
        async def async_iter():
            for msg in messages:
                yield msg
            consumer._running = False
        
        mock_kafka.__aiter__ = lambda self: async_iter()
        consumer._consumer = mock_kafka
        consumer._running = True

        await consumer.consume_loop()

        assert mock_kafka.commit.call_count == 2
        mock_process_starter.start_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_consume_loop_sends_errors_to_dead_letter(
        self,
        consumer: EventConsumer,
        mock_process_starter: ProcessStarter,
        mock_dead_letter: DeadLetterHandler,
    ) -> None:
        mock_msg = MagicMock()
        mock_msg.topic = "test.topic"
        mock_msg.partition = 0
        mock_msg.offset = 1
        # Create a valid event that will map to an action
        mock_msg.value = {
            "op": "c",
            "source": {"table": "ATENDIMENTO", "ts_ms": 0, "db": "AUSTA"},
            "after": {"nr_atendimento": "ATD-ERROR"},
        }

        # Reconfigure start_process to raise exception
        mock_process_starter.start_process = AsyncMock(side_effect=Exception("Test error"))

        mock_kafka = MagicMock()
        mock_kafka.commit = AsyncMock()
        
        # Create proper async iterator
        async def async_iter():
            yield mock_msg
            consumer._running = False
        
        mock_kafka.__aiter__ = lambda self: async_iter()
        consumer._consumer = mock_kafka
        consumer._running = True

        await consumer.consume_loop()

        # Verify dead letter was called with the event
        mock_dead_letter.send.assert_called_once()
        call_args = mock_dead_letter.send.call_args[0]
        assert call_args[0] == mock_msg.value
        assert call_args[1] == "processing_error"


class TestConsumerConfiguration:
    """Test consumer configuration from BridgeConfig."""

    @pytest.mark.asyncio
    async def test_consumer_uses_config_topics(
        self, bridge_config: BridgeConfig, mock_process_starter: ProcessStarter, mock_dead_letter: DeadLetterHandler
    ) -> None:
        bridge_config.kafka.topics = ["custom.topic1", "custom.topic2"]
        consumer = EventConsumer(bridge_config, mock_process_starter, mock_dead_letter)

        with patch("healthcare_platform.shared.cdc_bridge.consumer.AIOKafkaConsumer") as MockConsumer:
            mock_instance = AsyncMock()
            MockConsumer.return_value = mock_instance
            await consumer.start()
            MockConsumer.assert_called_once()
            call_args = MockConsumer.call_args[0]
            assert "custom.topic1" in call_args
            assert "custom.topic2" in call_args

    @pytest.mark.asyncio
    async def test_consumer_uses_config_kafka_settings(
        self, bridge_config: BridgeConfig, mock_process_starter: ProcessStarter, mock_dead_letter: DeadLetterHandler
    ) -> None:
        bridge_config.kafka.bootstrap_servers = "kafka1:9092,kafka2:9092"
        bridge_config.kafka.consumer_group = "test-group"
        consumer = EventConsumer(bridge_config, mock_process_starter, mock_dead_letter)

        with patch("healthcare_platform.shared.cdc_bridge.consumer.AIOKafkaConsumer") as MockConsumer:
            mock_instance = AsyncMock()
            MockConsumer.return_value = mock_instance
            await consumer.start()
            call_kwargs = MockConsumer.call_args[1]
            assert call_kwargs["bootstrap_servers"] == "kafka1:9092,kafka2:9092"
            assert call_kwargs["group_id"] == "test-group"
