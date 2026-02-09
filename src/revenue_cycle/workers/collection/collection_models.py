"""
Pydantic models for collection workers input/output validation.

These models provide type-safe validation for debt collection operations,
agency referrals, and collection-related Camunda process variables.

Follows Brazilian debt collection regulations (CDC - Código de Defesa do Consumidor).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CollectionStrategy(str, Enum):
    """
    Collection strategies for debt recovery, ordered by intensity (lexicographically).

    Values use numeric prefixes so string comparison works correctly:
    - "1_SOFT" < "2_MEDIUM" < "3_AGGRESSIVE" < "4_LEGAL" (by ASCII/lexicographic order)
    - Intensity order: SOFT (1) < MEDIUM (2) < AGGRESSIVE (3) < LEGAL (4)

    Attributes:
        SOFT: Soft collection approach (low intensity)
        MEDIUM: Medium collection approach
        AGGRESSIVE: Aggressive collection approach
        LEGAL: Legal action/court proceedings
        INTERNAL: Internal collection by hospital staff (alias for SOFT)
        AGENCY_REFERRAL: External collection agency (alias for AGGRESSIVE)
        NEGOTIATION: Payment plan negotiation
        WRITE_OFF: Write off as bad debt
    """

    SOFT = "1_SOFT"
    MEDIUM = "2_MEDIUM"
    AGGRESSIVE = "3_AGGRESSIVE"
    LEGAL = "4_LEGAL"
    INTERNAL = "1_SOFT"
    AGENCY_REFERRAL = "3_AGGRESSIVE"
    NEGOTIATION = "2_MEDIUM"
    WRITE_OFF = "1_SOFT"

    def __lt__(self, other):
        """Compare strategies by intensity. String comparison works with numeric prefixes."""
        if isinstance(other, CollectionStrategy):
            # Direct string comparison: "1_SOFT" < "2_MEDIUM" < "3_AGGRESSIVE" < "4_LEGAL"
            return self.value < other.value
        return False

    def __le__(self, other):
        """Compare strategies by intensity. String comparison works with numeric prefixes."""
        if isinstance(other, CollectionStrategy):
            return self.value <= other.value
        return False

    def __gt__(self, other):
        """Compare strategies by intensity. String comparison works with numeric prefixes."""
        if isinstance(other, CollectionStrategy):
            return self.value > other.value
        return False

    def __ge__(self, other):
        """Compare strategies by intensity. String comparison works with numeric prefixes."""
        if isinstance(other, CollectionStrategy):
            return self.value >= other.value
        return False


class CollectionStatus(str, Enum):
    """
    Status of a collection case.

    Attributes:
        INITIATED: Collection case created
        IN_PROGRESS: Active collection efforts
        REFERRED: Referred to external agency
        ESCALATED: Escalated to legal action
        RESOLVED: Debt collected
        SETTLED: Partial settlement accepted
        WRITTEN_OFF: Bad debt write-off
        SUSPENDED: Collection suspended
    """

    INITIATED = "INITIATED"
    IN_PROGRESS = "IN_PROGRESS"
    REFERRED = "REFERRED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    SETTLED = "SETTLED"
    WRITTEN_OFF = "WRITTEN_OFF"
    SUSPENDED = "SUSPENDED"


class AgingBucket(str, Enum):
    """
    Aging buckets for debt aging analysis.

    Represents time periods since a debt became due.

    Attributes:
        DAYS_0_30: 0-30 days overdue
        DAYS_31_60: 31-60 days overdue
        DAYS_61_90: 61-90 days overdue
        DAYS_91_120: 91-120 days overdue
        DAYS_120_PLUS: 120+ days overdue
    """

    DAYS_0_30 = "0-30"
    DAYS_31_60 = "31-60"
    DAYS_61_90 = "61-90"
    DAYS_91_120 = "91-120"
    DAYS_120_PLUS = "120+"


class ContactMethod(str, Enum):
    """
    Methods for contacting debtor.

    Attributes:
        PHONE: Phone call
        SMS: Text message
        EMAIL: Email notification
        LETTER: Postal mail
        WHATSAPP: WhatsApp message
        IN_PERSON: In-person visit
    """

    PHONE = "PHONE"
    SMS = "SMS"
    EMAIL = "EMAIL"
    LETTER = "LETTER"
    WHATSAPP = "WHATSAPP"
    IN_PERSON = "IN_PERSON"


class PriorCollectionAttempt(BaseModel):
    """
    Record of a prior collection attempt.

    Tracks history of collection efforts for decision-making.
    """

    attempt_date: datetime = Field(
        ...,
        alias="attemptDate",
        description="Date of collection attempt",
    )
    contact_method: ContactMethod = Field(
        ...,
        alias="contactMethod",
        description="Method used for contact",
    )
    contacted: bool = Field(
        ...,
        description="Whether contact was successful",
    )
    payment_promised: bool = Field(
        False,
        alias="paymentPromised",
        description="Whether payment was promised",
    )
    promise_date: Optional[datetime] = Field(
        None,
        alias="promiseDate",
        description="Date payment was promised",
    )
    notes: Optional[str] = Field(
        None,
        max_length=500,
        description="Notes about the attempt",
    )

    model_config = {
        "populate_by_name": True,
    }


class ScheduledContact(BaseModel):
    """
    A scheduled contact in the communication plan.

    Defines when and how to contact the debtor.
    """

    scheduled_date: datetime = Field(
        ...,
        alias="scheduledDate",
        description="When to make contact",
    )
    contact_method: ContactMethod = Field(
        ...,
        alias="contactMethod",
        description="Method of contact",
    )
    priority: str = Field(
        ...,
        description="Priority level (HIGH/MEDIUM/LOW)",
    )
    message_template: Optional[str] = Field(
        None,
        alias="messageTemplate",
        description="Template to use for message",
    )

    model_config = {
        "populate_by_name": True,
    }


class InitiateCollectionInput(BaseModel):
    """
    Input model for InitiateCollectionWorker.

    Validates all required fields for initiating debt collection.
    Supports both field naming conventions for compatibility.
    """

    claim_id: str = Field(
        ...,
        alias="claimId",
        min_length=1,
        description="Associated claim identifier",
    )
    patient_id: str = Field(
        ...,
        alias="patientId",
        min_length=1,
        description="Patient identifier",
    )
    # Support both debtAmount and outstandingBalance field names
    debt_amount: Optional[Decimal] = Field(
        None,
        alias="debtAmount",
        gt=0,
        description="Outstanding debt amount",
    )
    outstanding_balance: Optional[Decimal] = Field(
        None,
        alias="outstandingBalance",
        gt=0,
        description="Outstanding balance (alternative field name)",
    )
    # Support both daysPastDue and dueDate
    days_past_due: Optional[int] = Field(
        None,
        alias="daysPastDue",
        ge=0,
        description="Number of days payment is overdue",
    )
    due_date: Optional[datetime] = Field(
        None,
        alias="dueDate",
        description="Due date of the claim",
    )
    collection_strategy: Optional[CollectionStrategy] = Field(
        None,
        alias="collectionStrategy",
        description="Preferred collection strategy (if specified)",
    )

    # Optional fields
    previous_attempts: Optional[list[PriorCollectionAttempt]] = Field(
        None,
        alias="previousAttempts",
        description="History of prior collection attempts",
    )
    patient_name: Optional[str] = Field(
        None,
        alias="patientName",
        description="Patient name for communications",
    )
    patient_phone: Optional[str] = Field(
        None,
        alias="patientPhone",
        description="Patient contact phone",
    )
    patient_email: Optional[str] = Field(
        None,
        alias="patientEmail",
        description="Patient contact email",
    )
    payer_name: Optional[str] = Field(
        None,
        alias="payerName",
        description="Original payer name",
    )
    original_claim_amount: Optional[Decimal] = Field(
        None,
        alias="originalClaimAmount",
        description="Original claim amount",
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Additional collection notes",
    )

    # Multi-tenant support
    tenant_id: Optional[str] = Field(
        None,
        alias="tenantId",
        description="Tenant identifier",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data: Any) -> Any:
        """Normalize alternative field names before validation."""
        if isinstance(data, dict):
            # Map daysOverdue to daysPastDue if present and daysPastDue not set
            if "daysOverdue" in data and "daysPastDue" not in data:
                data["daysPastDue"] = data.pop("daysOverdue")
        return data

    @field_validator("debt_amount", "outstanding_balance", "original_claim_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Optional[Decimal]:
        """Parse various numeric types to Decimal."""
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    @field_validator("previous_attempts", mode="before")
    @classmethod
    def parse_attempts(cls, v: Any) -> Optional[list[PriorCollectionAttempt]]:
        """Parse list of prior attempts."""
        if v is None:
            return None
        if isinstance(v, list):
            return [
                PriorCollectionAttempt(**item) if isinstance(item, dict) else item
                for item in v
            ]
        return None

    @model_validator(mode="after")
    def consolidate_fields(self):
        """Consolidate alternative field names into primary fields."""
        # Use outstanding_balance if debtAmount not provided
        if self.debt_amount is None and self.outstanding_balance is not None:
            self.debt_amount = self.outstanding_balance

        # Calculate days_past_due from due_date if daysPastDue not provided
        if self.days_past_due is None and self.due_date is not None:
            if isinstance(self.due_date, str):
                # Parse ISO format date string
                try:
                    self.due_date = datetime.fromisoformat(self.due_date).date()
                except (ValueError, AttributeError):
                    self.due_date = date.fromisoformat(self.due_date)

            if isinstance(self.due_date, datetime):
                due_date = self.due_date.date()
            else:
                due_date = self.due_date

            # Calculate days from today (naive date comparison)
            self.days_past_due = max(0, (date.today() - due_date).days)

        # Ensure debt_amount is set
        if self.debt_amount is None:
            raise ValueError("Either debtAmount or outstandingBalance must be provided")

        # Ensure days_past_due is set
        if self.days_past_due is None:
            raise ValueError("Either daysPastDue or dueDate must be provided")

        return self

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "claimId": "CLM-2026-005678",
                    "patientId": "PAT-123456",
                    "debtAmount": "2500.00",
                    "daysPastDue": 95,
                    "patientName": "João da Silva",
                    "patientPhone": "+55-11-98765-4321",
                    "patientEmail": "joao.silva@example.com",
                }
            ]
        },
    }


class InitiateCollectionOutput(BaseModel):
    """
    Output model for InitiateCollectionWorker.

    Contains collection initiation results, assigned agency, and communication plan.
    """

    collection_initiated: bool = Field(
        ...,
        alias="collectionInitiated",
        description="Whether collection was successfully initiated",
    )
    collection_case_id: str = Field(
        ...,
        alias="collectionCaseId",
        description="Unique collection case identifier",
    )
    collection_status: CollectionStatus = Field(
        ...,
        alias="collectionStatus",
        description="Current status of collection",
    )
    collection_strategy: CollectionStrategy = Field(
        ...,
        alias="collectionStrategy",
        description="Collection strategy selected",
    )
    assigned_to: str = Field(
        ...,
        alias="assignedTo",
        description="Team or agency assigned to collection",
    )
    assigned_to_agency: bool = Field(
        False,
        alias="assignedToAgency",
        description="Whether assigned to external agency",
    )
    next_action_date: datetime = Field(
        ...,
        alias="nextActionDate",
        description="Date of next scheduled action",
    )
    communication_plan: list[ScheduledContact] = Field(
        default_factory=list,
        alias="communicationPlan",
        description="Scheduled contacts with debtor",
    )

    # Additional details
    debt_amount: Decimal = Field(
        ...,
        alias="debtAmount",
        description="Outstanding debt amount",
    )
    days_past_due: int = Field(
        ...,
        alias="daysPastDue",
        description="Days payment is overdue",
    )
    estimated_recovery_rate: Optional[Decimal] = Field(
        None,
        alias="estimatedRecoveryRate",
        description="Estimated % of debt that can be recovered",
    )
    agency_commission_rate: Optional[Decimal] = Field(
        None,
        alias="agencyCommissionRate",
        description="Commission rate if using external agency",
    )
    initiated_date: datetime = Field(
        ...,
        alias="initiatedDate",
        description="Timestamp when collection was initiated",
    )

    # Compliance tracking
    compliance_flags: Optional[list[str]] = Field(
        None,
        alias="complianceFlags",
        description="Any compliance considerations (CDC, vulnerable consumer, etc.)",
    )

    @field_validator("debt_amount", "estimated_recovery_rate", "agency_commission_rate", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Optional[Decimal]:
        """Parse various numeric types to Decimal."""
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    @field_validator("communication_plan", mode="before")
    @classmethod
    def parse_communication_plan(cls, v: Any) -> list[ScheduledContact]:
        """Parse communication plan."""
        if v is None:
            return []
        if isinstance(v, list):
            return [
                ScheduledContact(**item) if isinstance(item, dict) else item
                for item in v
            ]
        return []

    model_config = {
        "populate_by_name": True,
        "json_encoders": {
            Decimal: lambda v: float(round(v, 2)),
            datetime: lambda v: v.isoformat(),
        },
        "json_schema_extra": {
            "examples": [
                {
                    "collectionInitiated": True,
                    "collectionCaseId": "COL-2026-001234",
                    "collectionStatus": "REFERRED",
                    "collectionStrategy": "AGENCY_REFERRAL",
                    "assignedTo": "XYZ Collection Agency",
                    "nextActionDate": "2026-02-05T09:00:00Z",
                    "debtAmount": "2500.00",
                    "daysPastDue": 95,
                    "estimatedRecoveryRate": "65.00",
                    "agencyCommissionRate": "25.00",
                    "initiatedDate": "2026-02-04T14:30:00Z",
                }
            ]
        },
    }
