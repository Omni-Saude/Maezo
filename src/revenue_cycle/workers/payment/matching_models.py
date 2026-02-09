"""
Pydantic models for auto-matching worker input/output validation.

These models provide type-safe validation for automated remittance-to-claim matching,
supporting fuzzy matching, confidence scoring, and partial match suggestions.

Used by AutoMatchingWorker for insurance remittance reconciliation.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class MatchType(str, Enum):
    """
    Types of matches found during auto-matching.

    Attributes:
        EXACT: Exact match on claim number and amount
        FUZZY: Fuzzy match on patient name, date, and amount
        PARTIAL: Partial match requiring manual review
        NONE: No match found
    """

    EXACT = "EXACT"
    FUZZY = "FUZZY"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class RemittanceItem(BaseModel):
    """
    Individual item from insurance remittance file.

    Represents a payment line item with potential adjustments (glosas).
    """

    item_id: str = Field(
        ...,
        alias="itemId",
        description="Unique identifier for this remittance item",
    )
    claim_number: Optional[str] = Field(
        None,
        alias="claimNumber",
        description="Claim number from remittance",
    )
    patient_name: str = Field(
        ...,
        alias="patientName",
        description="Patient name from remittance",
    )
    service_date: date = Field(
        ...,
        alias="serviceDate",
        description="Date of service",
    )
    billed_amount: Decimal = Field(
        ...,
        alias="billedAmount",
        gt=0,
        description="Amount originally billed",
    )
    paid_amount: Decimal = Field(
        ...,
        alias="paidAmount",
        ge=0,
        description="Amount paid by insurance",
    )
    adjustment_amount: Optional[Decimal] = Field(
        None,
        alias="adjustmentAmount",
        description="Adjustment/glosa amount (if any)",
    )
    adjustment_reason: Optional[str] = Field(
        None,
        alias="adjustmentReason",
        description="Reason for adjustment/glosa",
    )
    procedure_code: Optional[str] = Field(
        None,
        alias="procedureCode",
        description="Procedure/TUSS code",
    )

    @field_validator("billed_amount", "paid_amount", "adjustment_amount", mode="before")
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

    @field_validator("service_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date:
        """Parse date from various formats."""
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
            except ValueError:
                from dateutil import parser
                return parser.parse(v).date()
        raise ValueError(f"Cannot convert {type(v).__name__} to date")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "itemId": "REM-001-001",
                    "claimNumber": "CLM-2026-005678",
                    "patientName": "João da Silva",
                    "serviceDate": "2026-01-15",
                    "billedAmount": "1500.00",
                    "paidAmount": "1350.00",
                    "adjustmentAmount": "150.00",
                    "adjustmentReason": "Tabela não compatível",
                }
            ]
        },
    }


class UnmatchedClaim(BaseModel):
    """
    Claim awaiting payment matching.

    Represents a claim that needs to be matched with remittance items.
    """

    claim_id: str = Field(
        ...,
        alias="claimId",
        description="Unique claim identifier",
    )
    claim_number: str = Field(
        ...,
        alias="claimNumber",
        description="Claim number for matching",
    )
    patient_name: str = Field(
        ...,
        alias="patientName",
        description="Patient name",
    )
    service_date: date = Field(
        ...,
        alias="serviceDate",
        description="Date of service",
    )
    billed_amount: Decimal = Field(
        ...,
        alias="billedAmount",
        gt=0,
        description="Billed amount",
    )
    expected_amount: Optional[Decimal] = Field(
        None,
        alias="expectedAmount",
        description="Expected payment amount (after glosas)",
    )

    @field_validator("billed_amount", "expected_amount", mode="before")
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

    @field_validator("service_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date:
        """Parse date from various formats."""
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
            except ValueError:
                from dateutil import parser
                return parser.parse(v).date()
        raise ValueError(f"Cannot convert {type(v).__name__} to date")

    model_config = {
        "populate_by_name": True,
    }


class MatchedItem(BaseModel):
    """
    Result of matching a remittance item with a claim.

    Contains both the remittance item and matched claim with confidence score.
    """

    remittance_item: RemittanceItem = Field(
        ...,
        alias="remittanceItem",
        description="The remittance item",
    )
    matched_claim: UnmatchedClaim = Field(
        ...,
        alias="matchedClaim",
        description="The matched claim",
    )
    match_type: MatchType = Field(
        ...,
        alias="matchType",
        description="Type of match",
    )
    confidence_score: Decimal = Field(
        ...,
        alias="confidenceScore",
        ge=0,
        le=1,
        description="Confidence score (0-1)",
    )
    match_reasons: list[str] = Field(
        default_factory=list,
        alias="matchReasons",
        description="Reasons for the match",
    )

    model_config = {
        "populate_by_name": True,
    }


class MatchingSummary(BaseModel):
    """
    Summary statistics for matching operation.

    Provides overview of matching results for reporting.
    """

    total_remittance_items: int = Field(
        ...,
        alias="totalRemittanceItems",
        ge=0,
        description="Total remittance items processed",
    )
    total_claims: int = Field(
        ...,
        alias="totalClaims",
        ge=0,
        description="Total claims available for matching",
    )
    exact_matches: int = Field(
        ...,
        alias="exactMatches",
        ge=0,
        description="Number of exact matches",
    )
    fuzzy_matches: int = Field(
        ...,
        alias="fuzzyMatches",
        ge=0,
        description="Number of fuzzy matches",
    )
    partial_matches: int = Field(
        ...,
        alias="partialMatches",
        ge=0,
        description="Number of partial matches requiring review",
    )
    unmatched_remittances: int = Field(
        ...,
        alias="unmatchedRemittances",
        ge=0,
        description="Number of unmatched remittance items",
    )
    unmatched_claims: int = Field(
        ...,
        alias="unmatchedClaims",
        ge=0,
        description="Number of unmatched claims",
    )
    total_paid_amount: Decimal = Field(
        ...,
        alias="totalPaidAmount",
        ge=0,
        description="Total amount paid in remittance",
    )
    total_matched_amount: Decimal = Field(
        ...,
        alias="totalMatchedAmount",
        ge=0,
        description="Total amount successfully matched",
    )
    matching_rate: Decimal = Field(
        ...,
        alias="matchingRate",
        ge=0,
        le=100,
        description="Percentage of items matched (0-100)",
    )

    @field_validator("total_paid_amount", "total_matched_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse various numeric types to Decimal."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {
        "populate_by_name": True,
    }


class AutoMatchingInput(BaseModel):
    """
    Input model for AutoMatchingWorker.

    Validates all required fields for automated remittance-to-claim matching.
    """

    remittance_file: str = Field(
        ...,
        alias="remittanceFile",
        min_length=1,
        description="Remittance file identifier",
    )
    remittance_items: list[RemittanceItem] = Field(
        ...,
        alias="remittanceItems",
        min_length=1,
        description="List of remittance items to match",
    )
    unmatched_claims: list[UnmatchedClaim] = Field(
        ...,
        alias="unmatchedClaims",
        min_length=0,
        description="List of claims awaiting payment",
    )
    matching_tolerance: Decimal = Field(
        default=Decimal("0.01"),
        alias="matchingTolerance",
        ge=0,
        description="Amount variance tolerance (default R$0.01)",
    )
    fuzzy_threshold: Decimal = Field(
        default=Decimal("0.80"),
        alias="fuzzyThreshold",
        ge=0,
        le=1,
        description="Minimum confidence for fuzzy matches (0-1)",
    )

    @field_validator("matching_tolerance", "fuzzy_threshold", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse various numeric types to Decimal."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    # Multi-tenant support
    tenant_id: Optional[str] = Field(
        None,
        alias="tenantId",
        description="Tenant identifier",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "remittanceFile": "REM-20260204-001",
                    "remittanceItems": [
                        {
                            "itemId": "REM-001-001",
                            "claimNumber": "CLM-2026-005678",
                            "patientName": "João da Silva",
                            "serviceDate": "2026-01-15",
                            "billedAmount": "1500.00",
                            "paidAmount": "1350.00",
                        }
                    ],
                    "unmatchedClaims": [
                        {
                            "claimId": "CLM-2026-005678",
                            "claimNumber": "CLM-2026-005678",
                            "patientName": "João da Silva",
                            "serviceDate": "2026-01-15",
                            "billedAmount": "1500.00",
                        }
                    ],
                    "matchingTolerance": "0.01",
                }
            ]
        },
    }


class AutoMatchingOutput(BaseModel):
    """
    Output model for AutoMatchingWorker.

    Contains matching results, statistics, and items requiring manual review.
    """

    matching_complete: bool = Field(
        ...,
        alias="matchingComplete",
        description="Whether matching completed successfully",
    )
    matched_items: list[MatchedItem] = Field(
        ...,
        alias="matchedItems",
        description="List of successfully matched items",
    )
    unmatched_remittances: list[RemittanceItem] = Field(
        ...,
        alias="unmatchedRemittances",
        description="Remittance items without matching claims",
    )
    unmatched_claims: list[UnmatchedClaim] = Field(
        ...,
        alias="unmatchedClaims",
        description="Claims without matching remittances",
    )
    matching_summary: MatchingSummary = Field(
        ...,
        alias="matchingSummary",
        description="Summary statistics",
    )
    confidence_scores: dict[str, float] = Field(
        default_factory=dict,
        alias="confidenceScores",
        description="Confidence scores by item ID",
    )
    requires_manual_review: bool = Field(
        ...,
        alias="requiresManualReview",
        description="Whether manual review is required",
    )
    manual_review_count: int = Field(
        default=0,
        alias="manualReviewCount",
        ge=0,
        description="Number of items requiring manual review",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "matchingComplete": True,
                    "matchedItems": [],
                    "unmatchedRemittances": [],
                    "unmatchedClaims": [],
                    "matchingSummary": {
                        "totalRemittanceItems": 10,
                        "totalClaims": 12,
                        "exactMatches": 8,
                        "fuzzyMatches": 2,
                        "partialMatches": 0,
                        "unmatchedRemittances": 0,
                        "unmatchedClaims": 2,
                        "totalPaidAmount": "15000.00",
                        "totalMatchedAmount": "15000.00",
                        "matchingRate": "100.00",
                    },
                    "confidenceScores": {},
                    "requiresManualReview": False,
                    "manualReviewCount": 0,
                }
            ]
        },
    }
