"""
Structured Logger with PII Redaction (LGPD Compliant).

ADR-010: Structured JSON logging with OpenTelemetry correlation.
ADR-011: All log output is PII-redacted before emission.

Usage:
    from healthcare_platform.shared.observability.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Patient registered", patient_id="123", tenant_id="hospital-a")
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from healthcare_platform.shared.observability.correlation import get_current_context
from healthcare_platform.shared.observability.redaction import PIIRedactor

_redactor = PIIRedactor()
_configured = False


def _add_correlation_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Inject correlation IDs into every log event."""
    ctx = get_current_context()
    event_dict.update(ctx.as_dict())
    return event_dict


def _redact_pii(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Redact PII from all string values in the log event."""
    return _redactor.redact_dict(event_dict)


def configure_logging(
    level: str = "INFO",
    json_output: bool = True,
    redact: bool = True,
) -> None:
    """Configure structlog with PII redaction and correlation context.

    Call once at application startup. Safe to call multiple times (idempotent).
    """
    global _configured
    if _configured:
        return

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _add_correlation_context,
    ]

    if redact:
        processors.append(_redact_pii)

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(asctime)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    _configured = True


def get_logger(name: str, **initial_bindings: Any) -> structlog.stdlib.BoundLogger:
    """Get a structured logger bound to the given module name.

    Automatically includes PII redaction and correlation context.
    """
    if not _configured:
        configure_logging()
    return structlog.get_logger(name, **initial_bindings)
