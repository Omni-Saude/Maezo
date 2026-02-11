"""Idempotency manager using Redis (ADR-014).

Ensures at-most-once processing for webhook callbacks.
Key format: webhook:{system}:{idempotency_key}
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_TTL_DAYS = 7
_SECONDS_PER_DAY = 86_400


class IdempotencyManager:
    """Tracks processed webhook events via Redis to prevent duplicates."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    @staticmethod
    def _make_key(system: str, idempotency_key: str) -> str:
        return f"webhook:{system}:{idempotency_key}"

    async def check_and_store(
        self, system: str, idempotency_key: str, *, ttl_days: int = _DEFAULT_TTL_DAYS
    ) -> bool:
        """Check if event is new and mark it as seen.

        Returns:
            True if the event is **new** (first time seen).
            False if it was already processed (duplicate).
        """
        key = self._make_key(system, idempotency_key)
        was_set = await self._redis.set(
            key, "processing", ex=ttl_days * _SECONDS_PER_DAY, nx=True
        )
        if not was_set:
            logger.info("Duplicate webhook ignored", key=key)
            return False
        return True

    async def get_cached_response(
        self, system: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        """Retrieve cached response for a previously processed event."""
        key = self._make_key(system, idempotency_key)
        raw = await self._redis.get(key)
        if raw is None or raw == b"processing":
            return None
        return json.loads(raw)

    async def store_response(
        self,
        system: str,
        idempotency_key: str,
        response: dict[str, Any],
        *,
        ttl_days: int = _DEFAULT_TTL_DAYS,
    ) -> None:
        """Store the final response for an idempotency key."""
        key = self._make_key(system, idempotency_key)
        await self._redis.set(
            key, json.dumps(response), ex=ttl_days * _SECONDS_PER_DAY
        )
