"""TISS Payer Response webhook handler — ADR-014.

Receives claim adjudication callbacks from ANS/payers
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
from healthcare_platform.shared.webhooks.models.callback_payloads import TissPayerCallback
from healthcare_platform.shared.webhooks.security.idempotency import IdempotencyManager
from healthcare_platform.shared.webhooks.security.signature_validator import (
    SignatureValidator,
)

logger = get_logger(__name__)

_VALID_EVENTS = frozenset({"adjudicated", "partial", "rejected"})

_EVENT_TO_OUTCOME: dict[str, str] = {
    "adjudicated": "paid",
    "partial": "partially_paid",
    "rejected": "denied",
}


class TissResponseHandler(BaseWebhookHandler):
    """Handles TISS payer claim adjudication callbacks."""

    SYSTEM_NAME = "tiss_payer"

    def __init__(
        self,
        config: WebhookSettings,
        idempotency: IdempotencyManager,
        http_client: httpx.AsyncClient,
        signature_validator: SignatureValidator,
    ) -> None:
        super().__init__(config, idempotency, http_client)
        self.signature_validator = signature_validator

    async def handle(self, payload: TissPayerCallback) -> dict[str, Any]:  # type: ignore[override]
        """Correlate a TISS adjudication callback with BPM."""
        correlation_keys = {
            "claim_id": payload.guide_number,
            "encounter_id": payload.raw_metadata.get("encounter_id", ""),
        }

        denied_items = [
            item.get("code", "") for item in payload.glosa_items
        ]
        denial_codes = [
            item.get("glosa_code", "") for item in payload.glosa_items
        ]

        variables: dict[str, Any] = {
            "outcome": str(payload.adjudication_status),
            "paid_amount": payload.paid_amount_brl,
            "denied_items": json.dumps(denied_items),
            "denial_codes": json.dumps(denial_codes),
            "payment_date": (
                payload.payment_date.isoformat() if payload.payment_date else ""
            ),
        }

        result = await self.correlate_message(
            message_name="MSG_CLAIM_ADJUDICATED",
            correlation_keys=correlation_keys,
            variables=variables,
            tenant_id=payload.tenant_id,
        )

        self._logger.info(
            "TISS adjudication correlated",
            guide_number=payload.guide_number,
            outcome=str(payload.adjudication_status),
        )

        return {"status": "correlated", "message_name": "MSG_CLAIM_ADJUDICATED", **result}

    async def handle_tiss(
        self,
        request: Request,
        event: str,
    ) -> dict[str, Any]:
        """HTTP endpoint handler for /webhooks/payer/tiss/{event}."""
        if event not in _VALID_EVENTS:
            raise HTTPException(status_code=400, detail=f"Invalid event: {event}")

        # Validate API Key
        api_key = request.headers.get("X-ANS-API-Key", "")
        payer_id = self.signature_validator.validate_api_key(
            api_key, self._config.payer_api_keys,
        )

        body = await request.body()
        data = json.loads(body)
        data.setdefault("payer_id", payer_id)
        data.setdefault("idempotency_key", data.get("guide_number", data.get("nr_guia", "")))
        data.setdefault("tenant_id", getattr(request.state, "tenant_id", ""))
        data["raw_metadata"] = {
            **data.get("raw_metadata", {}),
            "encounter_id": data.get("encounter_id", data.get("nr_atendimento", "")),
        }
        payload = TissPayerCallback(**data)

        cached = await self._idempotency.check(payload.idempotency_key)
        if cached is not None:
            return {"status": "duplicate", "original_result": cached}

        self._set_tenant_context(payload.tenant_id)

        result = await self.handle(payload)

        await self._idempotency.store(payload.idempotency_key, result)
        return result
