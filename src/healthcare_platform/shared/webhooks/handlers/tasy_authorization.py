"""TASY Authorization webhook handler — ADR-014.

Receives insurance authorization responses from TASY TIE
and correlates with CIB Seven BPM.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import HTTPException, Request

from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.webhooks.config import WebhookSettings
from healthcare_platform.shared.webhooks.handlers.base_handler import BaseWebhookHandler
from healthcare_platform.shared.webhooks.models.callback_payloads import (
    TasyAuthorizationCallback,
)
from healthcare_platform.shared.webhooks.security.idempotency import IdempotencyManager
from healthcare_platform.shared.webhooks.security.signature_validator import (
    SignatureValidator,
)

logger = get_logger(__name__)

_VALID_STATUSES = frozenset({"approved", "denied", "pending_documentation"})


class TasyAuthorizationHandler(BaseWebhookHandler):
    """Handles TASY TIE authorization response callbacks."""

    SYSTEM_NAME = "tasy_authorization"

    def __init__(
        self,
        config: WebhookSettings,
        idempotency: IdempotencyManager,
        http_client: httpx.AsyncClient,
        signature_validator: SignatureValidator,
    ) -> None:
        super().__init__(config, idempotency, http_client)
        self.signature_validator = signature_validator

    async def handle(self, payload: TasyAuthorizationCallback) -> dict[str, Any]:  # type: ignore[override]
        """Correlate an authorization callback with BPM."""
        correlation_keys = {
            "encounter_id": payload.encounter_id,
            "authorization_request_id": payload.raw_metadata.get(
                "authorization_request_id", payload.authorization_number
            ),
        }

        approved_procedures = [
            item.get("procedure_code", "") for item in payload.approved_items
        ]

        variables: dict[str, Any] = {
            "auth_status": str(payload.status),
            "auth_code": payload.authorization_number,
            "denial_reason": payload.denial_reason,
            "expiration_date": (
                payload.valid_until.isoformat() if payload.valid_until else ""
            ),
            "approved_procedures": json.dumps(approved_procedures),
        }

        result = await self.correlate_message(
            message_name="MSG_AUTHORIZATION_RESPONSE",
            correlation_keys=correlation_keys,
            variables=variables,
            tenant_id=payload.tenant_id,
        )

        self._logger.info(
            "Authorization callback correlated",
            encounter_id=payload.encounter_id,
            auth_status=str(payload.status),
        )

        return {"status": "correlated", "message_name": "MSG_AUTHORIZATION_RESPONSE", **result}

    async def handle_authorization(
        self,
        request: Request,
        status: str,
    ) -> dict[str, Any]:
        """HTTP endpoint handler for /webhooks/tasy/authorization/{status}."""
        if status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        body = await request.body()

        # Validate HMAC signature
        signature = request.headers.get("X-TASY-Signature", "")
        self.signature_validator.validate_hmac_sha256(
            body, signature, self._config.tasy_hmac_secret,
        )

        data = json.loads(body)
        data.setdefault("idempotency_key", data.get("authorization_number", ""))
        data.setdefault("tenant_id", getattr(request.state, "tenant_id", ""))
        payload = TasyAuthorizationCallback(**data)

        cached = await self._idempotency.check(payload.idempotency_key)
        if cached is not None:
            return {"status": "duplicate", "original_result": cached}

        self._set_tenant_context(payload.tenant_id)

        result = await self.handle(payload)

        await self._idempotency.store(payload.idempotency_key, result)
        return result
