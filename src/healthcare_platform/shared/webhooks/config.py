"""Webhook configuration via Pydantic Settings (ADR-014).

Environment variable loading for all webhook receiver integrations.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class TasyWebhookSettings(BaseSettings):
    """TASY TIE callback authentication."""

    secret: str = Field(default="", alias="TASY_WEBHOOK_SECRET")
    signature_header: str = Field(
        default="X-Tasy-Signature", alias="TASY_WEBHOOK_SIGNATURE_HEADER"
    )

    model_config = {"env_prefix": "TASY_WEBHOOK_", "extra": "ignore"}


class PixWebhookSettings(BaseSettings):
    """Banco Central PIX notification settings."""

    certificate_path: str = Field(default="", alias="PIX_WEBHOOK_CERT_PATH")
    private_key_path: str = Field(default="", alias="PIX_WEBHOOK_KEY_PATH")
    mtls_enabled: bool = Field(default=True, alias="PIX_WEBHOOK_MTLS_ENABLED")

    model_config = {"env_prefix": "PIX_WEBHOOK_", "extra": "ignore"}


class WhatsAppWebhookSettings(BaseSettings):
    """Meta WhatsApp webhook settings."""

    secret: str = Field(default="", alias="WHATSAPP_WEBHOOK_SECRET")
    verify_token: str = Field(default="", alias="WHATSAPP_WEBHOOK_VERIFY_TOKEN")

    model_config = {"env_prefix": "WHATSAPP_WEBHOOK_", "extra": "ignore"}


class PayerWebhookSettings(BaseSettings):
    """ANS/TISS payer callback settings."""

    api_keys: dict[str, str] = Field(default_factory=dict, alias="PAYER_WEBHOOK_API_KEYS")

    model_config = {"env_prefix": "PAYER_WEBHOOK_", "extra": "ignore"}


class WebhookSettings(BaseSettings):
    """Root webhook configuration."""

    redis_url: str = Field(default="redis://localhost:6379/0", alias="WEBHOOK_REDIS_URL")
    cib7_engine_url: str = Field(
        default="http://localhost:8080", alias="CIB7_ENGINE_URL"
    )
    default_tenant_id: str = Field(default="hospital-a", alias="DEFAULT_TENANT_ID")
    idempotency_ttl_days: int = Field(default=7, alias="WEBHOOK_IDEMPOTENCY_TTL_DAYS")
    log_level: str = Field(default="INFO", alias="WEBHOOK_LOG_LEVEL")

    tasy: TasyWebhookSettings = Field(default_factory=TasyWebhookSettings)
    pix: PixWebhookSettings = Field(default_factory=PixWebhookSettings)
    whatsapp: WhatsAppWebhookSettings = Field(default_factory=WhatsAppWebhookSettings)
    payers: PayerWebhookSettings = Field(default_factory=PayerWebhookSettings)

    model_config = {"env_prefix": "WEBHOOK_", "extra": "ignore"}
