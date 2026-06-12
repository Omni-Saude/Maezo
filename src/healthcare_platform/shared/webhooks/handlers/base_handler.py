"""Abstract base handler for webhook callbacks (ADR-014).

Provides BPM correlation via CIB Seven REST API.
Concrete handlers implement handle() with zero business logic —
all decisions remain in BPMN/DMN.
"""

from __future__ import annotations

import abc
from typing import Any

import httpx

from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    set_current_tenant,
)
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.webhooks.config import WebhookSettings
from healthcare_platform.shared.webhooks.models.callback_payloads import WebhookPayloadBase
from healthcare_platform.shared.webhooks.security.idempotency import IdempotencyManager

logger = get_logger(__name__)


class WebhookProcessingError(Exception):
    """Raised when webhook processing fails after validation."""


class BaseWebhookHandler(abc.ABC):
    """Base class for all webhook handlers.

    Provides:
    - BPM message correlation via CIB7 REST API
    - Process instance start via CIB7 REST API
    - Structured logging with tenant context (no PII)
    - Idempotency checking
    """

    SYSTEM_NAME: str = "unknown"

    def __init__(
        self,
        config: WebhookSettings,
        idempotency: IdempotencyManager,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._config = config
        self._idempotency = idempotency
        self._http = http_client
        self._logger = get_logger(f"webhook.handler.{self.SYSTEM_NAME}")
        self._engine_url = config.cib7_engine_url.rstrip("/")

    async def correlate_message(
        self,
        message_name: str,
        correlation_keys: dict[str, Any],
        variables: dict[str, Any],
        *,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Send a correlation message to CIB Seven BPM engine.

        POST /engine-rest/message/{messageName}

        This wakes up a waiting receive-task or intermediate catch event
        in an active process instance.
        """
        url = f"{self._engine_url}/engine-rest/message/{message_name}"
        payload: dict[str, Any] = {
            "messageName": message_name,
            "correlationKeys": {
                k: {"value": v, "type": "String"} for k, v in correlation_keys.items()
            },
            "processVariables": {
                k: {"value": v, "type": _infer_camunda_type(v)}
                for k, v in variables.items()
            },
        }
        if tenant_id:
            payload["tenantId"] = tenant_id

        self._logger.info(
            "Correlating BPM message",
            message_name=message_name,
            correlation_keys=list(correlation_keys.keys()),
        )

        resp = await self._http.post(url, json=payload)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def start_process(
        self,
        process_key: str,
        variables: dict[str, Any],
        *,
        business_key: str = "",
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Start a new process instance in CIB Seven BPM engine.

        POST /engine-rest/process-definition/key/{key}/start
        """
        url = (
            f"{self._engine_url}/engine-rest/process-definition"
            f"/key/{process_key}/start"
        )
        payload: dict[str, Any] = {
            "variables": {
                k: {"value": v, "type": _infer_camunda_type(v)}
                for k, v in variables.items()
            },
        }
        if business_key:
            payload["businessKey"] = business_key
        if tenant_id:
            payload["tenantId"] = tenant_id

        self._logger.info(
            "Starting BPM process",
            process_key=process_key,
            business_key=business_key,
        )

        resp = await self._http.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def _set_tenant_context(self, tenant_id: str) -> None:
        """Set tenant context from webhook payload or default."""
        tid = tenant_id or self._config.default_tenant_id
        try:
            ctx = TenantContext.from_tenant_id(tid)
            set_current_tenant(ctx)
        except Exception:
            self._logger.warning("Unknown tenant in webhook", tenant_id=tid)

    @abc.abstractmethod
    async def handle(self, payload: WebhookPayloadBase) -> dict[str, Any]:
        """Process a validated webhook payload.

        Implementations must:
        1. Extract correlation keys from the payload
        2. Call correlate_message() or start_process()
        3. Return a response dict (stored for idempotency)

        Must NOT contain business logic — delegate to BPMN/DMN.
        """
        ...


def _infer_camunda_type(value: Any) -> str:
    """Map Python types to Camunda variable types."""
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Long"
    if isinstance(value, float):
        return "Double"
    if isinstance(value, dict):
        return "Json"
    return "String"
