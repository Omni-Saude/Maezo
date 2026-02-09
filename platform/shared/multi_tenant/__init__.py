"""Multi-tenancy layer for Healthcare Orchestration Platform.

ADR-002: Single engine with tenant markers per hospital.
ADR-007: DMN federation with tenant-specific overrides.
ADR-008: Keycloak OAuth2 per tenant.

Tenants: austa-hospital, amh-sp-morumbi, amh-rj-barra, amh-mg-bh
"""
from __future__ import annotations

from platform.shared.multi_tenant.context import TenantContext, get_current_tenant
from platform.shared.multi_tenant.decorators import require_tenant, with_tenant_context
from platform.shared.multi_tenant.middleware import TenantMiddleware

__all__ = [
    "TenantContext",
    "TenantMiddleware",
    "get_current_tenant",
    "require_tenant",
    "with_tenant_context",
]
