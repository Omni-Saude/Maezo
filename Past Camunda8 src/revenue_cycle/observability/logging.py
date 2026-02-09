"""
Structured logging configuration using structlog.

Provides consistent logging across all workers with:
- JSON format for production (machine-parseable)
- Console format for development (human-readable)
- Automatic context binding (tenant, correlation ID)
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from typing import Any, Literal

import structlog
from structlog.stdlib import BoundLogger

from revenue_cycle.config import Settings, get_settings
from revenue_cycle.observability.redaction import RedactionProcessor


def configure_logging(
    settings: Settings | None = None,
    log_level: str | None = None,
    log_format: Literal["json", "console"] | None = None,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        settings: Application settings (uses get_settings() if not provided)
        log_level: Override log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Override log format (json, console)
    """
    settings = settings or get_settings()
    obs_settings = settings.observability

    level = log_level or obs_settings.log_level
    fmt = log_format or obs_settings.log_format

    # Set up standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    # Configure structlog processors
    # Redaction must be early in the chain to prevent credential leakage
    shared_processors: list[Any] = [
        RedactionProcessor(max_depth=10),
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if fmt == "json":
        # JSON format for production
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console format for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


@lru_cache
def get_logger(name: str | None = None) -> BoundLogger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


class LoggerMixin:
    """
    Mixin class to add logging capability to any class.

    Usage:
        class MyService(LoggerMixin):
            def do_something(self):
                self._logger.info("Doing something", key="value")
    """

    @property
    def _logger(self) -> BoundLogger:
        """Get a logger bound to this class."""
        return get_logger(self.__class__.__name__)
