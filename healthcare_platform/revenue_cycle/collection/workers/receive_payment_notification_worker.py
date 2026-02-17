"""Worker: Receive payment notification from bank webhook."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.revenue_cycle.collection.enums import PaymentMethod
from healthcare_platform.revenue_cycle.collection.exceptions import PaymentValidationError

logger = get_logger(__name__)


class WebhookPayload(BaseModel):
    """    Bank webhook payment notification payload.
    
        Archetype: FINANCIAL_CALCULATION
        """

    transaction_id: str = Field(..., min_length=1)
    bank_code: str
    agency: str
    account: str
    amount: Decimal
    currency: str = "BRL"
    payment_date: str
    payer_name: str
    payer_document: str
    payment_method: str = "bank_transfer"
    signature: str = Field(..., description="HMAC signature for validation")


class ReceivePaymentNotificationWorker:
    """Receives bank webhook notification of incoming payment."""

    WORKER_TYPE = "receive_payment_notification"

    def __init__(self, webhook_secret: str = "") -> None:
        """Initialize worker with webhook secret for signature validation.

        Args:
            webhook_secret: Shared secret for HMAC validation. If not provided,
                          loads from WEBHOOK_SECRET or PAYMENT_WEBHOOK_SECRET
                          environment variable.

        Raises:
            ValueError: If webhook secret is not configured via parameter or
                       environment variable.
        """
        # Use provided secret, fallback to environment variables
        self.webhook_secret = webhook_secret or os.getenv(
            "WEBHOOK_SECRET"
        ) or os.getenv("PAYMENT_WEBHOOK_SECRET")

        if not self.webhook_secret:
            raise ValueError(
                "Webhook secret must be provided via constructor parameter "
                "or WEBHOOK_SECRET/PAYMENT_WEBHOOK_SECRET environment variable"
            )

        self.dmn_service = FederatedDMNService()
        self._logger = get_logger(__name__)

    def _evaluate_cash_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate cash_operations DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id='default',
                category='cash_operations',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    def _validate_signature(self, payload: str, signature: str) -> bool:
        """Validate webhook HMAC signature.

        Args:
            payload: Raw JSON payload string.
            signature: HMAC signature from webhook header.

        Returns:
            True if signature is valid.
        """
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @track_task_execution(metric_name="receive_payment_notification")
    async def execute(self, task_variables: dict) -> dict:
        """Execute payment notification reception.

        Args:
            task_variables: Contains 'webhook_payload' (JSON string) and 'signature'.

        Returns:
            Dict with parsed payment data for downstream workers.

        Raises:
            PaymentValidationError: If signature invalid or payload malformed.
        """
        raw_payload = task_variables.get("webhook_payload", "")
        signature = task_variables.get("signature", "")

        if not raw_payload or not signature:
            raise PaymentValidationError(
                _("Payload ou assinatura do webhook ausentes")
            )

        # Validate webhook signature
        if not self._validate_signature(raw_payload, signature):
            logger.warning("webhook_signature_invalid", signature=signature[:8])
            raise PaymentValidationError(_("Assinatura do webhook inválida"))

        # Parse and validate payload
        try:
            import json
            payload_dict = json.loads(raw_payload)
            payload = WebhookPayload(**payload_dict)
        except Exception as exc:
            logger.error("webhook_parse_failed", error=str(exc))
            raise PaymentValidationError(
                _("Falha ao parsear payload do webhook: {err}").format(err=str(exc))
            ) from exc

        # Map payment method
        payment_method = PaymentMethod.BANK_TRANSFER
        if payload.payment_method.lower() in ("pix", "boleto"):
            payment_method = PaymentMethod(payload.payment_method.lower())

        logger.info(
            "payment_notification_received",
            transaction_id=payload.transaction_id,
            amount=str(payload.amount),
            bank_code=payload.bank_code,
        )

        return {
            "transaction_id": payload.transaction_id,
            "bank_code": payload.bank_code,
            "agency": payload.agency,
            "account": payload.account,
            "gross_amount": str(payload.amount),
            "currency": payload.currency,
            "payment_date": payload.payment_date,
            "payer_name": payload.payer_name,
            "payer_document": payload.payer_document,
            "payment_method": payment_method.value,
            "received_at": datetime.utcnow().isoformat(),
            "source": "webhook",
        }
