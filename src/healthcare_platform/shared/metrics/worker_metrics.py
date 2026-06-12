"""
Worker Metrics Module
Provides metrics collection for external task workers.
"""
from __future__ import annotations

from typing import Any, Dict


class WorkerMetrics:
    """
    Metrics collector for worker execution.
    
    Records latency, success/failure rates, DMN call counts, etc.
    """

    def __init__(self):
        self._metrics: Dict[str, Any] = {}

    def record_execution(
        self,
        worker_id: str,
        tenant_id: str,
        duration_ms: float,
        success: bool,
    ) -> None:
        """Record worker execution metrics."""
        pass  # Stub - would send to Prometheus/StatsD

    def record_dmn_call(
        self,
        decision_key: str,
        tenant_id: str,
        latency_ms: float,
        success: bool,
    ) -> None:
        """Record DMN evaluation metrics."""
        pass  # Stub - would send to Prometheus/StatsD

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        return self._metrics.copy()
