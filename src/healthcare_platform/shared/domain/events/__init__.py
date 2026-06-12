"""Domain events for CDC (Change Data Capture) and event sourcing."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.enums import (
    AuthorizationStatus,
    BillingStatus,
    EncounterStatus,
    GlosaType,
    TenantCode,
)
from healthcare_platform.shared.domain.value_objects import FHIRReference, Money


class DomainEvent(BaseModel, frozen=True):
    """Base domain event for CDC pipeline."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(..., description="Fully qualified event name")
    tenant_id: TenantCode = Field(..., description="Hospital tenant")
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    aggregate_id: UUID = Field(..., description="ID of the aggregate root")
    aggregate_type: str = Field(..., description="Type of aggregate (e.g. Encounter)")
    correlation_id: UUID | None = Field(default=None, description="Process correlation")
    causation_id: UUID | None = Field(default=None, description="Causing event ID")
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Patient Events ──────────────────────────────────────────────────────


class PatientRegistered(DomainEvent):
    """Emitted when a patient is registered or updated in the platform."""

    event_type: str = "patient.registered"
    aggregate_type: str = "Patient"
    patient_reference: FHIRReference
    coverage_references: list[FHIRReference] = Field(default_factory=list)


# ── Encounter Events ────────────────────────────────────────────────────


class EncounterStarted(DomainEvent):
    """Emitted when a clinical encounter begins."""

    event_type: str = "encounter.started"
    aggregate_type: str = "Encounter"
    patient_reference: FHIRReference
    status: EncounterStatus = EncounterStatus.IN_PROGRESS
    business_key: str | None = None


class EncounterCompleted(DomainEvent):
    """Emitted when a clinical encounter is finished."""

    event_type: str = "encounter.completed"
    aggregate_type: str = "Encounter"
    patient_reference: FHIRReference
    status: EncounterStatus = EncounterStatus.FINISHED
    period_start: datetime | None = None
    period_end: datetime | None = None


# ── Billing Events ──────────────────────────────────────────────────────


class BillingCompleted(DomainEvent):
    """Emitted when billing/coding of an encounter is complete."""

    event_type: str = "billing.completed"
    aggregate_type: str = "Claim"
    claim_reference: FHIRReference
    encounter_reference: FHIRReference
    total_amount: Money
    billing_status: BillingStatus = BillingStatus.SUBMITTED
    item_count: int = 0
    tiss_guide_number: str | None = None


class ClaimSubmitted(DomainEvent):
    """Emitted when a claim is submitted to the payer."""

    event_type: str = "claim.submitted"
    aggregate_type: str = "Claim"
    claim_reference: FHIRReference
    coverage_reference: FHIRReference | None = None
    total_amount: Money
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class PaymentReceived(DomainEvent):
    """Emitted when payment is received from payer."""

    event_type: str = "payment.received"
    aggregate_type: str = "ClaimResponse"
    claim_reference: FHIRReference
    paid_amount: Money
    payment_date: datetime


# ── Glosa (Denial) Events ──────────────────────────────────────────────


class GlosaDetected(DomainEvent):
    """Emitted when a glosa (denial/disallowance) is detected in payer response."""

    event_type: str = "glosa.detected"
    aggregate_type: str = "ClaimResponse"
    claim_reference: FHIRReference
    glosa_type: GlosaType
    reason_code: str
    reason_display: str = ""
    denied_amount: Money
    original_amount: Money
    appealable: bool = True
    item_sequence: int | None = None


class GlosaAppealed(DomainEvent):
    """Emitted when a glosa appeal (recurso de glosa) is initiated."""

    event_type: str = "glosa.appealed"
    aggregate_type: str = "ClaimResponse"
    claim_reference: FHIRReference
    appeal_reason: str = ""
    appeal_deadline: datetime | None = None


# ── Authorization Events ───────────────────────────────────────────────


class AuthorizationRequested(DomainEvent):
    """Emitted when prior authorization is requested."""

    event_type: str = "authorization.requested"
    aggregate_type: str = "MedicationRequest"
    patient_reference: FHIRReference
    procedure_codes: list[str] = Field(default_factory=list)
    status: AuthorizationStatus = AuthorizationStatus.REQUESTED


class AuthorizationDecided(DomainEvent):
    """Emitted when authorization decision is received."""

    event_type: str = "authorization.decided"
    aggregate_type: str = "MedicationRequest"
    patient_reference: FHIRReference
    status: AuthorizationStatus
    decision_reason: str = ""
