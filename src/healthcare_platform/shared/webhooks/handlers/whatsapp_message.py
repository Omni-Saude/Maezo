"""WhatsApp Message webhook handler — ADR-014.

Receives inbound messages and status updates from Meta WhatsApp
Business API and correlates with CIB Seven BPM.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
from fastapi import HTTPException, Query, Request, Response

from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.webhooks.config import WebhookSettings
from healthcare_platform.shared.webhooks.handlers.base_handler import BaseWebhookHandler
from healthcare_platform.shared.webhooks.models.callback_payloads import (
    WhatsAppEventType,
    WhatsAppMessageCallback,
)
from healthcare_platform.shared.webhooks.security.idempotency import IdempotencyManager
from healthcare_platform.shared.webhooks.security.signature_validator import (
    SignatureValidator,
)

logger = get_logger(__name__)


def _hash_phone(phone: str) -> str:
    """SHA-256 hash a phone number for LGPD compliance."""
    return hashlib.sha256(phone.encode()).hexdigest()



class WhatsAppMessageHandler(BaseWebhookHandler):
    """Handles WhatsApp Business API callbacks from Meta."""

    SYSTEM_NAME = "whatsapp"

    def __init__(
        self,
        config: WebhookSettings,
        idempotency: IdempotencyManager,
        http_client: httpx.AsyncClient,
        signature_validator: SignatureValidator,
    ) -> None:
        super().__init__(config, idempotency, http_client)
        self.signature_validator = signature_validator

    async def handle(self, payload: WhatsAppMessageCallback) -> dict[str, Any]:  # type: ignore[override]
        """Correlate a WhatsApp callback with BPM."""
        meta = payload.raw_metadata

        correlation_keys = {
            "patient_phone": payload.from_number_hash,
            "conversation_id": meta.get("conversation_id", payload.context_message_id),
        }

        if payload.event_type in (
            WhatsAppEventType.DELIVERY_RECEIPT,
            WhatsAppEventType.READ_RECEIPT,
            WhatsAppEventType.STATUS_UPDATE,
        ):
            message_name = "MSG_WHATSAPP_STATUS"
            variables: dict[str, Any] = {
                "status": payload.delivery_status or str(payload.event_type),
                "timestamp": payload.timestamp.isoformat(),
            }
        else:
            message_name = "MSG_WHATSAPP_INBOUND"
            variables = {
                "message_type": payload.message_type,
                "message_text": meta.get("message_text", ""),
                "button_id": meta.get("button_id", ""),
                "timestamp": payload.timestamp.isoformat(),
                "status": "received",
            }

        result = await self.correlate_message(
            message_name=message_name,
            correlation_keys=correlation_keys,
            variables=variables,
            tenant_id=payload.tenant_id,
        )

        self._logger.info(
            "WhatsApp callback correlated",
            event_type=str(payload.event_type),
            message_type=payload.message_type,
            phone_hash=meta.get("wa_id_hash", "")[:8],
        )

        return {"status": "correlated", "message_name": message_name, **result}

    async def handle_verification(
        self,
        hub_mode: str = Query("", alias="hub.mode"),
        hub_verify_token: str = Query("", alias="hub.verify_token"),
        hub_challenge: str = Query("", alias="hub.challenge"),
    ) -> Response:
        """GET /webhooks/whatsapp/message — Meta verification challenge."""
        if hub_mode == "subscribe" and hmac.compare_digest(hub_verify_token, self._config.whatsapp_verify_token):
            return Response(content=hub_challenge, media_type="text/plain")
        raise HTTPException(status_code=403, detail="Verification failed")

    async def handle_message(self, request: Request) -> dict[str, Any]:
        """POST /webhooks/whatsapp/message — inbound messages and statuses."""
        body = await request.body()

        # Validate X-Hub-Signature-256
        signature = request.headers.get("X-Hub-Signature-256", "")
        self.signature_validator.validate_hmac_sha256(
            body, signature, self._config.whatsapp_app_secret,
        )

        data = json.loads(body)

        results = []
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Handle status updates
                for status_obj in value.get("statuses", []):
                    payload = WhatsAppMessageCallback(
                        idempotency_key=status_obj.get("id", ""),
                        event_type=WhatsAppEventType.STATUS_UPDATE,
                        message_id=status_obj.get("id", ""),
                        delivery_status=status_obj.get("status", ""),
                        from_number_hash=_hash_phone(
                            status_obj.get("recipient_id", "")
                        ),
                        tenant_id=getattr(request.state, "tenant_id", ""),
                        raw_metadata={
                            "conversation_id": status_obj.get("conversation", {}).get("id", ""),
                            "wa_id_hash": _hash_phone(status_obj.get("recipient_id", "")),
                        },
                    )
                    cached = await self._idempotency.check(payload.idempotency_key)
                    if cached is not None:
                        results.append(cached)
                        continue
                    self._set_tenant_context(payload.tenant_id)
                    r = await self.handle(payload)
                    await self._idempotency.store(payload.idempotency_key, r)
                    results.append(r)

                # Handle inbound messages
                for msg in value.get("messages", []):
                    wa_id = msg.get("from", "")
                    msg_type = msg.get("type", "text")

                    raw_meta: dict[str, Any] = {
                        "wa_id_hash": _hash_phone(wa_id),
                        "conversation_id": msg.get("context", {}).get("id", ""),
                    }

                    if msg_type == "text":
                        raw_meta["message_text"] = msg.get("text", {}).get("body", "")
                    elif msg_type == "interactive":
                        interactive = msg.get("interactive", {})
                        itype = interactive.get("type", "")
                        if itype == "button_reply":
                            raw_meta["button_id"] = interactive.get("button_reply", {}).get("id", "")
                            raw_meta["message_text"] = interactive.get("button_reply", {}).get("title", "")
                        elif itype == "list_reply":
                            raw_meta["button_id"] = interactive.get("list_reply", {}).get("id", "")
                            raw_meta["message_text"] = interactive.get("list_reply", {}).get("title", "")

                    payload = WhatsAppMessageCallback(
                        idempotency_key=msg.get("id", ""),
                        event_type=WhatsAppEventType.MESSAGE_RECEIVED,
                        message_id=msg.get("id", ""),
                        from_number_hash=_hash_phone(wa_id),
                        message_type=msg_type,
                        context_message_id=msg.get("context", {}).get("message_id", ""),
                        tenant_id=getattr(request.state, "tenant_id", ""),
                        raw_metadata=raw_meta,
                    )

                    cached = await self._idempotency.check(payload.idempotency_key)
                    if cached is not None:
                        results.append(cached)
                        continue
                    self._set_tenant_context(payload.tenant_id)
                    r = await self.handle(payload)
                    await self._idempotency.store(payload.idempotency_key, r)
                    results.append(r)

        return {"status": "processed", "count": len(results)}
