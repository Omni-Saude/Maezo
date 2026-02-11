"""Pydantic models for webhook callback payloads (ADR-014).

Each model represents an inbound callback from an external system.
Common fields: timestamp, idempotency_key, tenant_id.
No PII stored — only identifiers and status fields (LGPD compliance).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common base
# ---------------------------------------------------------------------------


class WebhookPayloadBase(BaseModel):
    """Fields common to all webhook callback payloads."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    idempotency_key: str = Field(..., min_length=1, max_length=256)
    tenant_id: str = Field(default="")
    source_system: str = Field(default="")
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# TASY Regulatory Callbacks (APAC, CNES, SUS)
# ---------------------------------------------------------------------------


class RegulatoryStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_CORRECTION = "pending_correction"
    ERROR = "error"


class RegulatoryResultItem(BaseModel):
    """Single item result within a regulatory callback."""

    code: str
    status: RegulatoryStatus
    message: str = ""
    protocol_number: str = ""


class TasyRegulatoryCallback(WebhookPayloadBase):
    """Callback from TASY TIE for regulatory submissions (APAC/CNES/SUS).

    Received when an async regulatory report submission completes.
    """

    source_system: str = "tasy_tie"
    report_type: str = Field(..., description="apac | cnes | sus | bpa")
    submission_id: str = Field(..., description="TASY submission reference")
    overall_status: RegulatoryStatus
    protocol_number: str = ""
    results: list[RegulatoryResultItem] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TASY Authorization Callbacks
# ---------------------------------------------------------------------------


class AuthorizationStatus(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    PARTIALLY_APPROVED = "partially_approved"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TasyAuthorizationCallback(WebhookPayloadBase):
    """Callback from TASY TIE for insurance authorization responses."""

    source_system: str = "tasy_tie"
    authorization_number: str = ""
    encounter_id: str = Field(..., description="Internal encounter reference")
    insurance_code: str = ""
    status: AuthorizationStatus
    approved_items: list[dict[str, Any]] = Field(default_factory=list)
    denied_items: list[dict[str, Any]] = Field(default_factory=list)
    denial_reason: str = ""
    valid_until: datetime | None = None


# ---------------------------------------------------------------------------
# PIX Payment Callbacks (Banco Central)
# ---------------------------------------------------------------------------


class PixEventType(StrEnum):
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_REFUNDED = "payment_refunded"
    PAYMENT_CANCELLED = "payment_cancelled"
    REFUND_REQUESTED = "refund_requested"


class PixPaymentCallback(WebhookPayloadBase):
    """Callback from Banco Central for PIX payment events."""

    source_system: str = "banco_central_pix"
    event_type: PixEventType
    end_to_end_id: str = Field(..., description="PIX E2E identifier")
    txid: str = ""
    amount_brl: float = Field(..., ge=0)
    payer_ispb: str = ""
    receiver_ispb: str = ""
    settlement_date: datetime | None = None


# ---------------------------------------------------------------------------
# WhatsApp Message Callbacks (Meta)
# ---------------------------------------------------------------------------


class WhatsAppEventType(StrEnum):
    MESSAGE_RECEIVED = "message_received"
    DELIVERY_RECEIPT = "delivery_receipt"
    READ_RECEIPT = "read_receipt"
    STATUS_UPDATE = "status_update"


class WhatsAppMessageCallback(WebhookPayloadBase):
    """Callback from Meta for WhatsApp Business API events."""

    source_system: str = "whatsapp_meta"
    event_type: WhatsAppEventType
    message_id: str = ""
    from_number_hash: str = Field(
        default="", description="SHA-256 hash of phone number (LGPD)"
    )
    message_type: str = ""  # text, image, document, etc.
    template_name: str = ""
    delivery_status: str = ""
    context_message_id: str = ""  # reply-to reference


# ---------------------------------------------------------------------------
# TISS Payer Callbacks (ANS)
# ---------------------------------------------------------------------------


class ClaimAdjudicationStatus(StrEnum):
    PAID = "paid"
    DENIED = "denied"
    PARTIALLY_PAID = "partially_paid"
    PENDING_REVIEW = "pending_review"
    RETURNED = "returned"


class TissPayerCallback(WebhookPayloadBase):
    """Callback from ANS/Payers for TISS claim adjudication results."""

    source_system: str = "tiss_payer"
    payer_id: str = Field(..., description="ANS payer registry number")
    claim_number: str = ""
    guide_number: str = Field(..., description="TISS guide number")
    batch_number: str = ""
    adjudication_status: ClaimAdjudicationStatus
    paid_amount_brl: float = Field(default=0.0, ge=0)
    denied_amount_brl: float = Field(default=0.0, ge=0)
    glosa_items: list[dict[str, Any]] = Field(default_factory=list)
    payment_date: datetime | None = None
