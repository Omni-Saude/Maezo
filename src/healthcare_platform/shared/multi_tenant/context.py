"""Thread-local tenant context (ADR-002).

Provides TenantContext stored in contextvars for async safety.
Every request / external-task handler MUST set context before processing.
"""
from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import InvalidTenant
from healthcare_platform.shared.i18n import _

logger = logging.getLogger(__name__)

# ── Tenant-to-identifier mapping (ADR-002) ─────────────────────────────

TENANT_ID_MAP: dict[TenantCode, str] = {
    TenantCode.HOSPITAL_A: "austa-hospital",
    TenantCode.AMH_SP: "amh-sp-morumbi",
    TenantCode.AMH_RJ: "amh-rj-barra",
    TenantCode.AMH_MG: "amh-mg-bh",
}

TENANT_ID_REVERSE: dict[str, TenantCode] = {v: k for k, v in TENANT_ID_MAP.items()}


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable tenant context propagated through the call chain."""

    tenant_code: TenantCode
    tenant_id: str  # e.g. "austa-hospital"
    correlation_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_tenant_id(
        cls, tenant_id: str, *, correlation_id: str | None = None
    ) -> TenantContext:
        """Create context from raw tenant identifier string."""
        code = TENANT_ID_REVERSE.get(tenant_id)
        if code is None:
            raise InvalidTenant(
                _("Tenant desconhecido: {}. Válidos: {}").format(
                    tenant_id, list(TENANT_ID_REVERSE.keys())
                ),
                details={"tenant_id": tenant_id},
            )
        return cls(tenant_code=code, tenant_id=tenant_id, correlation_id=correlation_id)

    @classmethod
    def from_tenant_code(
        cls, code: TenantCode, *, correlation_id: str | None = None
    ) -> TenantContext:
        """Create context from TenantCode enum."""
        tenant_id = TENANT_ID_MAP.get(code)
        if tenant_id is None:
            raise InvalidTenant(
                _("TenantCode desconhecido: {}").format(code),
                details={"tenant_code": str(code)},
            )
        return cls(tenant_code=code, tenant_id=tenant_id, correlation_id=correlation_id)


# ── Context variable (async-safe, replaces threading.local) ────────────

_tenant_ctx_var: contextvars.ContextVar[TenantContext | None] = contextvars.ContextVar(
    "tenant_context", default=None
)


def set_current_tenant(ctx: TenantContext) -> contextvars.Token[TenantContext | None]:
    """Set tenant context for the current async task / thread."""
    logger.debug("Tenant context set: %s (%s)", ctx.tenant_id, ctx.correlation_id)
    return _tenant_ctx_var.set(ctx)


def get_current_tenant() -> TenantContext | None:
    """Get tenant context for the current async task / thread. Returns None if unset."""
    return _tenant_ctx_var.get()


def get_required_tenant() -> TenantContext:
    """Get tenant context, raising if not set."""
    ctx = _tenant_ctx_var.get()
    if ctx is None:
        raise InvalidTenant(_("Contexto do tenant não definido. Chame set_current_tenant primeiro."))
    return ctx


def clear_tenant() -> None:
    """Clear tenant context for the current async task / thread."""
    _tenant_ctx_var.set(None)
    logger.debug("Tenant context cleared")
