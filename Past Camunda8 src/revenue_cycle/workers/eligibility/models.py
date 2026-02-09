"""
Pydantic models for eligibility verification workers.

These models provide type-safe validation for insurance eligibility
verification, coverage details, and authorization requirements.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CoverageStatus(str, Enum):
    """
    Status of insurance coverage.

    Attributes:
        ACTIVE: Coverage is active and valid
        SUSPENDED: Coverage temporarily suspended
        CANCELLED: Coverage cancelled
        PENDING: Coverage pending activation
        EXPIRED: Coverage expired
    """
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"


class AuthorizationType(str, Enum):
    """
    Types of authorization required for procedures.

    Attributes:
        NONE: No authorization required
        PRIOR: Prior authorization required before service
        CONCURRENT: Concurrent authorization during service
        RETROSPECTIVE: Retrospective authorization after service
    """
    NONE = "NONE"
    PRIOR = "PRIOR"
    CONCURRENT = "CONCURRENT"
    RETROSPECTIVE = "RETROSPECTIVE"


class CoverageLevel(str, Enum):
    """
    Level of coverage for procedures.

    Attributes:
        FULL: Procedure fully covered
        PARTIAL: Procedure partially covered
        NOT_COVERED: Procedure not covered
        SUBJECT_TO_AUTHORIZATION: Coverage subject to authorization
    """
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NOT_COVERED = "NOT_COVERED"
    SUBJECT_TO_AUTHORIZATION = "SUBJECT_TO_AUTHORIZATION"


class EligibilityStatus(str, Enum):
    """
    Status of patient eligibility for healthcare services.

    Attributes:
        ELIGIBLE: Patient is eligible for services
        INELIGIBLE: Patient is not eligible for services
        PENDING: Eligibility verification is pending
        EXPIRED: Patient eligibility has expired
        SUSPENDED: Patient eligibility is suspended
    """
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"


class EligibilityError(BaseModel):
    """
    Structured error information from eligibility verification.
    """
    error_code: str = Field(..., alias="errorCode")
    error_message: str = Field(..., alias="errorMessage")
    field: Optional[str] = None
    severity: str = Field("ERROR")  # ERROR, WARNING, INFO

    model_config = {
        "populate_by_name": True,
    }


class CoveragePeriod(BaseModel):
    """
    Coverage period with start and end dates.

    Represents a period of time during which insurance coverage is active.
    """
    start_date: date = Field(..., alias="startDate", description="Start date of coverage")
    end_date: date = Field(..., alias="endDate", description="End date of coverage")

    model_config = {
        "populate_by_name": True,
    }


class CoverageDetail(BaseModel):
    """
    Detailed coverage information for a specific procedure or category.
    """
    procedure_code: Optional[str] = Field(None, alias="procedureCode")
    procedure_category: Optional[str] = Field(None, alias="procedureCategory")
    coverage_level: CoverageLevel = Field(..., alias="coverageLevel")
    coverage_percentage: Decimal = Field(
        Decimal("100.00"),
        alias="coveragePercentage",
        ge=0,
        le=100,
        description="Percentage of procedure covered by insurance (0-100)"
    )
    annual_limit: Optional[Decimal] = Field(
        None,
        alias="annualLimit",
        description="Annual limit for this procedure/category"
    )
    remaining_limit: Optional[Decimal] = Field(
        None,
        alias="remainingLimit",
        description="Remaining annual limit"
    )
    notes: Optional[str] = None

    @field_validator("coverage_percentage", "annual_limit", "remaining_limit", mode="before")
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

    model_config = {
        "populate_by_name": True,
        "json_encoders": {Decimal: lambda v: float(round(v, 2))},
    }


class ValidateEligibilityInput(BaseModel):
    """
    Input model for ValidateEligibilityWorker.

    Validates the process variables required for eligibility verification.
    """
    patient_id: str = Field(
        ...,
        alias="patientId",
        min_length=1,
        description="Patient identifier"
    )
    insurance_id: str = Field(
        ...,
        alias="insuranceId",
        min_length=1,
        description="Insurance plan identifier (ANS registration number or internal ID)"
    )
    procedure_codes: List[str] = Field(
        default_factory=list,
        alias="procedureCodes",
        description="List of procedure codes to verify coverage (TUSS/CBHPM)"
    )
    encounter_date: Optional[date] = Field(
        None,
        alias="encounterDate",
        description="Date of service/encounter"
    )
    service_date: Optional[date] = Field(
        None,
        alias="serviceDate",
        description="Alias for encounter_date for backwards compatibility"
    )
    encounter_id: Optional[str] = Field(
        None,
        alias="encounterId",
        description="Optional encounter identifier for tracking"
    )
    card_number: Optional[str] = Field(
        None,
        alias="cardNumber",
        description="Patient insurance card number"
    )
    validate_authorization: bool = Field(
        True,
        alias="validateAuthorization",
        description="Whether to check authorization requirements"
    )
    tenant_id: Optional[str] = Field(
        None,
        alias="tenantId",
        description="Tenant identifier for multi-tenant support"
    )

    @field_validator("encounter_date", "service_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> Optional[date]:
        """Parse date from various formats."""
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            # Try ISO format first (YYYY-MM-DD)
            try:
                return datetime.fromisoformat(v).date()
            except ValueError:
                pass
            # Try Brazilian format (DD/MM/YYYY)
            try:
                return datetime.strptime(v, "%d/%m/%Y").date()
            except ValueError:
                pass
            # Try other common formats
            try:
                return datetime.strptime(v, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError(f"Cannot parse date from: {v}")
        raise ValueError(f"Cannot convert {type(v).__name__} to date")

    @field_validator("procedure_codes", mode="before")
    @classmethod
    def validate_procedure_codes(cls, v: Any) -> List[str]:
        """Validate each procedure code is not empty."""
        if v is None or (isinstance(v, list) and len(v) == 0):
            return []  # Allow empty list
        if not isinstance(v, list):
            v = [v]
        validated_codes = []
        for code in v:
            if not code or not str(code).strip():
                raise ValueError("Procedure code cannot be empty")
            validated_codes.append(str(code).strip())
        return validated_codes

    @model_validator(mode="after")
    def normalize_dates_and_validate(self) -> "ValidateEligibilityInput":
        """Normalize service_date to encounter_date and validate."""
        # If service_date is provided and encounter_date is not, use service_date
        if self.service_date is not None:
            if self.encounter_date is None:
                self.encounter_date = self.service_date

        # If neither is provided, default to today
        if self.encounter_date is None:
            self.encounter_date = date.today()

        # Set service_date to encounter_date if not already set
        if self.service_date is None:
            self.service_date = self.encounter_date

        return self

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "patientId": "PAT-123456",
                    "insuranceId": "ANS-12345",
                    "procedureCodes": ["10101012", "20101015"],
                    "encounterDate": "2026-02-04",
                    "cardNumber": "1234567890123456",
                }
            ]
        },
    }


class ValidateEligibilityOutput(BaseModel):
    """
    Output model for ValidateEligibilityWorker.

    Contains eligibility verification results, coverage details, and authorization requirements.
    Supports both old and new field naming for backwards compatibility.
    """
    # Main eligibility status
    eligible: bool = Field(
        ...,
        description="Whether patient is eligible for services"
    )
    eligibility_status: str = Field(
        ...,
        alias="eligibilityStatus",
        description="Status of insurance eligibility (ACTIVE, INACTIVE, EXPIRED, etc.)"
    )

    # Coverage dates
    coverage_start: Optional[date] = Field(
        None,
        alias="coverageStart",
        description="Coverage start date"
    )
    coverage_end: Optional[date] = Field(
        None,
        alias="coverageEnd",
        description="Coverage end date"
    )

    # Plan and provider information
    plan_name: Optional[str] = Field(
        None,
        alias="planName",
        description="Insurance plan name"
    )
    member_id: Optional[str] = Field(
        None,
        alias="memberId",
        description="Patient member ID in insurance plan"
    )
    payer_id: Optional[str] = Field(
        None,
        alias="payerId",
        description="Payer/insurance company identifier"
    )
    payer_name: Optional[str] = Field(
        None,
        alias="payerName",
        description="Payer/insurance company name"
    )

    # Benefits information
    max_coverage: Optional[Decimal] = Field(
        None,
        alias="maxCoverage",
        description="Maximum annual coverage amount"
    )
    deductible: Optional[Decimal] = Field(
        None,
        alias="deductible",
        description="Annual deductible amount"
    )
    copay_percentage: Optional[float] = Field(
        None,
        alias="copayPercentage",
        description="Copay/coinsurance percentage (0-100)"
    )

    # Ineligibility reason (if not eligible)
    ineligibility_reason: Optional[str] = Field(
        None,
        alias="ineligibilityReason",
        description="Reason for ineligibility if not eligible"
    )

    # Authorization information
    authorization_required: bool = Field(
        False,
        alias="authorizationRequired",
        description="Whether prior authorization is required"
    )
    authorization_type: Optional[str] = Field(
        None,
        alias="authorizationType",
        description="Type of authorization required (PRIOR, CONCURRENT, RETROSPECTIVE)"
    )

    @field_validator("max_coverage", "deductible", mode="before")
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

    model_config = {
        "populate_by_name": True,
        "json_encoders": {
            Decimal: lambda v: float(round(v, 2)),
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        },
    }
