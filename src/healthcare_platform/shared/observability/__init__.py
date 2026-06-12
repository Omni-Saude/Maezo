"""
Observability Stack - Logging, Metrics, Tracing, and Health Checks.

ADR-010: OpenTelemetry, Prometheus, Grafana
ADR-011: LGPD - PII redaction in logs
"""

from healthcare_platform.shared.observability.correlation import CorrelationContext
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_api_call, track_task_execution
from healthcare_platform.shared.observability.redaction import PIIRedactor

__all__ = [
    "get_logger",
    "track_task_execution",
    "track_api_call",
    "PIIRedactor",
    "CorrelationContext",
]
