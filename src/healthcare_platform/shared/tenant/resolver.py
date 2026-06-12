"""
Tenant Resolver Module
Provides tenant resolution from process variables (ADR-002).
"""
from __future__ import annotations

from typing import Any, Dict


class TenantResolver:
    """
    Tenant resolver for external task workers.
    
    Resolution order (ADR-002):
    1. Explicit "tenant_id" variable
    2. "hospitalCode" variable (implicit)
    3. Deployment tenant marker
    4. Default tenant
    """

    def __init__(self, default_tenant: str = "default"):
        self.default_tenant = default_tenant

    def resolve(self, variables: Dict[str, Any]) -> str:
        """
        Resolve tenant ID from process variables.
        
        Args:
            variables: Process variables dict
            
        Returns:
            Resolved tenant ID
        """
        # Priority 1: Explicit tenant_id
        if "tenant_id" in variables:
            return str(variables["tenant_id"])
        
        # Priority 2: hospitalCode (implicit)
        if "hospitalCode" in variables:
            return str(variables["hospitalCode"])
        
        # Priority 3: tenantId (camelCase variant)
        if "tenantId" in variables:
            return str(variables["tenantId"])
        
        # Fallback: default tenant
        return self.default_tenant
