"""Configuration for CDC-to-BPM Bridge via Pydantic Settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class KafkaSettings(BaseSettings):
    """Kafka consumer configuration."""

    model_config = {"env_prefix": "KAFKA_"}

    bootstrap_servers: str = "kafka:9092"
    consumer_group: str = "cdc-to-bpm-bridge"
    topics: list[str] = Field(default_factory=lambda: [
        "tasy.TASY.ATENDIMENTO_PACIENTE",
        "tasy.TASY.CONTA_PACIENTE",
        "tasy.TASY.PROCEDIMENTO_PACIENTE",
    ])
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False
    max_poll_interval_ms: int = 300_000
    session_timeout_ms: int = 30_000


class CIB7Settings(BaseSettings):
    """CIB Seven engine connection settings (Basic Auth — ADR-020)."""

    model_config = {"env_prefix": "CIB7_"}

    engine_url: str = "http://cib7-engine:8080"
    tenant_id: str = "austa"
    user: str = "admin"
    password: str = ""


class DeadLetterSettings(BaseSettings):
    """Dead-letter topic configuration."""

    model_config = {"env_prefix": "DLQ_"}

    topic: str = "bridge.dead-letter"


class BridgeConfig(BaseSettings):
    """Aggregate configuration loaded from environment variables."""

    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    cib7: CIB7Settings = Field(default_factory=CIB7Settings)
    dead_letter: DeadLetterSettings = Field(default_factory=DeadLetterSettings)
    health_port: int = 8091
    log_level: str = "INFO"


def load_config() -> BridgeConfig:
    """Load configuration from environment variables."""
    return BridgeConfig()
