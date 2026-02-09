"""
Application settings using Pydantic Settings.

Loads configuration from environment variables with validation.
Supports multiple environments (development, staging, production).
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CamundaSettings(BaseSettings):
    """Camunda 8 connection settings."""

    model_config = SettingsConfigDict(env_prefix="CAMUNDA_")

    # Zeebe Gateway
    gateway_address: str = Field(
        default="localhost:26500",
        description="Zeebe gateway address (host:port)",
    )

    # Authentication (Camunda Cloud or Self-Managed)
    client_id: Optional[str] = Field(
        default=None,
        description="OAuth client ID for Camunda Cloud",
    )
    client_secret: Optional[SecretStr] = Field(
        default=None,
        description="OAuth client secret for Camunda Cloud",
    )
    cluster_id: Optional[str] = Field(
        default=None,
        description="Camunda Cloud cluster ID",
    )
    region: str = Field(
        default="bru-2",
        description="Camunda Cloud region",
    )

    # Worker settings
    worker_name: str = Field(
        default="revenue-cycle-worker",
        description="Worker identifier for logging",
    )
    max_jobs: int = Field(
        default=32,
        ge=1,
        le=128,
        description="Maximum concurrent jobs",
    )
    request_timeout: int = Field(
        default=30000,
        ge=1000,
        description="Request timeout in milliseconds",
    )
    poll_interval: float = Field(
        default=0.3,
        ge=0.1,
        description="Poll interval in seconds",
    )

    @property
    def is_cloud(self) -> bool:
        """Check if using Camunda Cloud."""
        return self.client_id is not None and self.cluster_id is not None


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    # Connection
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, ge=1, le=65535, description="Database port")
    name: str = Field(default="revenue_cycle", description="Database name")
    user: str = Field(default="postgres", description="Database user")
    password: SecretStr = Field(default=SecretStr("postgres"), description="Database password")

    # Pool settings
    pool_size: int = Field(default=10, ge=1, le=100, description="Connection pool size")
    max_overflow: int = Field(default=20, ge=0, le=100, description="Max overflow connections")
    pool_timeout: int = Field(default=30, ge=1, description="Pool timeout in seconds")

    # SSL
    ssl_mode: str = Field(default="prefer", description="SSL mode (disable, prefer, require)")

    @property
    def url(self) -> str:
        """Get database URL for SQLAlchemy."""
        password = self.password.get_secret_value()
        return f"postgresql+asyncpg://{self.user}:{password}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_url(self) -> str:
        """Get synchronous database URL."""
        password = self.password.get_secret_value()
        return f"postgresql://{self.user}:{password}@{self.host}:{self.port}/{self.name}"


class VaultSettings(BaseSettings):
    """HashiCorp Vault settings for secrets management."""

    model_config = SettingsConfigDict(env_prefix="VAULT_")

    enabled: bool = Field(default=False, description="Enable Vault integration")
    url: str = Field(default="http://localhost:8200", description="Vault URL")
    token: Optional[SecretStr] = Field(default=None, description="Vault token")
    mount_point: str = Field(default="secret", description="KV secrets engine mount point")
    path_prefix: str = Field(default="revenue-cycle", description="Secret path prefix")

    # Authentication methods
    auth_method: Literal["token", "kubernetes", "approle"] = Field(
        default="token",
        description="Vault authentication method",
    )
    role_id: Optional[str] = Field(default=None, description="AppRole role ID")
    secret_id: Optional[SecretStr] = Field(default=None, description="AppRole secret ID")


class ObservabilitySettings(BaseSettings):
    """Observability settings (logging, metrics, tracing)."""

    model_config = SettingsConfigDict(env_prefix="OBSERVABILITY_")

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    log_format: Literal["json", "console"] = Field(
        default="json",
        description="Log output format",
    )

    # OpenTelemetry
    otlp_enabled: bool = Field(default=False, description="Enable OTLP export")
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP collector endpoint",
    )
    service_name: str = Field(
        default="revenue-cycle-workers",
        description="Service name for tracing",
    )

    # Prometheus
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, ge=1, le=65535, description="Metrics server port")


class IntegrationSettings(BaseSettings):
    """External integration settings."""

    model_config = SettingsConfigDict(env_prefix="INTEGRATION_")

    # TASY ERP
    tasy_base_url: str = Field(
        default="http://localhost:8080/api",
        description="TASY ERP base URL",
    )
    tasy_timeout: int = Field(default=30, ge=1, description="TASY request timeout in seconds")

    # TISS
    tiss_base_url: str = Field(
        default="http://localhost:8081/api",
        description="TISS service base URL",
    )
    tiss_timeout: int = Field(default=60, ge=1, description="TISS request timeout in seconds")

    # LIS (Laboratory Information System)
    lis_base_url: str = Field(
        default="http://localhost:8082/api",
        description="LIS base URL",
    )

    # PACS (Picture Archiving and Communication System)
    pacs_base_url: str = Field(
        default="http://localhost:8083/api",
        description="PACS base URL",
    )

    # WhatsApp Business API
    whatsapp_api_url: str = Field(
        default="https://graph.facebook.com/v18.0",
        description="WhatsApp Business API URL",
    )
    whatsapp_phone_number_id: Optional[str] = Field(
        default=None,
        description="WhatsApp phone number ID",
    )


class Settings(BaseSettings):
    """
    Main application settings.

    Aggregates all sub-settings and provides environment-based configuration.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Application environment",
    )
    debug: bool = Field(default=False, description="Enable debug mode")

    # Sub-settings
    camunda: CamundaSettings = Field(default_factory=CamundaSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    vault: VaultSettings = Field(default_factory=VaultSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    integration: IntegrationSettings = Field(default_factory=IntegrationSettings)

    # Worker defaults
    default_retries: int = Field(default=3, ge=0, le=10, description="Default retry count")
    retry_backoff_base: float = Field(default=2.0, ge=1.0, description="Exponential backoff base")

    # Audit streaming settings
    audit_batch_size: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Batch size for streaming audit analysis",
    )
    audit_memory_threshold_mb: int = Field(
        default=512,
        ge=128,
        le=2048,
        description="Memory threshold in MB for triggering GC",
    )
    audit_timeout_seconds: int = Field(
        default=300,
        ge=60,
        le=600,
        description="Timeout for audit operations in seconds",
    )

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Normalize environment name."""
        return v.lower().strip()

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Returns:
        Settings instance (cached)
    """
    return Settings()
