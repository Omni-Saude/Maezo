"""Domain entities for Revenue Collection subprocess."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from healthcare_platform.shared.domain.entities import DomainEntity
from healthcare_platform.shared.domain.value_objects import FHIRReference, Money
from healthcare_platform.revenue_cycle.collection.enums import (
    AgingBucket,
    AllocationStatus,
    CNABFormat,
    CollectionAction,
    CollectionPriority,
    DiscrepancyType,
    PaymentMethod,
    PaymentStatus,
    PaymentType,
    ReconciliationPeriod,
    ReconciliationStatus,
)


class Payment(DomainEntity):
    """A payment received from a payer (operadora/convênio)."""

    status: PaymentStatus = PaymentStatus.PENDING
    payment_type: PaymentType = PaymentType.FULL
    payment_method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    gross_amount: Money = Field(default_factory=lambda: Money.zero())
    net_amount: Money = Field(default_factory=lambda: Money.zero())
    fees: Money = Field(default_factory=lambda: Money.zero())
    payer_reference: FHIRReference | None = None
    bank_code: str = ""
    agency: str = ""
    account: str = ""
    transaction_id: str = ""
    cnab_format: CNABFormat | None = None
    cnab_line_number: int | None = None
    payment_date: date | None = None
    received_at: datetime | None = None
    source_file: str = ""
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    notes: str = ""


class PaymentAllocation(DomainEntity):
    """Maps a payment (or portion) to one or more claims."""

    payment_id: UUID = Field(...)
    claim_reference: FHIRReference = Field(...)
    allocated_amount: Money = Field(default_factory=lambda: Money.zero())
    expected_amount: Money = Field(default_factory=lambda: Money.zero())
    variance: Money = Field(default_factory=lambda: Money.zero())
    status: AllocationStatus = AllocationStatus.PENDING
    match_method: str = ""
    match_confidence: Decimal = Field(default=Decimal("0.0"))
    discrepancy_type: DiscrepancyType | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None


class Reconciliation(DomainEntity):
    """A reconciliation run for a given period."""

    period: ReconciliationPeriod = ReconciliationPeriod.DAILY
    period_start: date = Field(...)
    period_end: date = Field(...)
    status: ReconciliationStatus = ReconciliationStatus.OPEN
    total_expected: Money = Field(default_factory=lambda: Money.zero())
    total_received: Money = Field(default_factory=lambda: Money.zero())
    total_variance: Money = Field(default_factory=lambda: Money.zero())
    payment_count: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    closed_at: datetime | None = None
    closed_by: str | None = None
    archived_at: datetime | None = None


class CollectionCase(DomainEntity):
    """A collection case for overdue claims."""

    claim_reference: FHIRReference = Field(...)
    payer_reference: FHIRReference | None = None
    overdue_amount: Money = Field(default_factory=lambda: Money.zero())
    penalty_amount: Money = Field(default_factory=lambda: Money.zero())
    total_due: Money = Field(default_factory=lambda: Money.zero())
    aging_bucket: AgingBucket = AgingBucket.CURRENT
    priority: CollectionPriority = CollectionPriority.LOW
    priority_score: Decimal = Field(default=Decimal("0.0"))
    last_action: CollectionAction | None = None
    last_action_at: datetime | None = None
    next_action: CollectionAction | None = None
    next_action_at: datetime | None = None
    days_overdue: int = 0
    contact_attempts: int = 0
    escalated_to_legal: bool = False
    written_off: bool = False
    payment_plan_active: bool = False
    predicted_collection_date: date | None = None


class PaymentPlan(DomainEntity):
    """Negotiated installment payment plan."""

    collection_case_id: UUID = Field(...)
    payer_reference: FHIRReference | None = None
    total_amount: Money = Field(default_factory=lambda: Money.zero())
    installment_count: int = Field(default=1, ge=1)
    installment_amount: Money = Field(default_factory=lambda: Money.zero())
    first_due_date: date | None = None
    frequency_days: int = Field(default=30)
    paid_installments: int = 0
    active: bool = True
    negotiated_by: str = ""
    negotiated_at: datetime | None = None
