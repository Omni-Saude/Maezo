"""
Tenant context management for multi-tenant operations.

Provides thread-safe and async-safe tenant context using contextvars.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)

# Context variable for current tenant
_current_tenant: contextvars.ContextVar[Optional["TenantContext"]] = contextvars.ContextVar(
    "current_tenant", default=None
)


@dataclass(frozen=True)
class TenantInfo:
    """
    Immutable tenant information.

    Attributes:
        tenant_id: Unique tenant identifier
        tenant_name: Human-readable tenant name
        database_schema: Database schema for this tenant
        settings: Tenant-specific settings
    """

    tenant_id: str
    tenant_name: str
    database_schema: str
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def schema_prefix(self) -> str:
        """Get the schema prefix for SQL queries."""
        return f"{self.database_schema}."


@dataclass
class TenantContext:
    """
    Context manager for tenant-scoped operations.

    Manages the current tenant context using contextvars for
    thread-safe and async-safe operation.

    Example:
        async with TenantContext(tenant_info) as ctx:
            # All database operations within this block
            # will use the tenant's schema
            result = await repository.find_all()

    Attributes:
        tenant: Tenant information
        correlation_id: Unique request correlation ID
        user_id: Current user ID (optional)
        started_at: Context creation timestamp
    """

    tenant: TenantInfo
    correlation_id: UUID = field(default_factory=uuid4)
    user_id: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)

    _token: Optional[contextvars.Token[Optional["TenantContext"]]] = field(
        default=None, repr=False, compare=False
    )

    def __enter__(self) -> "TenantContext":
        """Enter the tenant context."""
        self._token = _current_tenant.set(self)
        logger.debug(
            "Entered tenant context",
            tenant_id=self.tenant.tenant_id,
            correlation_id=str(self.correlation_id),
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the tenant context."""
        if self._token is not None:
            _current_tenant.reset(self._token)
            self._token = None
        logger.debug(
            "Exited tenant context",
            tenant_id=self.tenant.tenant_id,
            correlation_id=str(self.correlation_id),
        )

    async def __aenter__(self) -> "TenantContext":
        """Async enter the tenant context."""
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async exit the tenant context."""
        self.__exit__(exc_type, exc_val, exc_tb)

    @classmethod
    def from_job_variables(
        cls,
        variables: dict[str, Any],
        default_tenant_id: str = "default",
    ) -> "TenantContext":
        """
        Create TenantContext from Camunda job variables.

        Args:
            variables: Job variables from Camunda
            default_tenant_id: Default tenant ID if not specified

        Returns:
            TenantContext instance
        """
        tenant_id = variables.get("tenantId", default_tenant_id)
        tenant_name = variables.get("tenantName", tenant_id)
        database_schema = variables.get("databaseSchema", f"tenant_{tenant_id}")
        correlation_id = variables.get("correlationId")
        user_id = variables.get("userId")

        tenant_info = TenantInfo(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            database_schema=database_schema,
            settings=variables.get("tenantSettings", {}),
        )

        return cls(
            tenant=tenant_info,
            correlation_id=UUID(correlation_id) if correlation_id else uuid4(),
            user_id=user_id,
        )

    def get_logger(self) -> structlog.stdlib.BoundLogger:
        """Get a logger bound with tenant context."""
        return logger.bind(
            tenant_id=self.tenant.tenant_id,
            correlation_id=str(self.correlation_id),
            user_id=self.user_id,
        )


def get_current_tenant() -> Optional[TenantContext]:
    """
    Get the current tenant context.

    Returns:
        Current TenantContext or None if not in a tenant context
    """
    return _current_tenant.get()


def require_tenant_context() -> TenantContext:
    """
    Get the current tenant context, raising an error if not set.

    Returns:
        Current TenantContext

    Raises:
        RuntimeError: If not in a tenant context
    """
    ctx = get_current_tenant()
    if ctx is None:
        raise RuntimeError("No tenant context set. Ensure operation is within TenantContext.")
    return ctx


def get_current_tenant_id() -> Optional[str]:
    """
    Get the current tenant ID.

    Returns:
        Current tenant ID or None if not in a tenant context
    """
    ctx = get_current_tenant()
    return ctx.tenant.tenant_id if ctx else None


def get_current_schema() -> Optional[str]:
    """
    Get the current tenant's database schema.

    Returns:
        Current database schema or None if not in a tenant context
    """
    ctx = get_current_tenant()
    return ctx.tenant.database_schema if ctx else None
