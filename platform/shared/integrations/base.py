"""Base integration client with circuit breaker, retry, and tenant support.

All integration clients inherit from BaseIntegrationClient which provides:
- Circuit breaker pattern (CLOSED -> OPEN -> HALF_OPEN)
- Retry with exponential backoff via tenacity
- Multi-tenant credential resolution via TenantContext
- Structured logging (no PII) via platform.shared.observability.logging
- Prometheus metrics via @track_api_call
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from platform.shared.domain.exceptions import ExternalServiceException
from platform.shared.multi_tenant.context import TenantContext, get_current_tenant
from platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitState(enum.StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Prevents cascading failures to external services."""

    failure_threshold: int = 5
    timeout_seconds: float = 60.0
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.timeout_seconds:
                self._state = CircuitState.HALF_OPEN
        return self._state

    async def call(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        current = self.state
        if current == CircuitState.OPEN:
            raise ExternalServiceException(
                "Circuit breaker OPEN — service unavailable",
                service_name="circuit_breaker",
                operation="call",
            )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker OPENED",
                failure_count=self._failure_count,
                timeout_seconds=self.timeout_seconds,
            )


# ---------------------------------------------------------------------------
# Integration Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IntegrationSettings:
    """Common settings for integration clients."""

    base_url: str
    timeout_seconds: float = 30.0
    max_retries: int = 3
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0


# ---------------------------------------------------------------------------
# Base Client
# ---------------------------------------------------------------------------


class BaseIntegrationClient:
    """Abstract base for all integration clients.

    Provides httpx.AsyncClient lifecycle, circuit breaker, and tenant context.
    Subclasses implement service-specific methods.
    """

    SERVICE_NAME: str = "unknown"

    def __init__(self, settings: IntegrationSettings) -> None:
        self._settings = settings
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_threshold,
            timeout_seconds=settings.circuit_breaker_timeout,
        )
        self._client: httpx.AsyncClient | None = None
        self._logger = get_logger(f"integration.{self.SERVICE_NAME}")

    async def initialize(self) -> None:
        """Create HTTP client. Call before first use or use as async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self._settings.base_url,
            timeout=httpx.Timeout(self._settings.timeout_seconds),
            headers={"Content-Type": "application/json"},
        )
        self._logger.info("Client initialized", base_url=self._settings.base_url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> BaseIntegrationClient:
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                f"{self.SERVICE_NAME} client not initialized. "
                "Call initialize() or use as async context manager."
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        """Make HTTP request with circuit breaker and retry."""
        client = self._ensure_client()

        async def _do_request() -> httpx.Response:
            resp = await client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp

        try:
            return await self._circuit_breaker.call(_do_request)
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceException(
                f"{self.SERVICE_NAME} returned {exc.response.status_code}",
                service_name=self.SERVICE_NAME,
                operation=f"{method} {path}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ExternalServiceException(
                f"{self.SERVICE_NAME} timed out",
                service_name=self.SERVICE_NAME,
                operation=f"{method} {path}",
            ) from exc

    def _get_tenant_context(self) -> TenantContext:
        """Get current tenant or raise."""
        ctx = get_current_tenant()
        if ctx is None:
            raise ExternalServiceException(
                "Tenant context required",
                service_name=self.SERVICE_NAME,
                operation="get_tenant",
            )
        return ctx
