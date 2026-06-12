"""Tenant configuration management with DMN overrides and feature flags (ADR-007).

ADR-007: Global DMN tables as defaults, tenant-specific DMN tables override per hospital.
Payer-specific logic is handled via input parameters, not separate deployments.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import InvalidTenant
from healthcare_platform.shared.multi_tenant.context import TENANT_ID_MAP, get_required_tenant
from healthcare_platform.shared.i18n import _

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TenantConfig:
    """Configuration for a single tenant."""

    tenant_id: str
    tenant_code: TenantCode
    dmn_overrides: dict[str, str] = field(default_factory=dict)
    feature_flags: dict[str, bool] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    def has_dmn_override(self, decision_key: str) -> bool:
        """Check if tenant has a specific DMN override (ADR-007)."""
        return decision_key in self.dmn_overrides

    def get_dmn_deployment_id(self, decision_key: str) -> str | None:
        """Get tenant-specific DMN deployment ID, or None for global fallback."""
        return self.dmn_overrides.get(decision_key)

    def is_feature_enabled(self, feature: str, *, default: bool = False) -> bool:
        """Check if a feature flag is enabled for this tenant."""
        return self.feature_flags.get(feature, default)


class TenantConfigurationManager:
    """Manages per-tenant configuration, DMN overrides, and feature flags.

    ADR-007 resolution order:
    1. Check tenant-specific DMN table (deployed with tenantId)
    2. Fall back to global DMN table (deployed without tenantId)
    """

    def __init__(self) -> None:
        self._configs: dict[TenantCode, TenantConfig] = {}
        self._global_settings: dict[str, Any] = {}

    def register_tenant(
        self,
        tenant_code: TenantCode,
        *,
        dmn_overrides: dict[str, str] | None = None,
        feature_flags: dict[str, bool] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> TenantConfig:
        """Register or update configuration for a tenant."""
        if tenant_code not in TENANT_ID_MAP:
            raise InvalidTenant(
                _("Tenant desconhecido: {}").format(tenant_code),
                details={"tenant_code": str(tenant_code)},
            )

        tenant_id = TENANT_ID_MAP[tenant_code]
        config = TenantConfig(
            tenant_id=tenant_id,
            tenant_code=tenant_code,
            dmn_overrides=dmn_overrides or {},
            feature_flags=feature_flags or {},
            settings=settings or {},
        )
        self._configs[tenant_code] = config
        logger.info("Registered config for tenant %s", tenant_id)
        return config

    def get_config(self, tenant_code: TenantCode | None = None) -> TenantConfig:
        """Get configuration for a tenant.

        If tenant_code is None, uses the current tenant context.
        Falls back to empty config if tenant is valid but not explicitly registered.
        """
        if tenant_code is None:
            ctx = get_required_tenant()
            tenant_code = ctx.tenant_code

        if tenant_code not in TENANT_ID_MAP:
            raise InvalidTenant(
                _("Tenant desconhecido: {}").format(tenant_code),
                details={"tenant_code": str(tenant_code)},
            )

        if tenant_code not in self._configs:
            # Auto-register with defaults
            return self.register_tenant(tenant_code)

        return self._configs[tenant_code]

    def resolve_dmn_decision(
        self, decision_key: str, tenant_code: TenantCode | None = None
    ) -> str | None:
        """Resolve DMN decision: tenant override first, then global fallback.

        Returns the deployment ID to use, or None if no override exists
        (caller should use global default).
        """
        config = self.get_config(tenant_code)
        override = config.get_dmn_deployment_id(decision_key)
        if override:
            logger.debug(
                "DMN override for %s tenant=%s: %s",
                decision_key, config.tenant_id, override,
            )
        return override

    def set_global_setting(self, key: str, value: Any) -> None:
        """Set a global setting (applies to all tenants unless overridden)."""
        self._global_settings[key] = value

    def get_setting(
        self, key: str, *, tenant_code: TenantCode | None = None, default: Any = None
    ) -> Any:
        """Get a setting value: tenant-specific first, then global, then default."""
        config = self.get_config(tenant_code)
        if key in config.settings:
            return config.settings[key]
        return self._global_settings.get(key, default)
