"""Tenant-aware credential management with vault integration (ADR-008).

Each tenant has its own Keycloak client credentials and service accounts.
Credentials are fetched from a vault backend (HashiCorp Vault, AWS Secrets
Manager, or environment variables for local dev).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Any, Protocol

from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import InvalidTenant, TenantAccessDenied
from platform.shared.multi_tenant.context import TENANT_ID_MAP, get_required_tenant

logger = logging.getLogger(__name__)


@unique
class VaultBackend(StrEnum):
    ENV = "env"
    HASHICORP = "hashicorp"
    AWS_SECRETS = "aws-secrets"


@dataclass(frozen=True, slots=True)
class TenantCredentials:
    """OAuth2 client credentials for a tenant's Keycloak realm (ADR-008)."""

    tenant_id: str
    keycloak_url: str
    realm: str  # default: "austa-bpm"
    client_id: str
    client_secret: str
    token_endpoint: str


class VaultClient(Protocol):
    """Protocol for vault implementations."""

    async def get_secret(self, path: str) -> dict[str, str]: ...


class TenantCredentialManager:
    """Manages per-tenant OAuth2 credentials via vault integration.

    ADR-008: Keycloak realm "austa-bpm" with per-tenant service clients.
    """

    def __init__(
        self,
        *,
        vault_backend: VaultBackend = VaultBackend.ENV,
        vault_client: VaultClient | None = None,
        keycloak_url: str = "",
        realm: str = "austa-bpm",
        secret_path_template: str = "healthcare/{tenant_id}/keycloak",
    ) -> None:
        self._vault_backend = vault_backend
        self._vault_client = vault_client
        self._keycloak_url = keycloak_url or os.getenv("KEYCLOAK_URL", "http://localhost:8080")
        self._realm = realm
        self._secret_path_template = secret_path_template
        self._cache: dict[TenantCode, TenantCredentials] = {}

    async def get_credentials(
        self, tenant_code: TenantCode | None = None
    ) -> TenantCredentials:
        """Get OAuth2 credentials for a tenant.

        If tenant_code is None, uses the current tenant context.
        """
        if tenant_code is None:
            ctx = get_required_tenant()
            tenant_code = ctx.tenant_code

        if tenant_code not in TENANT_ID_MAP:
            raise InvalidTenant(
                f"Unknown tenant: {tenant_code!r}",
                details={"tenant_code": str(tenant_code)},
            )

        if tenant_code in self._cache:
            return self._cache[tenant_code]

        creds = await self._fetch_credentials(tenant_code)
        self._cache[tenant_code] = creds
        return creds

    async def _fetch_credentials(self, tenant_code: TenantCode) -> TenantCredentials:
        """Fetch credentials from the configured vault backend."""
        tenant_id = TENANT_ID_MAP[tenant_code]

        if self._vault_backend == VaultBackend.ENV:
            return self._from_env(tenant_code, tenant_id)

        if self._vault_client is None:
            raise RuntimeError(
                f"vault_client required for backend {self._vault_backend}"
            )

        path = self._secret_path_template.format(tenant_id=tenant_id)
        try:
            secrets = await self._vault_client.get_secret(path)
        except Exception as exc:
            raise TenantAccessDenied(
                f"Failed to fetch credentials for tenant {tenant_id}",
                details={"tenant_id": tenant_id, "vault_path": path},
            ) from exc

        return TenantCredentials(
            tenant_id=tenant_id,
            keycloak_url=secrets.get("keycloak_url", self._keycloak_url),
            realm=secrets.get("realm", self._realm),
            client_id=secrets["client_id"],
            client_secret=secrets["client_secret"],
            token_endpoint=(
                f"{secrets.get('keycloak_url', self._keycloak_url)}"
                f"/realms/{secrets.get('realm', self._realm)}"
                f"/protocol/openid-connect/token"
            ),
        )

    def _from_env(self, tenant_code: TenantCode, tenant_id: str) -> TenantCredentials:
        """Load credentials from environment variables (local dev)."""
        prefix = tenant_code.replace("-", "_").upper()
        client_id = os.getenv(f"{prefix}_CLIENT_ID", f"worker-{tenant_id}")
        client_secret = os.getenv(f"{prefix}_CLIENT_SECRET", "")

        if not client_secret:
            logger.warning("No client secret for tenant %s in env", tenant_id)

        return TenantCredentials(
            tenant_id=tenant_id,
            keycloak_url=self._keycloak_url,
            realm=self._realm,
            client_id=client_id,
            client_secret=client_secret,
            token_endpoint=(
                f"{self._keycloak_url}/realms/{self._realm}"
                f"/protocol/openid-connect/token"
            ),
        )

    def invalidate_cache(self, tenant_code: TenantCode | None = None) -> None:
        """Invalidate cached credentials. If tenant_code is None, clear all."""
        if tenant_code is None:
            self._cache.clear()
        else:
            self._cache.pop(tenant_code, None)
