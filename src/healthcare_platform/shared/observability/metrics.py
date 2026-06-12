"""
Prometheus Metrics Collectors.

ADR-010: Prometheus metrics with multi-tenant labels.

Provides decorators:
    @track_task_execution  - Histogram + counter for CIB7 external task workers
    @track_api_call        - Histogram + counter for outbound API calls

Usage:
    from healthcare_platform.shared.observability.metrics import track_task_execution

    @track_task_execution(_metric_name="billing_validate")
    async def execute(self, task): ...
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

from prometheus_client import Counter, Gauge, Histogram, Info

from healthcare_platform.shared.observability.correlation import get_current_context

# ---------------------------------------------------------------------------
# Task execution metrics
# ---------------------------------------------------------------------------

TASK_DURATION = Histogram(
    "cib7_task_duration_seconds",
    "Duration of external task execution",
    labelnames=["worker", "tenant_id", "status"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

TASK_TOTAL = Counter(
    "cib7_task_total",
    "Total number of external tasks processed",
    labelnames=["worker", "tenant_id", "status"],
)

TASK_ERRORS = Counter(
    "cib7_task_errors_total",
    "Total task errors by type",
    labelnames=["worker", "tenant_id", "error_type"],
)

TASKS_IN_PROGRESS = Gauge(
    "cib7_tasks_in_progress",
    "Tasks currently being processed",
    labelnames=["worker"],
)

# ---------------------------------------------------------------------------
# API call metrics
# ---------------------------------------------------------------------------

API_CALL_DURATION = Histogram(
    "cib7_api_call_duration_seconds",
    "Duration of outbound API calls",
    labelnames=["service", "endpoint", "method", "status_code"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

API_CALL_TOTAL = Counter(
    "cib7_api_call_total",
    "Total outbound API calls",
    labelnames=["service", "endpoint", "method", "status_code"],
)

# ---------------------------------------------------------------------------
# Process metrics
# ---------------------------------------------------------------------------

PROCESS_INSTANCES_ACTIVE = Gauge(
    "cib7_process_instances_active",
    "Active process instances by definition",
    labelnames=["process_definition", "tenant_id"],
)

BUILD_INFO = Info(
    "cib7_build",
    "Build information",
)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def track_task_execution(
    metric_name: str | None = None, task_type: str | None = None
) -> Callable:
    """Decorator to track CIB7 external task execution metrics.

    Records duration histogram, total counter, and error counter.
    Extracts tenant_id from correlation context.

    Supports both parameter styles:
    - New style: task_type
    - Old style: metric_name
    """
    # Support both parameter naming conventions
    _metric_name = task_type or metric_name or "unknown"

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = get_current_context()
            tenant = ctx.tenant_id or "unknown"
            TASKS_IN_PROGRESS.labels(worker=_metric_name).inc()
            start = time.monotonic()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as exc:
                status = "error"
                error_type = type(exc).__name__
                TASK_ERRORS.labels(
                    worker=_metric_name, tenant_id=tenant, error_type=error_type
                ).inc()
                raise
            finally:
                elapsed = time.monotonic() - start
                TASK_DURATION.labels(
                    worker=_metric_name, tenant_id=tenant, status=status
                ).observe(elapsed)
                TASK_TOTAL.labels(
                    worker=_metric_name, tenant_id=tenant, status=status
                ).inc()
                TASKS_IN_PROGRESS.labels(worker=_metric_name).dec()

        return wrapper

    return decorator


def track_api_call(
    service: str | None = None,
    endpoint: str | None = None,
    method: str = "GET",
    service_name: str | None = None,
    operation: str | None = None,
) -> Callable:
    """Decorator to track outbound API call metrics.

    Records duration histogram and total counter with status code.

    Supports both parameter styles:
    - New style: service_name, operation
    - Old style: service, endpoint, method
    """
    # Support both parameter naming conventions
    _service = service_name or service or "unknown"
    _endpoint = operation or endpoint or "unknown"

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            status_code = "000"
            try:
                result = await func(*args, **kwargs)
                status_code = str(getattr(result, "status_code", 200))
                return result
            except Exception:
                status_code = "error"
                raise
            finally:
                elapsed = time.monotonic() - start
                API_CALL_DURATION.labels(
                    service=_service,
                    endpoint=_endpoint,
                    method=method,
                    status_code=status_code,
                ).observe(elapsed)
                API_CALL_TOTAL.labels(
                    service=_service,
                    endpoint=_endpoint,
                    method=method,
                    status_code=status_code,
                ).inc()

        return wrapper

    return decorator
