"""FHIR R4 aligned domain entities with multi-tenancy support."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from platform.shared.domain.enums import (
    AuthorizationStatus,
    BillingStatus,
    ClaimStatus,
    ClaimUse,
    CoverageStatus,
    EncounterClass,
    EncounterStatus,
    GlosaType,
    TenantCode,
    TISSGuideType,
)
from platform.shared.domain.value_objects import (
    CodedValue,
    FHIRReference,
    InsuranceCard,
    Money,
)


class DomainEntity(BaseModel):
    """Base entity with tenant isolation and audit fields."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: TenantCode = Field(..., description="Hospital tenant identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=1, description="Optimistic locking version")
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── FHIR Patient (LGPD: reference-only, no PII stored) ──────────────────


class Patient(DomainEntity):
    """FHIR Patient reference. LGPD: only FHIR reference + hashed identifiers."""

    fhir_reference: FHIRReference
    active: bool = True
    coverage_references: list[FHIRReference] = Field(default_factory=list)


# ── FHIR Encounter ──────────────────────────────────────────────────────


class Encounter(DomainEntity):
    """FHIR Encounter - a clinical interaction / atendimento."""

    status: EncounterStatus = EncounterStatus.PLANNED
    encounter_class: EncounterClass = EncounterClass.AMBULATORY
    patient_reference: FHIRReference = Field(..., description="Reference to Patient")
    practitioner_references: list[FHIRReference] = Field(default_factory=list)
    location_reference: FHIRReference | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    reason_codes: list[CodedValue] = Field(default_factory=list, description="CID-10")
    diagnosis_codes: list[CodedValue] = Field(default_factory=list)
    service_type: CodedValue | None = None
    priority: CodedValue | None = None
    business_key: str | None = Field(default=None, description="CIB7 process key")


# ── FHIR Procedure ──────────────────────────────────────────────────────


class Procedure(DomainEntity):
    """FHIR Procedure - clinical procedure / procedimento."""

    status: str = "completed"
    code: CodedValue = Field(..., description="TUSS or CBHPM code")
    patient_reference: FHIRReference = Field(...)
    encounter_reference: FHIRReference = Field(...)
    performer_references: list[FHIRReference] = Field(default_factory=list)
    performed_start: datetime | None = None
    performed_end: datetime | None = None
    quantity: int = Field(default=1, ge=1)
    body_site: CodedValue | None = None
    notes: str = ""


# ── FHIR Coverage ───────────────────────────────────────────────────────


class Coverage(DomainEntity):
    """FHIR Coverage - insurance / convênio."""

    status: CoverageStatus = CoverageStatus.ACTIVE
    patient_reference: FHIRReference = Field(...)
    payor_reference: FHIRReference = Field(..., description="Insurance operator")
    insurance_card: InsuranceCard | None = None
    plan_name: str = ""
    period_start: date | None = None
    period_end: date | None = None
    ans_operator_code: str = Field(default="", description="ANS registry number")


# ── FHIR Claim ──────────────────────────────────────────────────────────


class ClaimItem(BaseModel):
    """Single line item in a Claim."""

    sequence: int = Field(..., ge=1)
    procedure_code: CodedValue
    quantity: int = Field(default=1, ge=1)
    unit_price: Money = Field(default_factory=lambda: Money.zero())
    total_price: Money = Field(default_factory=lambda: Money.zero())
    modifier_codes: list[CodedValue] = Field(default_factory=list)
    authorization_reference: str | None = None
    service_date: date | None = None


class Claim(DomainEntity):
    """FHIR Claim - billing claim / conta hospitalar."""

    status: ClaimStatus = ClaimStatus.DRAFT
    use: ClaimUse = ClaimUse.CLAIM
    billing_status: BillingStatus = BillingStatus.DRAFT
    patient_reference: FHIRReference = Field(...)
    encounter_reference: FHIRReference = Field(...)
    coverage_reference: FHIRReference | None = None
    provider_reference: FHIRReference | None = None
    items: list[ClaimItem] = Field(default_factory=list)
    total: Money = Field(default_factory=lambda: Money.zero())
    tiss_guide_type: TISSGuideType | None = None
    tiss_guide_number: str | None = None
    submitted_at: datetime | None = None
    created_from_encounter: bool = True


# ── FHIR ClaimResponse ─────────────────────────────────────────────────


class GlosaItem(BaseModel):
    """Single glosa (denial) line item in a ClaimResponse."""

    item_sequence: int = Field(..., ge=1)
    glosa_type: GlosaType
    reason_code: str
    reason_display: str = ""
    original_amount: Money = Field(default_factory=lambda: Money.zero())
    denied_amount: Money = Field(default_factory=lambda: Money.zero())
    appealable: bool = True


class ClaimResponse(DomainEntity):
    """FHIR ClaimResponse - payer's response / retorno da operadora."""

    claim_reference: FHIRReference = Field(...)
    status: str = "active"
    outcome: str = Field(default="queued", description="queued|complete|error|partial")
    approved_amount: Money = Field(default_factory=lambda: Money.zero())
    denied_amount: Money = Field(default_factory=lambda: Money.zero())
    paid_amount: Money = Field(default_factory=lambda: Money.zero())
    glosa_items: list[GlosaItem] = Field(default_factory=list)
    payment_date: date | None = None
    processing_notes: str = ""


# ── FHIR Practitioner ──────────────────────────────────────────────────


class Practitioner(DomainEntity):
    """FHIR Practitioner - healthcare professional (LGPD: reference only)."""

    fhir_reference: FHIRReference
    active: bool = True
    specialty_codes: list[CodedValue] = Field(default_factory=list)
    crm_state: str = Field(default="", description="CRM state code (e.g. SP, RJ)")
    council_type: str = Field(default="CRM", description="CRM, COREN, CRF, etc.")


# ── FHIR Location ──────────────────────────────────────────────────────


class Location(DomainEntity):
    """FHIR Location - physical place / local de atendimento."""

    name: str = Field(..., min_length=1)
    status: str = Field(default="active")
    mode: str = Field(default="instance", description="instance|kind")
    location_type: CodedValue | None = None
    cnes_code: str = Field(default="", description="CNES facility code")
    physical_type: str = Field(default="room", description="room|bed|wing|ward")


# ── FHIR MedicationRequest ─────────────────────────────────────────────


class MedicationRequest(DomainEntity):
    """FHIR MedicationRequest - prescription / prescrição médica."""

    status: str = Field(default="active")
    intent: str = Field(default="order")
    medication_code: CodedValue = Field(..., description="ANVISA or internal code")
    patient_reference: FHIRReference = Field(...)
    encounter_reference: FHIRReference = Field(...)
    requester_reference: FHIRReference | None = None
    dosage_text: str = ""
    quantity: Decimal = Field(default=Decimal("1"))
    unit: str = Field(default="unit")
    frequency: str = ""
    route: CodedValue | None = None
    authorized: bool = False
    authorization_status: AuthorizationStatus | None = None
