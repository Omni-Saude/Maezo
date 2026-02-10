"""Enums for Revenue Collection subprocess."""
from __future__ import annotations

from enum import StrEnum, unique


@unique
class PaymentStatus(StrEnum):
    PENDING = "pending"
    RECEIVED = "received"
    VALIDATED = "validated"
    ALLOCATED = "allocated"
    PARTIALLY_ALLOCATED = "partially_allocated"
    RECONCILED = "reconciled"
    REJECTED = "rejected"
    REVERSED = "reversed"


@unique
class PaymentType(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    ADVANCE = "advance"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


@unique
class PaymentMethod(StrEnum):
    BANK_TRANSFER = "bank_transfer"
    BOLETO = "boleto"
    PIX = "pix"
    DEPOSIT = "deposit"
    CHECK = "check"
    CREDIT_CARD = "credit_card"


@unique
class AllocationStatus(StrEnum):
    PENDING = "pending"
    AUTO_MATCHED = "auto_matched"
    MANUAL_MATCHED = "manual_matched"
    PARTIALLY_ALLOCATED = "partially_allocated"
    FULLY_ALLOCATED = "fully_allocated"
    UNMATCHED = "unmatched"
    ESCALATED = "escalated"
    LOCKED = "locked"


@unique
class ReconciliationPeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@unique
class ReconciliationStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BALANCED = "balanced"
    UNBALANCED = "unbalanced"
    CLOSED = "closed"
    ARCHIVED = "archived"


class AgingBucket(StrEnum):
    """Aging buckets for overdue accounts (allows aliases)."""
    CURRENT = "current"
    DAYS_0_30 = "0_30_days"
    DAYS_31_60 = "31_60_days"
    DAYS_61_90 = "61_90_days"
    DAYS_91_120 = "91_120_days"
    DAYS_121_180 = "121_180_days"
    DAYS_180_PLUS = "180_plus_days"
    # Legacy aliases for compatibility (not @unique to allow duplicates)
    DAYS_30 = "0_30_days"
    DAYS_60 = "31_60_days"
    DAYS_90 = "61_90_days"
    DAYS_120 = "91_120_days"
    DAYS_180 = "121_180_days"
    OVER_180 = "180_plus_days"


@unique
class CollectionPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@unique
class CollectionStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PAYMENT_PLAN = "payment_plan"
    LEGAL = "legal"
    WRITTEN_OFF = "written_off"
    COLLECTED = "collected"


@unique
class CollectionAction(StrEnum):
    LETTER_FIRST = "letter_first"
    LETTER_SECOND = "letter_second"
    LETTER_FINAL = "letter_final"
    WHATSAPP_REMINDER = "whatsapp_reminder"
    PHONE_CALL = "phone_call"
    PAYMENT_PLAN = "payment_plan"
    PENALTY_APPLIED = "penalty_applied"
    LEGAL_ESCALATION = "legal_escalation"
    WRITE_OFF = "write_off"


@unique
class DiscrepancyType(StrEnum):
    OVERPAYMENT = "overpayment"
    UNDERPAYMENT = "underpayment"
    DUPLICATE_PAYMENT = "duplicate_payment"
    WRONG_CLAIM = "wrong_claim"
    CONTRACTUAL_ADJUSTMENT = "contractual_adjustment"
    UNMATCHED = "unmatched"


@unique
class CNABFormat(StrEnum):
    CNAB_240 = "cnab_240"
    CNAB_400 = "cnab_400"
