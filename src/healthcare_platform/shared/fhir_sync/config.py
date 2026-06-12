"""Configuration for FHIR Sync Service via Pydantic Settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class KafkaSettings(BaseSettings):
    """Kafka consumer configuration for FHIR sync."""

    model_config = {"env_prefix": "KAFKA_"}

    bootstrap_servers: str = "kafka:9092"
    consumer_group: str = "fhir-sync"
    topics: list[str] = Field(default_factory=lambda: [
        # tasy-oracle-connector topics (JSON via Avro worker override)
        "tasy.TASY.CONVENIO",
        "tasy.TASY.PACIENTE",
        "tasy.TASY.PESSOA_FISICA",
        "tasy.TASY.CONVENIO_PACIENTE",
        "tasy.TASY.ATENDIMENTO_PACIENTE",
        "tasy.TASY.PROCEDIMENTO_PACIENTE",
        "tasy.TASY.AUTORIZACAO_CONVENIO",
        "tasy.TASY.AUTORIZACAO_PROCEDIMENTO",
        "tasy.TASY.ATEND_CATEGORIA_CONVENIO",
        # SP-RC-002 new tables
        "tasy.TASY.MEDICO",
        "tasy.TASY.DIAGNOSTICO_DOENCA",
        "tasy.TASY.PROCEDIMENTO_AUTORIZADO",
        "tasy.TASY.CONVENIO_ESTABELECIMENTO",
        "tasy.TASY.PLANO_CONVENIO",
        # austa-operadora-connector topics (Avro)
        "austa.TASY.CONVENIO",
        "austa.TASY.PESSOA_FISICA",
        "austa.TASY.CONVENIO_PACIENTE",
        "austa.TASY.AUTORIZACAO_CONVENIO",
        "austa.TASY.AUTORIZACAO_PROCEDIMENTO",
        "austa.TASY.PACIENTE",
    ])
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False
    max_poll_interval_ms: int = 300_000
    session_timeout_ms: int = 30_000


class FHIRSettings(BaseSettings):
    """HAPI FHIR server connection settings."""

    model_config = {"env_prefix": "FHIR_"}

    base_url: str = "http://hapi_fhir:8080/fhir"
    timeout: float = 30.0
    max_retries: int = 3
    api_key: str | None = None


class SchemaRegistrySettings(BaseSettings):
    """Confluent Schema Registry connection settings."""

    model_config = {"env_prefix": "SCHEMA_REGISTRY_"}

    url: str = "http://schema_registry:8081"


class DeadLetterSettings(BaseSettings):
    """Dead-letter topic configuration."""

    model_config = {"env_prefix": "DLQ_"}

    topic: str = "fhir-sync.dead-letter"


class FHIRSyncConfig(BaseSettings):
    """Aggregate configuration loaded from environment variables."""

    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    fhir: FHIRSettings = Field(default_factory=FHIRSettings)
    schema_registry: SchemaRegistrySettings = Field(default_factory=SchemaRegistrySettings)
    dead_letter: DeadLetterSettings = Field(default_factory=DeadLetterSettings)
    tenant_id: str = "austa"
    health_port: int = 8092
    log_level: str = "INFO"


def load_config() -> FHIRSyncConfig:
    """Load configuration from environment variables."""
    return FHIRSyncConfig()
