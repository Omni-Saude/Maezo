"""Tenant-aware database connection pooling (ADR-002).

Single PostgreSQL database with tenant markers — connections are pooled
per-tenant to enable per-tenant resource limits and connection tracking.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import InvalidTenant
from platform.shared.multi_tenant.context import TENANT_ID_MAP, get_required_tenant
from platform.shared.i18n import _

logger = logging.getLogger(__name__)


class AsyncConnectionPool(Protocol):
    """Protocol for async connection pool implementations."""

    async def acquire(self) -> Any: ...
    async def release(self, conn: Any) -> None: ...
    async def close(self) -> None: ...


class TenantDatabaseManager:
    """Manages per-tenant connection pools to a shared PostgreSQL database.

    ADR-002: Single database, tenant isolation via tenant_id column.
    Each tenant gets its own connection pool for resource isolation
    and noisy-neighbor mitigation.
    """

    def __init__(
        self,
        dsn_template: str,
        *,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
        pool_factory: Any = None,
    ) -> None:
        self._dsn_template = dsn_template
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size
        self._pool_factory = pool_factory
        self._pools: dict[TenantCode, AsyncConnectionPool] = {}

    async def get_pool(self, tenant_code: TenantCode | None = None) -> AsyncConnectionPool:
        """Get or create connection pool for a tenant.

        If tenant_code is None, uses the current tenant context.
        """
        if tenant_code is None:
            ctx = get_required_tenant()
            tenant_code = ctx.tenant_code

        if tenant_code not in TENANT_ID_MAP:
            raise InvalidTenant(
                _("Tenant desconhecido: {}").format(tenant_code),
                details={"tenant_code": str(tenant_code)},
            )

        if tenant_code not in self._pools:
            self._pools[tenant_code] = await self._create_pool(tenant_code)

        return self._pools[tenant_code]

    async def _create_pool(self, tenant_code: TenantCode) -> AsyncConnectionPool:
        """Create a new connection pool for the given tenant."""
        tenant_id = TENANT_ID_MAP[tenant_code]
        dsn = self._dsn_template.format(tenant_id=tenant_id)
        logger.info("Creating connection pool for tenant %s", tenant_id)

        if self._pool_factory is not None:
            return await self._pool_factory(
                dsn,
                min_size=self._min_pool_size,
                max_size=self._max_pool_size,
            )

        # Lazy import — asyncpg is optional
        try:
            import asyncpg  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                _("asyncpg é necessário para TenantDatabaseManager. "
                  "Instale com: pip install asyncpg")
            ) from exc

        return await asyncpg.create_pool(
            dsn,
            min_size=self._min_pool_size,
            max_size=self._max_pool_size,
        )

    async def close_all(self) -> None:
        """Close all tenant connection pools."""
        for tenant_code, pool in self._pools.items():
            logger.info("Closing pool for tenant %s", tenant_code)
            await pool.close()
        self._pools.clear()

    async def health_check(self) -> dict[str, bool]:
        """Check connectivity for all active pools."""
        results: dict[str, bool] = {}
        for tenant_code, pool in self._pools.items():
            tenant_id = TENANT_ID_MAP[tenant_code]
            try:
                conn = await pool.acquire()
                await pool.release(conn)
                results[tenant_id] = True
            except Exception:
                logger.exception("Health check failed for tenant %s", tenant_id)
                results[tenant_id] = False
        return results
