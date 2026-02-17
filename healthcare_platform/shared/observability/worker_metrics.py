"""Prometheus metrics stubs for worker observability.

Uses try/except so the module works even without prometheus_client installed.
"""
from __future__ import annotations

from typing import Any

try:
    from prometheus_client import Counter, Histogram

    WORKER_EXECUTION_TIME = Histogram(
        'worker_execution_seconds',
        'Time spent executing a worker task',
        ['worker_name', 'tenant_id', 'routing_result'],
    )
    WORKER_ERRORS_TOTAL = Counter(
        'worker_errors_total',
        'Total worker errors',
        ['worker_name', 'error_type'],
    )
    WORKER_DMN_CALLS = Counter(
        'worker_dmn_calls_total',
        'Total DMN table evaluations',
        ['worker_name', 'dmn_table'],
    )
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


def record_execution(worker_name: str, tenant_id: str, duration: float, routing: str = 'unknown') -> None:
    """Record a successful worker execution."""
    if _HAS_PROMETHEUS:
        WORKER_EXECUTION_TIME.labels(
            worker_name=worker_name, tenant_id=tenant_id, routing_result=routing,
        ).observe(duration)


def record_error(worker_name: str, error_type: str) -> None:
    """Record a worker error."""
    if _HAS_PROMETHEUS:
        WORKER_ERRORS_TOTAL.labels(worker_name=worker_name, error_type=error_type).inc()


def record_dmn_call(worker_name: str, dmn_table: str) -> None:
    """Record a DMN table evaluation."""
    if _HAS_PROMETHEUS:
        WORKER_DMN_CALLS.labels(worker_name=worker_name, dmn_table=dmn_table).inc()
