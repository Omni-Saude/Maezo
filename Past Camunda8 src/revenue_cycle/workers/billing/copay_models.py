"""
Pydantic models for copay calculation and patient responsibility.

These models provide type-safe validation for copay and coinsurance calculation,
including deductible tracking and insurance coverage breakdown.

Follows Brazilian healthcare standards (ANS) for copay mechanisms.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CopayType(str, Enum):
    """
    Types of patient responsibility in Brazilian health insurance.

    Attributes:
        COPAY: Fixed amount per service/procedure
        COINSURANCE: Percentage of the procedure cost
        DEDUCTIBLE: Annual deductible amount
        MIXED: Combination of copay and coinsurance
    """

    COPAY = "COPAY"
    COINSURANCE = "COINSURANCE"
    DEDUCTIBLE = "DEDUCTIBLE"
    MIXED = "MIXED"


class CoverageStatus(str, Enum):
    """
    Coverage status for procedures under a contract.

    Attributes:
        COVERED: Fully covered, patient may have copay/coinsurance
        PARTIALLY_COVERED: Partially covered, patient pays difference
        NOT_COVERED: Not covered, patient pays full amount
        REQUIRES_AUTHORIZATION: Requires prior authorization
    """

    COVERED = "COVERED"
    PARTIALLY_COVERED = "PARTIALLY_COVERED"
    NOT_COVERED = "NOT_COVERED"
    REQUIRES_AUTHORIZATION = "REQUIRES_AUTHORIZATION"


class ProcedureCopayDetail(BaseModel):
    """
    Copay calculation details for a single procedure.

    Tracks copay amount, coinsurance, deductible application, and insurance coverage.
    """

    procedure_code: str = Field(
        ...,
        alias="procedureCode",
        min_length=1,
        description="TUSS or CBHPM procedure code",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable procedure description",
    )
    total_amount: Decimal = Field(
        ...,
        alias="totalAmount",
        ge=0,
        description="Total procedure cost",
    )
    coverage_status: CoverageStatus = Field(
        ...,
        alias="coverageStatus",
        description="Coverage status for this procedure",
    )
    copay_amount: Decimal = Field(
        ...,
        alias="copayAmount",
        ge=0,
        description="Fixed copay amount patient must pay",
    )
    coinsurance_amount: Decimal = Field(
        ...,
        alias="coinsuranceAmount",
        ge=0,
        description="Coinsurance amount (percentage-based) patient must pay",
    )
    coinsurance_rate: Decimal = Field(
        Decimal("0"),
        alias="coinsuranceRate",
        ge=0,
        le=1,
        description="Coinsurance rate (0.0 to 1.0)",
    )
    deductible_applied: Decimal = Field(
        ...,
        alias="deductibleApplied",
        ge=0,
        description="Deductible amount applied to this procedure",
    )
    insurance_covers: Decimal = Field(
        ...,
        alias="insuranceCovers",
        ge=0,
        description="Amount insurance pays for this procedure",
    )
    patient_responsibility: Decimal = Field(
        ...,
        alias="patientResponsibility",
        ge=0,
        description="Total amount patient must pay (copay + coinsurance + deductible + not covered)",
    )

    @field_validator("total_amount", "copay_amount", "coinsurance_amount", "deductible_applied", "insurance_covers", "patient_responsibility", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse amount from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    @model_validator(mode="after")
    def validate_amounts(self) -> ProcedureCopayDetail:
        """Validate that amounts sum correctly."""
        # Copay + Coinsurance + Deductible + (total - coverage) = patient responsibility
        expected_patient_responsibility = (
            self.copay_amount + self.coinsurance_amount + self.deductible_applied
        )

        # Add uncovered amount (only when not fully covered)
        if self.coverage_status == CoverageStatus.NOT_COVERED:
            expected_patient_responsibility += self.total_amount
        elif self.coverage_status == CoverageStatus.PARTIALLY_COVERED:
            uncovered_portion = self.total_amount - self.insurance_covers
            expected_patient_responsibility += uncovered_portion

        # Allow small rounding differences
        difference = abs(self.patient_responsibility - expected_patient_responsibility)
        if difference > Decimal("0.01"):
            raise ValueError(
                f"Patient responsibility {float(self.patient_responsibility)} does not match "
                f"calculated amount {float(expected_patient_responsibility)}"
            )

        return self

    model_config = {
        "populate_by_name": True,
        "json_encoders": {Decimal: lambda v: float(round(v, 2))},
    }


class CalculateCopayInput(BaseModel):
    """
    Input model for CalculateCopayWorker.

    Validates required variables for copay and coinsurance calculation.
    """

    procedure_codes: list[str] = Field(
        ...,
        alias="procedureCodes",
        min_length=1,
        description="List of TUSS codes for procedures",
    )
    coverage_details: dict[str, Any] = Field(
        ...,
        alias="coverageDetails",
        description="Coverage information from eligibility check",
    )
    contract_id: str = Field(
        ...,
        alias="contractId",
        min_length=1,
        description="Insurance contract identifier",
    )
    total_amount: Decimal = Field(
        ...,
        alias="totalAmount",
        gt=0,
        description="Pre-calculated total amount for all procedures",
    )
    patient_id: Optional[str] = Field(
        None,
        alias="patientId",
        description="Patient identifier for deductible tracking",
    )
    payer_id: Optional[str] = Field(
        None,
        alias="payerId",
        description="Insurance payer identifier",
    )
    tenant_id: Optional[str] = Field(
        None,
        alias="tenantId",
        description="Tenant identifier for multi-tenant support",
    )
    deductible_used_year: Optional[Decimal] = Field(
        Decimal("0"),
        alias="deductibleUsedYear",
        ge=0,
        description="Deductible amount already used in current year",
    )
    encounter_date: Optional[str] = Field(
        None,
        alias="encounterDate",
        description="Encounter date (ISO format) for deductible calculation",
    )

    @field_validator("total_amount", "deductible_used_year", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse amount from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "procedureCodes": ["10101012", "20101015"],
                    "coverageDetails": {
                        "copayType": "COPAY",
                        "copayAmount": "50.00",
                        "coinsuranceRate": "0.20",
                        "deductibleAmount": "500.00",
                    },
                    "contractId": "CONT-12345",
                    "totalAmount": "1500.00",
                }
            ]
        },
    }


class CalculateCopayOutput(BaseModel):
    """
    Output model for CalculateCopayWorker.

    Contains copay, coinsurance, deductible, and breakdown by procedure.
    """

    copay_amount: Decimal = Field(
        ...,
        alias="copayAmount",
        ge=0,
        description="Total fixed copay amount patient must pay",
    )
    coinsurance_amount: Decimal = Field(
        ...,
        alias="coinsuranceAmount",
        ge=0,
        description="Total coinsurance amount (percentage-based)",
    )
    deductible_remaining: Decimal = Field(
        ...,
        alias="deductibleRemaining",
        ge=0,
        description="Remaining annual deductible after this encounter",
    )
    deductible_applied: Decimal = Field(
        ...,
        alias="deductibleApplied",
        ge=0,
        description="Deductible amount applied to this encounter",
    )
    coverage_amount: Decimal = Field(
        ...,
        alias="coverageAmount",
        ge=0,
        description="Total amount insurance will pay",
    )
    patient_responsibility: Decimal = Field(
        ...,
        alias="patientResponsibility",
        ge=0,
        description="Total amount patient must pay",
    )
    breakdown_by_procedure: list[ProcedureCopayDetail] = Field(
        ...,
        alias="breakdownByProcedure",
        description="Detailed copay calculation per procedure",
    )
    copay_type_applied: CopayType = Field(
        ...,
        alias="copayTypeApplied",
        description="Type of copay mechanism applied",
    )
    calculation_rules_applied: list[str] = Field(
        default_factory=list,
        alias="calculationRulesApplied",
        description="List of copay rules applied (audit trail)",
    )
    contract_id: Optional[str] = Field(
        None,
        alias="contractId",
        description="Contract identifier used for calculation",
    )

    @field_validator("copay_amount", "coinsurance_amount", "deductible_remaining", "deductible_applied", "coverage_amount", "patient_responsibility", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse amount from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    @model_validator(mode="after")
    def validate_totals(self) -> CalculateCopayOutput:
        """Validate that amounts sum correctly."""
        # Patient responsibility = copay + coinsurance + deductible applied + uncovered
        expected_responsibility = self.copay_amount + self.coinsurance_amount + self.deductible_applied

        # Calculate uncovered amount from breakdown
        for procedure in self.breakdown_by_procedure:
            if procedure.coverage_status == CoverageStatus.NOT_COVERED:
                expected_responsibility += procedure.total_amount
            elif procedure.coverage_status == CoverageStatus.PARTIALLY_COVERED:
                uncovered = procedure.total_amount - procedure.insurance_covers
                if uncovered > Decimal("0"):
                    expected_responsibility += uncovered

        # Allow small rounding differences (up to 0.05 for multiple procedures)
        difference = abs(self.patient_responsibility - expected_responsibility)
        if difference > Decimal("0.05"):
            raise ValueError(
                f"Patient responsibility {float(self.patient_responsibility)} does not match "
                f"calculated amount {float(expected_responsibility)}"
            )

        # Coverage amount + Patient responsibility should equal total
        total_from_breakdown = sum(p.total_amount for p in self.breakdown_by_procedure)
        expected_total = self.coverage_amount + self.patient_responsibility

        difference = abs(total_from_breakdown - expected_total)
        if difference > Decimal("0.05"):
            raise ValueError(
                f"Total amount {float(total_from_breakdown)} does not match "
                f"coverage {float(self.coverage_amount)} + responsibility {float(self.patient_responsibility)}"
            )

        return self

    model_config = {
        "populate_by_name": True,
        "json_encoders": {Decimal: lambda v: float(round(v, 2))},
    }


class ContractCopayRule(BaseModel):
    """
    Copay rule configuration within a contract.

    Defines how copay/coinsurance should be calculated for specific procedures.
    """

    rule_id: str = Field(..., alias="ruleId", description="Unique rule identifier")
    copay_type: CopayType = Field(..., alias="copayType", description="Type of copay")
    copay_amount: Optional[Decimal] = Field(None, alias="copayAmount", description="Fixed copay amount")
    coinsurance_rate: Optional[Decimal] = Field(None, alias="coinsuranceRate", ge=0, le=1, description="Coinsurance rate (0-1)")
    deductible_amount: Optional[Decimal] = Field(None, alias="deductibleAmount", description="Annual deductible")
    applies_to_categories: Optional[list[str]] = Field(None, alias="appliesToCategories", description="Charge categories this rule applies to")
    applies_to_procedures: Optional[list[str]] = Field(None, alias="appliesToProcedures", description="Specific procedure codes this rule applies to")
    minimum_copay: Optional[Decimal] = Field(None, alias="minimumCopay", description="Minimum copay amount")
    maximum_copay: Optional[Decimal] = Field(None, alias="maximumCopay", description="Maximum copay amount per procedure")

    model_config = {
        "populate_by_name": True,
        "json_encoders": {Decimal: lambda v: float(round(v, 2))},
    }
