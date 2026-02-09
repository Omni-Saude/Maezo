"""
Prometheus metrics for monitoring worker performance.

Exposes metrics for:
- Worker execution time and counts
- Database operations
- External integrations
- Business metrics (claims processed, revenue recovered)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, TypeVar

from prometheus_client import Counter, Gauge, Histogram, Info

# Type variable for decorator
F = TypeVar("F", bound=Callable[..., object])


class MetricsRegistry:
    """
    Registry for all application metrics.

    Provides centralized access to Prometheus metrics
    with proper labeling and documentation.
    """

    def __init__(self, service_name: str = "revenue_cycle_workers"):
        """
        Initialize metrics registry.

        Args:
            service_name: Service name for metric prefixes
        """
        self.service_name = service_name

        # Application info
        self.app_info = Info(
            f"{service_name}_app_info",
            "Application information",
        )

        # Worker metrics
        self.worker_tasks_total = Counter(
            f"{service_name}_worker_tasks_total",
            "Total number of tasks processed",
            ["worker", "topic", "status"],
        )

        self.worker_task_duration_seconds = Histogram(
            f"{service_name}_worker_task_duration_seconds",
            "Task processing duration in seconds",
            ["worker", "topic"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
        )

        self.worker_active_tasks = Gauge(
            f"{service_name}_worker_active_tasks",
            "Number of tasks currently being processed",
            ["worker", "topic"],
        )

        self.worker_retries_total = Counter(
            f"{service_name}_worker_retries_total",
            "Total number of task retries",
            ["worker", "topic"],
        )

        self.worker_bpmn_errors_total = Counter(
            f"{service_name}_worker_bpmn_errors_total",
            "Total number of BPMN errors thrown",
            ["worker", "topic", "error_code"],
        )

        # Database metrics
        self.db_operations_total = Counter(
            f"{service_name}_db_operations_total",
            "Total database operations",
            ["operation", "table", "status"],
        )

        self.db_operation_duration_seconds = Histogram(
            f"{service_name}_db_operation_duration_seconds",
            "Database operation duration in seconds",
            ["operation", "table"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )

        self.db_connection_pool_size = Gauge(
            f"{service_name}_db_connection_pool_size",
            "Database connection pool size",
            ["pool_type"],
        )

        # Integration metrics
        self.integration_requests_total = Counter(
            f"{service_name}_integration_requests_total",
            "Total integration requests",
            ["system", "endpoint", "status"],
        )

        self.integration_request_duration_seconds = Histogram(
            f"{service_name}_integration_request_duration_seconds",
            "Integration request duration in seconds",
            ["system", "endpoint"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
        )

        self.integration_circuit_breaker_state = Gauge(
            f"{service_name}_integration_circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open, 0.5=half-open)",
            ["system"],
        )

        # Business metrics
        self.claims_processed_total = Counter(
            f"{service_name}_claims_processed_total",
            "Total claims processed",
            ["claim_type", "status"],
        )

        self.glosas_analyzed_total = Counter(
            f"{service_name}_glosas_analyzed_total",
            "Total glosas analyzed",
            ["glosa_type", "strategy"],
        )

        self.revenue_recovered_total = Counter(
            f"{service_name}_revenue_recovered_total",
            "Total revenue recovered from appeals (in cents)",
            ["glosa_type"],
        )

        self.appeals_submitted_total = Counter(
            f"{service_name}_appeals_submitted_total",
            "Total appeals submitted",
            ["strategy", "status"],
        )

    def set_app_info(
        self,
        version: str,
        environment: str,
        **kwargs: str,
    ) -> None:
        """
        Set application info metric.

        Args:
            version: Application version
            environment: Deployment environment
            **kwargs: Additional info labels
        """
        self.app_info.info({
            "version": version,
            "environment": environment,
            **kwargs,
        })

    def record_task_execution(
        self,
        worker: str,
        topic: str,
        duration: float,
        success: bool,
    ) -> None:
        """
        Record a task execution.

        Args:
            worker: Worker name
            topic: Camunda topic
            duration: Execution duration in seconds
            success: Whether execution was successful
        """
        status = "success" if success else "failure"

        self.worker_tasks_total.labels(
            worker=worker,
            topic=topic,
            status=status,
        ).inc()

        self.worker_task_duration_seconds.labels(
            worker=worker,
            topic=topic,
        ).observe(duration)

    def record_bpmn_error(
        self,
        worker: str,
        topic: str,
        error_code: str,
    ) -> None:
        """
        Record a BPMN error.

        Args:
            worker: Worker name
            topic: Camunda topic
            error_code: BPMN error code
        """
        self.worker_bpmn_errors_total.labels(
            worker=worker,
            topic=topic,
            error_code=error_code,
        ).inc()

    def record_glosa_analysis(
        self,
        glosa_type: str,
        strategy: str,
    ) -> None:
        """
        Record a glosa analysis.

        Args:
            glosa_type: Type of glosa
            strategy: Determined appeal strategy
        """
        self.glosas_analyzed_total.labels(
            glosa_type=glosa_type,
            strategy=strategy,
        ).inc()

    def record_revenue_recovered(
        self,
        glosa_type: str,
        amount_cents: int,
    ) -> None:
        """
        Record recovered revenue.

        Args:
            glosa_type: Type of glosa
            amount_cents: Amount recovered in cents
        """
        self.revenue_recovered_total.labels(
            glosa_type=glosa_type,
        ).inc(amount_cents)


@lru_cache
def get_metrics() -> MetricsRegistry:
    """
    Get the global metrics registry.

    Returns:
        MetricsRegistry instance (cached)
    """
    return MetricsRegistry()
