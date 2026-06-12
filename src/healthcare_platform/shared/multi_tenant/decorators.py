"""Tenant-aware decorators for workers and service functions.

@require_tenant  — validates that tenant context is set before execution
@with_tenant_context — sets tenant context from function arguments
"""
from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Callable, TypeVar, overload

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import InvalidTenant
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    get_current_tenant,
    set_current_tenant,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def require_tenant(func: F) -> F:
    """Decorator that ensures tenant context is set before function execution.

    Raises InvalidTenant if no tenant context is active.
    Works with both sync and async functions.
    """
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = get_current_tenant()
            if ctx is None:
                raise InvalidTenant(
                    _("Contexto do tenant necessário para {}. "
                      "Certifique-se de que TenantMiddleware está ativo ou use @with_tenant_context.").format(func.__qualname__)
                )
            return await func(*args, **kwargs)
        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = get_current_tenant()
        if ctx is None:
            raise InvalidTenant(
                _("Contexto do tenant necessário para {}. "
                  "Certifique-se de que TenantMiddleware está ativo ou use @with_tenant_context.").format(func.__qualname__)
            )
        return func(*args, **kwargs)
    return sync_wrapper  # type: ignore[return-value]


@overload
def with_tenant_context(func: F) -> F: ...
@overload
def with_tenant_context(
    *, tenant_id_param: str = "tenant_id", tenant_code_param: str = "tenant_code"
) -> Callable[[F], F]: ...


def with_tenant_context(
    func: F | None = None,
    *,
    tenant_id_param: str = "tenant_id",
    tenant_code_param: str = "tenant_code",
) -> F | Callable[[F], F]:
    """Decorator that sets tenant context from function arguments.

    Looks for tenant_id or tenant_code in kwargs/args and sets
    the TenantContext for the duration of the function call.

    Usage:
        @with_tenant_context
        async def process(task_vars: dict, tenant_id: str = ""):
            ...

        @with_tenant_context(tenant_id_param="hospital_id")
        def handle(hospital_id: str):
            ...
    """
    def decorator(fn: F) -> F:
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                ctx = _extract_context(fn, args, kwargs, tenant_id_param, tenant_code_param)
                if ctx is not None:
                    _token = set_current_tenant(ctx)
                    try:
                        return await fn(*args, **kwargs)
                    finally:
                        clear_tenant()
                return await fn(*args, **kwargs)
            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = _extract_context(fn, args, kwargs, tenant_id_param, tenant_code_param)
            if ctx is not None:
                _token = set_current_tenant(ctx)
                try:
                    return fn(*args, **kwargs)
                finally:
                    clear_tenant()
            return fn(*args, **kwargs)
        return sync_wrapper  # type: ignore[return-value]

    if func is not None:
        return decorator(func)
    return decorator


def _extract_context(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    tenant_id_param: str,
    tenant_code_param: str,
) -> TenantContext | None:
    """Extract tenant info from function arguments."""
    # Check kwargs first
    tenant_id = kwargs.get(tenant_id_param)
    tenant_code = kwargs.get(tenant_code_param)

    # Check positional args via signature
    if tenant_id is None and tenant_code is None:
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        for i, param_name in enumerate(params):
            if i < len(args):
                if param_name == tenant_id_param:
                    tenant_id = args[i]
                elif param_name == tenant_code_param:
                    tenant_code = args[i]

    if tenant_id and isinstance(tenant_id, str):
        return TenantContext.from_tenant_id(tenant_id)
    if tenant_code and isinstance(tenant_code, (str, TenantCode)):
        code = TenantCode(tenant_code) if isinstance(tenant_code, str) else tenant_code
        return TenantContext.from_tenant_code(code)

    return None
