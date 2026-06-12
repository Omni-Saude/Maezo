"""TASY Regulatory webhook handler (APAC, CNES, SUS) — ADR-014.

Receives async callbacks from TASY TIE when regulatory report
submissions complete, and correlates with CIB Seven BPM.
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
    TasyRegulatoryCallback,
)
from healthcare_platform.shared.webhooks.security.idempotency import IdempotencyManager
from healthcare_platform.shared.webhooks.security.signature_validator import (
    SignatureValidator,
)

logger = get_logger(__name__)

# Map report_type → BPM correlation message name
_REPORT_TYPE_MESSAGES: dict[str, str] = {
    "apac": "MSG_APAC_SUBMISSION_RESULT",
    "cnes": "MSG_CNES_SUBMISSION_RESULT",
    "sus": "MSG_SUS_SUBMISSION_RESULT",
}

_VALID_REPORT_TYPES = frozenset(_REPORT_TYPE_MESSAGES.keys())
_VALID_STATUSES = frozenset({"success", "error"})


class TasyRegulatoryHandler(BaseWebhookHandler):
    """Handles TASY TIE regulatory submission callbacks."""

    SYSTEM_NAME = "tasy_regulatory"

    def __init__(
        self,
        config: WebhookSettings,
        idempotency: IdempotencyManager,
        http_client: httpx.AsyncClient,
        signature_validator: SignatureValidator,
    ) -> None:
        super().__init__(config, idempotency, http_client)
        self.signature_validator = signature_validator

    async def handle(self, payload: TasyRegulatoryCallback) -> dict[str, Any]:  # type: ignore[override]
        """Correlate a regulatory callback with BPM."""
        report_type = payload.report_type.lower()
        message_name = _REPORT_TYPE_MESSAGES.get(report_type)
        if not message_name:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown report_type: {report_type}",
            )

        correlation_keys = {
            "encounter_id": payload.raw_metadata.get("nr_atendimento", ""),
            "submission_id": payload.submission_id,
        }

        variables: dict[str, Any] = {
            "status": str(payload.overall_status),
            "protocol_number": payload.protocol_number,
        }

        if payload.overall_status in ("approved", "pending_correction"):
            variables["approval_date"] = (
                payload.timestamp.isoformat() if payload.timestamp else ""
            )
        if payload.errors:
            variables["error_message"] = payload.errors[0].get("message", "")
            variables["error_code"] = payload.errors[0].get("code", "")

        result = await self.correlate_message(
            message_name=message_name,
            correlation_keys=correlation_keys,
            variables=variables,
            tenant_id=payload.tenant_id,
        )

        self._logger.info(
            "Regulatory callback correlated",
            report_type=report_type,
            submission_id=payload.submission_id,
            status=str(payload.overall_status),
        )

        return {"status": "correlated", "message_name": message_name, **result}

    async def handle_regulatory(
        self,
        request: Request,
        report_type: str,
        status: str,
    ) -> dict[str, Any]:
        """HTTP endpoint handler for /webhooks/tasy/regulatory/{report_type}/{status}."""
        if report_type not in _VALID_REPORT_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid report_type: {report_type}")
        if status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        body = await request.body()

        # Validate HMAC signature
        signature = request.headers.get("X-TASY-Signature", "")
        self.signature_validator.validate_hmac_sha256(
            body, signature, self._config.tasy_hmac_secret,
        )

        # Parse payload
        data = json.loads(body)
        data.setdefault("report_type", report_type)
        data.setdefault("idempotency_key", data.get("protocolo", ""))
        data.setdefault("tenant_id", getattr(request.state, "tenant_id", ""))
        payload = TasyRegulatoryCallback(**data)

        # Idempotency check
        cached = await self._idempotency.check(payload.idempotency_key)
        if cached is not None:
            return {"status": "duplicate", "original_result": cached}

        self._set_tenant_context(payload.tenant_id)

        result = await self.handle(payload)

        await self._idempotency.store(payload.idempotency_key, result)
        return result
