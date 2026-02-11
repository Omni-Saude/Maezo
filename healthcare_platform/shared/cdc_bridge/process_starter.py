"""Start or correlate CIB Seven process instances via REST API."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from healthcare_platform.shared.cdc_bridge.config import CIB7Settings, KeycloakSettings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 1.0  # seconds


class ProcessStarter:
    """Async client for CIB Seven engine REST API with OAuth2 token management."""

    def __init__(
        self, cib7: CIB7Settings, keycloak: KeycloakSettings
    ) -> None:
        self._cib7 = cib7
        self._keycloak = keycloak
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._cib7.engine_url, timeout=30.0
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def _ensure_token(self) -> str:
        """Obtain or refresh Keycloak access token."""
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token

        token_url = (
            f"{self._keycloak.url}/realms/{self._keycloak.realm}"
            f"/protocol/openid-connect/token"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._keycloak.client_id,
                    "client_secret": self._keycloak.client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 300)
            return self._token  # type: ignore[return-value]

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._ensure_token()
        return {"Authorization": f"Bearer {token}"}

    async def start_process(
        self,
        process_key: str,
        variables: dict[str, Any],
        business_key: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """Start a new process instance with exponential backoff retry."""
        url = (
            f"/engine-rest/process-definition/key/{process_key}"
            f"/tenant-id/{tenant_id}/start"
        )
        payload = {
            "businessKey": business_key,
            "variables": {
                k: {"value": v, "type": _camunda_type(v)}
                for k, v in variables.items()
            },
        }
        return await self._request_with_retry("POST", url, payload)

    async def correlate_message(
        self,
        message_name: str,
        correlation_keys: dict[str, Any],
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Correlate a message to a running process instance."""
        payload = {
            "messageName": message_name,
            "correlationKeys": {
                k: {"value": v, "type": _camunda_type(v)}
                for k, v in correlation_keys.items()
            },
            "processVariables": {
                k: {"value": v, "type": _camunda_type(v)}
                for k, v in variables.items()
            },
        }
        return await self._request_with_retry(
            "POST", "/engine-rest/message", payload
        )

    async def _request_with_retry(
        self, method: str, url: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._client is not None
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                headers = await self._auth_headers()
                resp = await self._client.request(
                    method, url, json=payload, headers=headers
                )
                resp.raise_for_status()
                return resp.json() if resp.content else {}
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                wait = BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "CIB7 request failed (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                    wait,
                )
                import asyncio
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"CIB7 request failed after {MAX_RETRIES} attempts"
        ) from last_exc


def _camunda_type(value: Any) -> str:
    """Map Python types to Camunda variable types."""
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Long"
    if isinstance(value, float):
        return "Double"
    return "String"
