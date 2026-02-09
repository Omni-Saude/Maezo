"""
Process Instance and Task Correlation IDs.

Provides context propagation for:
- Process instance ID (from CIB7 engine)
- Task ID (external task)
- Tenant ID (multi-tenancy)
- Request/trace ID (OpenTelemetry)

Uses contextvars for async-safe propagation.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from platform.shared.i18n import _


@dataclass(frozen=True)
class CorrelationContext:
    """Immutable correlation context propagated through the call chain."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    process_instance_id: str | None = None
    task_id: str | None = None
    business_key: str | None = None
    tenant_id: str | None = None
    worker_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return non-None fields as a dict for structured logging."""
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def with_task(
        self,
        task_id: str,
        process_instance_id: str | None = None,
        business_key: str | None = None,
    ) -> CorrelationContext:
        """Derive a new context with task-level fields set."""
        return CorrelationContext(
            trace_id=self.trace_id,
            process_instance_id=process_instance_id or self.process_instance_id,
            task_id=task_id,
            business_key=business_key or self.business_key,
            tenant_id=self.tenant_id,
            worker_name=self.worker_name,
        )


# Async-safe context variable
_current_context: ContextVar[CorrelationContext | None] = ContextVar(
    "correlation_context", default=None
)


def get_current_context() -> CorrelationContext:
    """Get the current correlation context, creating one if absent."""
    ctx = _current_context.get()
    if ctx is None:
        ctx = CorrelationContext()
        _current_context.set(ctx)
    return ctx


def set_current_context(ctx: CorrelationContext) -> None:
    """Set the current correlation context."""
    _current_context.set(ctx)


def clear_current_context() -> None:
    """Clear the current correlation context."""
    _current_context.set(None)
