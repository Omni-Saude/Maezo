"""FHIR writer with retry and error classification.

Wraps FHIRClient to provide conditional upsert and bundle execution
with exponential backoff for transient failures.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.fhir_sync.config import FHIRSettings
from healthcare_platform.shared.integrations.fhir_client import FHIRClient

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 1.0


def _is_retryable(exc: Exception) -> bool:
    """Classify whether an exception is transient (retryable)."""
    if isinstance(exc, ExternalServiceException):
        status = getattr(exc, "status_code", None)
        if status is not None and status < 500 and status != 429:
            return False  # 4xx (except 429) are permanent
        return True  # 5xx, 429, or no status code
    # TypeError from broken error handling is not retryable
    if isinstance(exc, TypeError):
        return False
    return True  # network errors are retryable


class FHIRWriter:
    """Writes FHIR resources with retry logic."""

    def __init__(self, fhir_settings: FHIRSettings) -> None:
        self._client: FHIRClient | None = None
        self._settings = fhir_settings

    async def start(self) -> None:
        self._client = FHIRClient(
            base_url=self._settings.base_url,
            timeout=self._settings.timeout,
            max_retries=self._settings.max_retries,
            api_key=self._settings.api_key,
        )

    async def close(self) -> None:
        self._client = None

    async def conditional_update(
        self,
        resource_type: str,
        resource: dict[str, Any],
        identifier_system: str,
        identifier_value: str,
    ) -> dict[str, Any]:
        """Upsert a FHIR resource with retry on transient failures."""
        assert self._client is not None
        return await self._with_retry(
            self._client.conditional_update,
            resource_type, resource, identifier_system, identifier_value,
        )

    async def execute_bundle(
        self, entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute a transaction bundle with retry on transient failures."""
        assert self._client is not None
        return await self._with_retry(self._client.execute_bundle, entries)

    async def _with_retry(self, fn, *args: Any) -> Any:
        """Call fn with exponential backoff on transient errors."""
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                return await fn(*args)
            except Exception as exc:
                last_exc = exc
                if not _is_retryable(exc) or attempt == MAX_RETRIES - 1:
                    raise
                wait = BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "FHIR write failed (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1, MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"FHIR write failed after {MAX_RETRIES} attempts"
        ) from last_exc
