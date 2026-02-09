"""
Observability Stack - Logging, Metrics, Tracing, and Health Checks.

ADR-010: OpenTelemetry, Prometheus, Grafana
ADR-011: LGPD - PII redaction in logs
"""

from platform.shared.observability.correlation import CorrelationContext
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_api_call, track_task_execution
from platform.shared.observability.redaction import PIIRedactor

__all__ = [
    "get_logger",
    "track_task_execution",
    "track_api_call",
    "PIIRedactor",
    "CorrelationContext",
]
