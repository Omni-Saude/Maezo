"""Idempotency manager using PostgreSQL RDS (ADR-014, ADR-020).

Garante processamento at-most-once para callbacks de webhook.
Tabela: webhook_idempotency (system, idempotency_key, response_data, expires_at)

Criada pelo init-swarm.sql:
  CREATE TABLE webhook_idempotency (
    system          VARCHAR(50)  NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    response_data   JSONB,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    expires_at      TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (system, idempotency_key)
  );
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_TTL_DAYS = 7


class IdempotencyManager:
    """Tracks processed webhook events via PostgreSQL to prevent duplicates."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def check_and_store(
        self, system: str, idempotency_key: str, *, ttl_days: int = _DEFAULT_TTL_DAYS
    ) -> bool:
        """Check if event is new and mark it as seen.

        Returns:
            True if the event is **new** (first time seen).
            False if it was already processed (duplicate).
        """
        async with self._pool.acquire() as conn:
            result = await conn.fetchval(
                """
                INSERT INTO webhook_idempotency(system, idempotency_key, expires_at)
                VALUES ($1, $2, NOW() + ($3 || ' days')::interval)
                ON CONFLICT (system, idempotency_key) DO NOTHING
                RETURNING TRUE
                """,
                system,
                idempotency_key,
                str(ttl_days),
            )
        if result is None:
            logger.info("Duplicate webhook ignored", system=system, key=idempotency_key)
            return False
        return True

    async def get_cached_response(
        self, system: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        """Retrieve cached response for a previously processed event."""
        async with self._pool.acquire() as conn:
            raw = await conn.fetchval(
                """
                SELECT response_data
                FROM webhook_idempotency
                WHERE system = $1 AND idempotency_key = $2 AND expires_at > NOW()
                """,
                system,
                idempotency_key,
            )
        if raw is None:
            return None
        return json.loads(raw) if isinstance(raw, str) else raw

    async def store_response(
        self,
        system: str,
        idempotency_key: str,
        response: dict[str, Any],
        *,
        ttl_days: int = _DEFAULT_TTL_DAYS,
    ) -> None:
        """Store the final response for an idempotency key."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE webhook_idempotency
                SET response_data = $3
                WHERE system = $1 AND idempotency_key = $2
                """,
                system,
                idempotency_key,
                json.dumps(response),
            )
