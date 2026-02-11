"""PIX Payment webhook handler — ADR-014.

Receives payment callbacks from Banco Central PIX system
and correlates with CIB Seven BPM.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
from fastapi import HTTPException, Request

from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.webhooks.config import WebhookSettings
from healthcare_platform.shared.webhooks.handlers.base_handler import BaseWebhookHandler
from healthcare_platform.shared.webhooks.models.callback_payloads import PixPaymentCallback
from healthcare_platform.shared.webhooks.security.idempotency import IdempotencyManager
from healthcare_platform.shared.webhooks.security.signature_validator import (
    SignatureValidator,
)

logger = get_logger(__name__)

_VALID_EVENTS = frozenset({"confirmed", "refunded", "cancelled"})

_EVENT_TO_MESSAGE: dict[str, str] = {
    "confirmed": "MSG_PAYMENT_RECEIVED",
    "refunded": "MSG_PAYMENT_REFUNDED",
    "cancelled": "MSG_PAYMENT_REFUNDED",
}

# Pattern to extract encounter_id from PIX endToEndId
# Convention: E{ispb}{date}{encounter_id_padded}
_E2E_ENCOUNTER_RE = re.compile(r"E\d{8}\d{8}(\w{1,20})")


def _mask_name(name: str) -> str:
    """Mask personal name for LGPD compliance."""
    if not name:
        return ""
    parts = name.split()
    return f"{parts[0]} ***" if parts else "***"


def _mask_document(doc: str) -> str:
    """Mask CPF/CNPJ for LGPD compliance."""
    if len(doc) == 11:
        return f"{doc[:3]}.***.***-{doc[-2:]}"
    if len(doc) == 14:
        return f"{doc[:2]}.***.***/****-{doc[-2:]}"
    return "***"


def _extract_encounter_from_e2e(end_to_end_id: str) -> str:
    """Extract encounter_id from PIX endToEndId convention."""
    m = _E2E_ENCOUNTER_RE.match(end_to_end_id)
    return m.group(1).lstrip("0") if m else ""


class PixPaymentHandler(BaseWebhookHandler):
    """Handles PIX payment callbacks from Banco Central."""

    SYSTEM_NAME = "pix_payment"

    def __init__(
        self,
        config: WebhookSettings,
        idempotency: IdempotencyManager,
        http_client: httpx.AsyncClient,
        signature_validator: SignatureValidator,
    ) -> None:
        super().__init__(config, idempotency, http_client)
        self.signature_validator = signature_validator

    async def handle(self, payload: PixPaymentCallback) -> dict[str, Any]:  # type: ignore[override]
        """Correlate a PIX payment callback with BPM."""
        encounter_id = _extract_encounter_from_e2e(payload.end_to_end_id)

        correlation_keys = {
            "encounter_id": encounter_id or payload.raw_metadata.get("encounter_id", ""),
            "payment_id": payload.txid,
        }

        payer_doc = payload.raw_metadata.get("payer_document", "")

        variables: dict[str, Any] = {
            "amount": payload.amount_brl,
            "payer_name": _mask_name(payload.raw_metadata.get("payer_name", "")),
            "payer_document": _mask_document(payer_doc),
            "payment_date": (
                payload.settlement_date.isoformat() if payload.settlement_date else ""
            ),
        }

        event = payload.raw_metadata.get("event", "confirmed")
        message_name = _EVENT_TO_MESSAGE.get(event, "MSG_PAYMENT_RECEIVED")

        if event in ("refunded", "cancelled"):
            variables["refund_reason"] = payload.raw_metadata.get("refund_reason", "")

        result = await self.correlate_message(
            message_name=message_name,
            correlation_keys=correlation_keys,
            variables=variables,
            tenant_id=payload.tenant_id,
        )

        self._logger.info(
            "PIX payment correlated",
            event=event,
            txid=payload.txid,
        )

        return {"status": "correlated", "message_name": message_name, **result}

    async def handle_payment(
        self,
        request: Request,
        event: str,
    ) -> dict[str, Any]:
        """HTTP endpoint handler for /webhooks/pix/payment/{event}."""
        if event not in _VALID_EVENTS:
            raise HTTPException(status_code=400, detail=f"Invalid event: {event}")

        body = await request.body()

        # Validate RSA signature (mTLS + RSA) — mandatory
        sig_header = request.headers.get("X-PIX-Signature", "")
        if not sig_header:
            raise HTTPException(status_code=401, detail="Missing signature")
        sig_bytes = base64.b64decode(sig_header)
        self.signature_validator.validate_rsa(
            body, sig_bytes, self._config.pix_cert_path,
        )

        data = json.loads(body)
        data.setdefault("event", event)
        data["raw_metadata"] = {**data.get("raw_metadata", {}), "event": event}
        data.setdefault("idempotency_key", data.get("txid", data.get("endToEndId", "")))
        data.setdefault("tenant_id", getattr(request.state, "tenant_id", ""))
        payload = PixPaymentCallback(**data)

        cached = await self._idempotency.check(payload.idempotency_key)
        if cached is not None:
            return {"status": "duplicate", "original_result": cached}

        self._set_tenant_context(payload.tenant_id)

        result = await self.handle(payload)

        await self._idempotency.store(payload.idempotency_key, result)
        return result
