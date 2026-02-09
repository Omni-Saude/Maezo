"""
Multi-tenant credential management with HashiCorp Vault integration.

Provides secure credential storage, retrieval, and rotation for multi-tenant
SaaS deployments. Each tenant has isolated credentials for external systems.

Features:
- HashiCorp Vault integration for secure storage
- Per-tenant credential isolation
- TTL-based caching with automatic refresh
- Audit logging for all credential access
- Key rotation support
- Multiple authentication methods (token, AppRole, Kubernetes)

Security:
- Credentials never logged or exposed
- Automatic cache invalidation
- Audit trail for compliance
- Encryption at rest (Vault)
- TLS in transit
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import hvac  # HashiCorp Vault client
import structlog
from hvac.exceptions import Forbidden, InvalidPath, VaultError
from pydantic import BaseModel, Field, SecretStr

from revenue_cycle.config import Settings, get_settings
from revenue_cycle.multi_tenant.context import get_current_tenant_id

logger = structlog.get_logger(__name__)


class CredentialType(str, Enum):
    """Types of credentials managed by the system."""

    TASY_API = "tasy_api"
    TISS_CERTIFICATE = "tiss_certificate"
    WHATSAPP_TOKEN = "whatsapp_token"
    DATABASE = "database"
    INTEGRATION_API = "integration_api"


class TasyCredentials(BaseModel):
    """TASY ERP API credentials."""

    username: str = Field(description="TASY API username")
    password: SecretStr = Field(description="TASY API password")
    api_key: Optional[SecretStr] = Field(default=None, description="Optional API key")
    base_url: str = Field(description="TASY instance URL")

    class Config:
        """Pydantic config."""

        frozen = True  # Immutable for security


class TissCertificate(BaseModel):
    """TISS certificate for ANS submission."""

    certificate_pem: SecretStr = Field(description="PEM-encoded certificate")
    private_key_pem: SecretStr = Field(description="PEM-encoded private key")
    passphrase: Optional[SecretStr] = Field(default=None, description="Key passphrase")
    valid_until: datetime = Field(description="Certificate expiration date")
    issuer: str = Field(description="Certificate issuer")

    class Config:
        """Pydantic config."""

        frozen = True

    @property
    def is_expired(self) -> bool:
        """Check if certificate is expired."""
        return datetime.utcnow() > self.valid_until

    @property
    def days_until_expiration(self) -> int:
        """Get days until certificate expires."""
        delta = self.valid_until - datetime.utcnow()
        return max(0, delta.days)


class WhatsAppCredentials(BaseModel):
    """WhatsApp Business API credentials."""

    access_token: SecretStr = Field(description="WhatsApp Business access token")
    phone_number_id: str = Field(description="WhatsApp phone number ID")
    business_account_id: str = Field(description="WhatsApp Business Account ID")
    webhook_verify_token: Optional[SecretStr] = Field(
        default=None, description="Webhook verification token"
    )

    class Config:
        """Pydantic config."""

        frozen = True


@dataclass
class CachedCredential:
    """Cached credential with TTL."""

    credential: Any
    cached_at: datetime
    ttl_seconds: int
    access_count: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        age = datetime.utcnow() - self.cached_at
        return age.total_seconds() > self.ttl_seconds

    @property
    def remaining_ttl(self) -> int:
        """Get remaining TTL in seconds."""
        age = datetime.utcnow() - self.cached_at
        remaining = self.ttl_seconds - int(age.total_seconds())
        return max(0, remaining)


@dataclass
class CredentialAccessAudit:
    """Audit record for credential access."""

    tenant_id: str
    credential_type: CredentialType
    accessed_at: datetime = field(default_factory=datetime.utcnow)
    user_id: Optional[str] = None
    correlation_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class TenantCredentialManager:
    """
    Multi-tenant credential manager with Vault integration.

    Provides secure, isolated credential management for each tenant
    with caching, audit logging, and automatic rotation support.

    Example:
        manager = TenantCredentialManager(settings)
        await manager.initialize()

        # Get credentials for current tenant
        tasy_creds = await manager.get_tasy_credentials("tenant-123")
        tiss_cert = await manager.get_tiss_certificate("tenant-123")
        whatsapp_token = await manager.get_whatsapp_token("tenant-123")

        # Rotate credentials
        await manager.rotate_credentials("tenant-123", CredentialType.TASY_API)
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        cache_ttl_seconds: int = 300,
        audit_enabled: bool = True,
    ):
        """
        Initialize credential manager.

        Args:
            settings: Application settings
            cache_ttl_seconds: Default cache TTL (5 minutes)
            audit_enabled: Enable audit logging
        """
        self._settings = settings or get_settings()
        self._cache_ttl = cache_ttl_seconds
        self._audit_enabled = audit_enabled

        self._vault_client: Optional[hvac.Client] = None
        self._cache: dict[str, CachedCredential] = {}
        self._cache_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize Vault client and authenticate.

        Raises:
            VaultError: If Vault initialization fails
        """
        if self._initialized:
            logger.warning("Credential manager already initialized")
            return

        vault_settings = self._settings.vault

        if not vault_settings.enabled:
            logger.warning("Vault integration disabled, using fallback credential store")
            self._initialized = True
            return

        try:
            # Initialize Vault client
            self._vault_client = hvac.Client(
                url=vault_settings.url,
                verify=True,  # Always verify TLS in production
            )

            # Authenticate based on configured method
            await self._authenticate_vault()

            # Verify authentication
            if not self._vault_client.is_authenticated():
                raise VaultError("Vault authentication failed")

            self._initialized = True
            logger.info(
                "Credential manager initialized",
                vault_url=vault_settings.url,
                auth_method=vault_settings.auth_method,
            )

        except Exception as e:
            logger.error("Failed to initialize credential manager", error=str(e))
            raise

    async def _authenticate_vault(self) -> None:
        """Authenticate with Vault using configured method."""
        vault_settings = self._settings.vault

        if vault_settings.auth_method == "token":
            if not vault_settings.token:
                raise ValueError("Vault token not configured")
            self._vault_client.token = vault_settings.token.get_secret_value()

        elif vault_settings.auth_method == "approle":
            if not vault_settings.role_id or not vault_settings.secret_id:
                raise ValueError("AppRole credentials not configured")

            response = self._vault_client.auth.approle.login(
                role_id=vault_settings.role_id,
                secret_id=vault_settings.secret_id.get_secret_value(),
            )
            self._vault_client.token = response["auth"]["client_token"]

        elif vault_settings.auth_method == "kubernetes":
            # Read service account token
            with open("/var/run/secrets/kubernetes.io/serviceaccount/token") as f:
                jwt = f.read()

            response = self._vault_client.auth.kubernetes.login(
                role=vault_settings.role_id or "default",
                jwt=jwt,
            )
            self._vault_client.token = response["auth"]["client_token"]

        else:
            raise ValueError(f"Unsupported auth method: {vault_settings.auth_method}")

        logger.info("Vault authentication successful", method=vault_settings.auth_method)

    def _get_vault_path(self, tenant_id: str, credential_type: CredentialType) -> str:
        """
        Get Vault path for tenant credential.

        Args:
            tenant_id: Tenant identifier
            credential_type: Type of credential

        Returns:
            Vault secret path
        """
        vault_settings = self._settings.vault
        return (
            f"{vault_settings.mount_point}/data/"
            f"{vault_settings.path_prefix}/tenants/{tenant_id}/{credential_type.value}"
        )

    def _get_cache_key(self, tenant_id: str, credential_type: CredentialType) -> str:
        """Get cache key for credential."""
        return f"{tenant_id}:{credential_type.value}"

    async def _get_from_cache(
        self, tenant_id: str, credential_type: CredentialType
    ) -> Optional[Any]:
        """Get credential from cache if not expired."""
        cache_key = self._get_cache_key(tenant_id, credential_type)

        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and not cached.is_expired:
                cached.access_count += 1
                logger.debug(
                    "Credential cache hit",
                    tenant_id=tenant_id,
                    type=credential_type.value,
                    remaining_ttl=cached.remaining_ttl,
                )
                return cached.credential

        return None

    async def _set_cache(
        self, tenant_id: str, credential_type: CredentialType, credential: Any
    ) -> None:
        """Store credential in cache."""
        cache_key = self._get_cache_key(tenant_id, credential_type)

        async with self._cache_lock:
            self._cache[cache_key] = CachedCredential(
                credential=credential,
                cached_at=datetime.utcnow(),
                ttl_seconds=self._cache_ttl,
            )
            logger.debug(
                "Credential cached",
                tenant_id=tenant_id,
                type=credential_type.value,
                ttl=self._cache_ttl,
            )

    async def _invalidate_cache(
        self, tenant_id: str, credential_type: Optional[CredentialType] = None
    ) -> None:
        """
        Invalidate cached credentials.

        Args:
            tenant_id: Tenant identifier
            credential_type: Specific credential type, or None for all
        """
        async with self._cache_lock:
            if credential_type:
                cache_key = self._get_cache_key(tenant_id, credential_type)
                self._cache.pop(cache_key, None)
                logger.info(
                    "Cache invalidated",
                    tenant_id=tenant_id,
                    type=credential_type.value,
                )
            else:
                # Invalidate all credentials for tenant
                keys_to_remove = [
                    k for k in self._cache.keys() if k.startswith(f"{tenant_id}:")
                ]
                for key in keys_to_remove:
                    self._cache.pop(key)
                logger.info("All credentials invalidated", tenant_id=tenant_id)

    async def _audit_access(
        self,
        tenant_id: str,
        credential_type: CredentialType,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Log credential access for audit trail."""
        if not self._audit_enabled:
            return

        audit_record = CredentialAccessAudit(
            tenant_id=tenant_id,
            credential_type=credential_type,
            success=success,
            error_message=error,
        )

        # Log audit record (structured logging for SIEM ingestion)
        logger.info(
            "credential_access",
            tenant_id=audit_record.tenant_id,
            credential_type=audit_record.credential_type.value,
            accessed_at=audit_record.accessed_at.isoformat(),
            user_id=audit_record.user_id,
            correlation_id=audit_record.correlation_id,
            success=audit_record.success,
            error=audit_record.error_message,
            # Add security event markers
            event_type="credential_access",
            severity="INFO" if success else "WARNING",
        )

    async def get_tasy_credentials(self, tenant_id: str) -> TasyCredentials:
        """
        Get TASY ERP credentials for tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            TASY credentials

        Raises:
            VaultError: If credentials cannot be retrieved
        """
        # Check cache first
        cached = await self._get_from_cache(tenant_id, CredentialType.TASY_API)
        if cached:
            await self._audit_access(tenant_id, CredentialType.TASY_API, True)
            return cached

        try:
            # Retrieve from Vault
            if self._vault_client and self._vault_client.is_authenticated():
                path = self._get_vault_path(tenant_id, CredentialType.TASY_API)
                secret = self._vault_client.secrets.kv.v2.read_secret_version(path=path)
                data = secret["data"]["data"]

                credentials = TasyCredentials(
                    username=data["username"],
                    password=SecretStr(data["password"]),
                    api_key=SecretStr(data.get("api_key")) if data.get("api_key") else None,
                    base_url=data["base_url"],
                )
            else:
                # Fallback: load from environment (development only)
                logger.warning(
                    "Using fallback credentials (development only)", tenant_id=tenant_id
                )
                credentials = TasyCredentials(
                    username="tasy_user",
                    password=SecretStr("tasy_password"),
                    base_url=self._settings.integration.tasy_base_url,
                )

            # Cache credentials
            await self._set_cache(tenant_id, CredentialType.TASY_API, credentials)
            await self._audit_access(tenant_id, CredentialType.TASY_API, True)

            return credentials

        except Exception as e:
            await self._audit_access(
                tenant_id, CredentialType.TASY_API, False, error=str(e)
            )
            logger.error(
                "Failed to retrieve TASY credentials",
                tenant_id=tenant_id,
                error=str(e),
            )
            raise

    async def get_tiss_certificate(self, tenant_id: str) -> TissCertificate:
        """
        Get TISS certificate for ANS submission.

        Args:
            tenant_id: Tenant identifier

        Returns:
            TISS certificate

        Raises:
            VaultError: If certificate cannot be retrieved
        """
        # Check cache first
        cached = await self._get_from_cache(tenant_id, CredentialType.TISS_CERTIFICATE)
        if cached:
            await self._audit_access(tenant_id, CredentialType.TISS_CERTIFICATE, True)
            return cached

        try:
            # Retrieve from Vault
            if self._vault_client and self._vault_client.is_authenticated():
                path = self._get_vault_path(tenant_id, CredentialType.TISS_CERTIFICATE)
                secret = self._vault_client.secrets.kv.v2.read_secret_version(path=path)
                data = secret["data"]["data"]

                certificate = TissCertificate(
                    certificate_pem=SecretStr(data["certificate_pem"]),
                    private_key_pem=SecretStr(data["private_key_pem"]),
                    passphrase=SecretStr(data["passphrase"]) if data.get("passphrase") else None,
                    valid_until=datetime.fromisoformat(data["valid_until"]),
                    issuer=data["issuer"],
                )

                # Warn if certificate is expiring soon
                if certificate.days_until_expiration < 30:
                    logger.warning(
                        "TISS certificate expiring soon",
                        tenant_id=tenant_id,
                        days_remaining=certificate.days_until_expiration,
                    )
            else:
                # Fallback not available for certificates (security)
                raise VaultError("Vault not available for certificate retrieval")

            # Cache certificate
            await self._set_cache(tenant_id, CredentialType.TISS_CERTIFICATE, certificate)
            await self._audit_access(tenant_id, CredentialType.TISS_CERTIFICATE, True)

            return certificate

        except Exception as e:
            await self._audit_access(
                tenant_id, CredentialType.TISS_CERTIFICATE, False, error=str(e)
            )
            logger.error(
                "Failed to retrieve TISS certificate",
                tenant_id=tenant_id,
                error=str(e),
            )
            raise

    async def get_whatsapp_token(self, tenant_id: str) -> WhatsAppCredentials:
        """
        Get WhatsApp Business API credentials.

        Args:
            tenant_id: Tenant identifier

        Returns:
            WhatsApp credentials

        Raises:
            VaultError: If credentials cannot be retrieved
        """
        # Check cache first
        cached = await self._get_from_cache(tenant_id, CredentialType.WHATSAPP_TOKEN)
        if cached:
            await self._audit_access(tenant_id, CredentialType.WHATSAPP_TOKEN, True)
            return cached

        try:
            # Retrieve from Vault
            if self._vault_client and self._vault_client.is_authenticated():
                path = self._get_vault_path(tenant_id, CredentialType.WHATSAPP_TOKEN)
                secret = self._vault_client.secrets.kv.v2.read_secret_version(path=path)
                data = secret["data"]["data"]

                credentials = WhatsAppCredentials(
                    access_token=SecretStr(data["access_token"]),
                    phone_number_id=data["phone_number_id"],
                    business_account_id=data["business_account_id"],
                    webhook_verify_token=SecretStr(data.get("webhook_verify_token"))
                    if data.get("webhook_verify_token")
                    else None,
                )
            else:
                # Fallback: load from environment (development only)
                logger.warning(
                    "Using fallback WhatsApp credentials (development only)",
                    tenant_id=tenant_id,
                )
                credentials = WhatsAppCredentials(
                    access_token=SecretStr("whatsapp_token"),
                    phone_number_id=self._settings.integration.whatsapp_phone_number_id
                    or "default_id",
                    business_account_id="default_account",
                )

            # Cache credentials
            await self._set_cache(tenant_id, CredentialType.WHATSAPP_TOKEN, credentials)
            await self._audit_access(tenant_id, CredentialType.WHATSAPP_TOKEN, True)

            return credentials

        except Exception as e:
            await self._audit_access(
                tenant_id, CredentialType.WHATSAPP_TOKEN, False, error=str(e)
            )
            logger.error(
                "Failed to retrieve WhatsApp credentials",
                tenant_id=tenant_id,
                error=str(e),
            )
            raise

    async def rotate_credentials(
        self, tenant_id: str, credential_type: CredentialType
    ) -> None:
        """
        Rotate credentials for a tenant.

        Args:
            tenant_id: Tenant identifier
            credential_type: Type of credential to rotate

        Note:
            This invalidates the cache. New credentials must be
            stored in Vault before calling this method.
        """
        await self._invalidate_cache(tenant_id, credential_type)
        logger.info(
            "Credentials rotated",
            tenant_id=tenant_id,
            type=credential_type.value,
        )

    async def close(self) -> None:
        """Clean up resources."""
        async with self._cache_lock:
            self._cache.clear()

        if self._vault_client:
            # Vault client doesn't need explicit cleanup
            self._vault_client = None

        self._initialized = False
        logger.info("Credential manager closed")

    @property
    def is_initialized(self) -> bool:
        """Check if credential manager is initialized."""
        return self._initialized

    @property
    def cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "total_entries": len(self._cache),
            "entries": [
                {
                    "key": key,
                    "cached_at": cached.cached_at.isoformat(),
                    "remaining_ttl": cached.remaining_ttl,
                    "access_count": cached.access_count,
                }
                for key, cached in self._cache.items()
            ],
        }
