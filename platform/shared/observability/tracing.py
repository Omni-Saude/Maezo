"""
OpenTelemetry Tracer Configuration.

ADR-010: Distributed tracing with OpenTelemetry, exported to Jaeger/OTLP.
Integrates with CIB7 process instance correlation.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import StatusCode

from platform.shared.observability.correlation import get_current_context

_configured = False


def configure_tracing(
    service_name: str = "healthcare-orchestrator",
    otlp_endpoint: str | None = None,
    console_export: bool = False,
    environment: str = "development",
) -> TracerProvider:
    """Configure OpenTelemetry tracing.

    Call once at application startup.

    Args:
        service_name: Name of the service for span metadata.
        otlp_endpoint: OTLP collector gRPC endpoint (e.g. "http://otel-collector:4317").
        console_export: If True, also export spans to console (dev mode).
        environment: Deployment environment tag.

    Returns:
        Configured TracerProvider.
    """
    global _configured
    if _configured:
        return trace.get_tracer_provider()  # type: ignore[return-value]

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "healthcare-platform",
            "deployment.environment": environment,
        }
    )

    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    if console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _configured = True
    return provider


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance, auto-configuring if needed."""
    if not _configured:
        configure_tracing()
    return trace.get_tracer(name)


def span_from_task(
    tracer: trace.Tracer,
    operation: str,
    task_id: str | None = None,
    **attributes: Any,
) -> trace.Span:
    """Create a span enriched with CIB7 correlation context.

    Usage:
        tracer = get_tracer(__name__)
        with span_from_task(tracer, "validate-eligibility", task_id="t-123") as span:
            ...
    """
    ctx = get_current_context()
    all_attrs: dict[str, Any] = {
        "cib7.process_instance_id": ctx.process_instance_id or "",
        "cib7.task_id": task_id or ctx.task_id or "",
        "cib7.business_key": ctx.business_key or "",
        "cib7.tenant_id": ctx.tenant_id or "",
        "cib7.worker": ctx.worker_name or "",
    }
    all_attrs.update(attributes)
    # Filter out empty values
    all_attrs = {k: v for k, v in all_attrs.items() if v}

    span = tracer.start_span(operation, attributes=all_attrs)
    return span


def record_exception(span: trace.Span, exc: Exception) -> None:
    """Record an exception on a span and set error status."""
    span.set_status(StatusCode.ERROR, str(exc))
    span.record_exception(exc)
