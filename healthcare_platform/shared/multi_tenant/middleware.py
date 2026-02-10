"""FastAPI middleware for tenant extraction and context binding (ADR-002, ADR-008).

Extracts tenant_id from:
1. JWT token claims (preferred — ADR-008 Keycloak)
2. X-Tenant-ID header (fallback for internal services)
3. Query parameter ?tenant_id= (dev/testing only)

Sets TenantContext for the duration of the request.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from healthcare_platform.shared.domain.exceptions import InvalidTenant, TenantAccessDenied
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import (
    TENANT_ID_REVERSE,
    TenantContext,
    clear_tenant,
    set_current_tenant,
)

logger = logging.getLogger(__name__)

# Paths that don't require tenant context
DEFAULT_EXEMPT_PATHS: frozenset[str] = frozenset({
    "/health",
    "/ready",
    "/metrics",
    "/docs",
    "/openapi.json",
})


class TenantMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that extracts tenant_id and sets TenantContext.

    ADR-008: JWT tokens from Keycloak contain tenant info in claims.
    ADR-002: tenant_id is propagated to all downstream services.
    """

    def __init__(
        self,
        app: Any,
        *,
        jwt_claim_key: str = "tenant_id",
        header_name: str = "X-Tenant-ID",
        allow_query_param: bool = False,
        exempt_paths: Sequence[str] | None = None,
        jwt_decoder: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(app)
        self._jwt_claim_key = jwt_claim_key
        self._header_name = header_name
        self._allow_query_param = allow_query_param
        self._exempt_paths = frozenset(exempt_paths) if exempt_paths else DEFAULT_EXEMPT_PATHS
        self._jwt_decoder = jwt_decoder

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip tenant extraction for exempt paths
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        try:
            tenant_id = self._extract_tenant_id(request)
        except InvalidTenant as exc:
            logger.warning("Tenant extraction failed: %s", exc)
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_tenant", "detail": str(exc)},
            )
        except TenantAccessDenied as exc:
            logger.warning("Tenant access denied: %s", exc)
            return JSONResponse(
                status_code=403,
                content={"error": "tenant_access_denied", "detail": str(exc)},
            )

        if tenant_id is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "missing_tenant",
                    "detail": _("Identificação do tenant necessária via JWT, cabeçalho, ou parâmetro de consulta."),
                },
            )

        # Build and set context
        correlation_id = request.headers.get("X-Correlation-ID")
        ctx = TenantContext.from_tenant_id(tenant_id, correlation_id=correlation_id)
        token = set_current_tenant(ctx)

        try:
            response = await call_next(request)
            # Propagate tenant_id in response headers for tracing
            response.headers["X-Tenant-ID"] = ctx.tenant_id
            return response
        finally:
            clear_tenant()

    def _extract_tenant_id(self, request: Request) -> str | None:
        """Extract tenant_id from request using priority chain."""

        # 1. JWT token (ADR-008)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and self._jwt_decoder:
            token = auth_header[7:]
            try:
                claims = self._jwt_decoder(token)
                tenant_id = claims.get(self._jwt_claim_key)
                if tenant_id and tenant_id in TENANT_ID_REVERSE:
                    return tenant_id
                if tenant_id:
                    raise InvalidTenant(
                        _("JWT contém tenant desconhecido: {}").format(tenant_id),
                        details={"tenant_id": tenant_id},
                    )
            except InvalidTenant:
                raise
            except Exception:
                logger.debug("JWT decode failed, trying header fallback")

        # 2. Header
        header_value = request.headers.get(self._header_name)
        if header_value:
            if header_value not in TENANT_ID_REVERSE:
                raise InvalidTenant(
                    _("Cabeçalho {} inválido: {}").format(self._header_name, header_value),
                    details={"tenant_id": header_value},
                )
            return header_value

        # 3. Query parameter (dev only)
        if self._allow_query_param:
            qp = request.query_params.get("tenant_id")
            if qp:
                if qp not in TENANT_ID_REVERSE:
                    raise InvalidTenant(
                        _("Parâmetro de consulta tenant_id inválido: {}").format(qp),
                        details={"tenant_id": qp},
                    )
                return qp

        return None
