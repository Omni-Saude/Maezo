"""
Pydantic models for billing workers input/output validation.

These models provide type-safe validation for contract rules application,
claim generation, and billing-related Camunda process variables.

Includes TISS 4.0 compliance models for Brazilian healthcare claims.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# Import copay models for re-export (tests expect them here)
from revenue_cycle.workers.billing.copay_models import (
    CopayType,
    CoverageStatus,
    ProcedureCopayDetail,
    CalculateCopayInput,
    CalculateCopayOutput,
    ContractCopayRule,
)

# =============================================================================
# Regex patterns for Brazilian healthcare procedure codes
# =============================================================================
TUSS_PATTERN = re.compile(r"^\d{8}$")
CBHPM_PATTERN = re.compile(r"^\d\.\d{2}\.\d{2}\.\d{2}-\d$")


class ChargeCategory(str, Enum):
    """
    Categories of charges in the billing system.

    Based on ANS (Agencia Nacional de Saude Suplementar) standards.

    Attributes:
        PROFESSIONAL: Professional fees (AMB/CBHPM procedures)
        HOSPITAL: Hospital fees, daily rates, room charges
        MATERIALS: OPME, disposable materials, implants
        MEDICATIONS: Medications per SIMPRO/Brasindice
        SERVICES: General services (exams, therapies)
        PACKAGES: Package rates (diarias globais)
    """

    PROFESSIONAL = "PROFESSIONAL"
    HOSPITAL = "HOSPITAL"
    MATERIALS = "MATERIALS"
    MEDICATIONS = "MEDICATIONS"
    SERVICES = "SERVICES"
    PACKAGES = "PACKAGES"


class PricingTableType(str, Enum):
    """
    Types of pricing tables used in Brazilian healthcare.

    Attributes:
        TUSS: Terminologia Unificada da Saude Suplementar
        CBHPM: Classificacao Brasileira Hierarquizada de Procedimentos Medicos
        AMB: Associacao Medica Brasileira (legacy)
        BRASINDICE: Medication pricing table
        SIMPRO: Medication pricing table
        SUS: Sistema Unico de Saude table
        CUSTOM: Custom pricing table per contract
    """

    TUSS = "TUSS"
    CBHPM = "CBHPM"
    AMB = "AMB"
    BRASINDICE = "BRASINDICE"
    SIMPRO = "SIMPRO"
    SUS = "SUS"
    CUSTOM = "CUSTOM"


class ContractRuleType(str, Enum):
    """
    Types of contract pricing rules.

    Attributes:
        PERCENTAGE: Apply percentage discount/markup
        FIXED: Fixed price per procedure
        PACKAGE: Package pricing (bundle)
        TIERED: Volume-based tiered pricing
        CAP: Maximum amount cap
    """

    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"
    PACKAGE = "PACKAGE"
    TIERED = "TIERED"
    CAP = "CAP"


class EncounterType(str, Enum):
    """
    Types of patient encounters.

    Attributes:
        AMBULATORIO: Outpatient/ambulatory
        INTERNACAO: Inpatient hospitalization
        URGENCIA: Emergency
        DAY_CLINIC: Day clinic
        HOME_CARE: Home care
    """

    AMBULATORIO = "AMBULATORIO"
    INTERNACAO = "INTERNACAO"
    URGENCIA = "URGENCIA"
    DAY_CLINIC = "DAY_CLINIC"
    HOME_CARE = "HOME_CARE"


class ChargeItem(BaseModel):
    """
    Individual charge item from consolidated charges.

    Represents a single billable item (procedure, material, medication, etc.)
    """

    charge_code: str = Field(
        ...,
        alias="chargeCode",
        min_length=1,
        description="Procedure/item code (TUSS, CBHPM, etc.)",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description",
    )
    amount: Decimal = Field(
        ...,
        ge=0,
        description="Unit price/amount",
    )
    category: ChargeCategory = Field(
        ...,
        description="Charge category for discount rate lookup",
    )
    quantity: int = Field(
        1,
        ge=1,
        description="Number of units",
    )
    complete: bool = Field(
        True,
        description="Whether documentation is complete",
    )
    pricing_table: Optional[PricingTableType] = Field(
        None,
        alias="pricingTable",
        description="Pricing table used for this item",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v: Any) -> Decimal:
        """Parse amount from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    @property
    def total_amount(self) -> Decimal:
        """Calculate total amount (unit price * quantity)."""
        return self.amount * self.quantity

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "chargeCode": "10101012",
                    "description": "Consulta Medica",
                    "amount": "200.00",
                    "category": "PROFESSIONAL",
                    "quantity": 1,
                    "complete": True,
                }
            ]
        },
    }


class ApplyContractRulesInput(BaseModel):
    """
    Input model for ApplyContractRulesWorker.

    Validates the process variables required for contract rules application.
    """

    payer_id: str = Field(
        ...,
        alias="payerId",
        min_length=1,
        description="Insurance payer identifier (ANS code or CNPJ)",
    )
    consolidated_charges: list[ChargeItem] = Field(
        ...,
        alias="consolidatedCharges",
        min_length=1,
        description="List of consolidated charge items",
    )
    total_charge_amount: Decimal = Field(
        ...,
        alias="totalChargeAmount",
        gt=0,
        description="Total charge amount before adjustments",
    )
    encounter_id: Optional[str] = Field(
        None,
        alias="encounterId",
        description="Encounter identifier",
    )
    encounter_type: Optional[EncounterType] = Field(
        None,
        alias="encounterType",
        description="Type of encounter",
    )
    total_days: Optional[int] = Field(
        None,
        alias="totalDays",
        ge=1,
        description="Total days for hospitalization encounters",
    )
    contract_id: Optional[str] = Field(
        None,
        alias="contractId",
        description="Specific contract ID to use (if known)",
    )
    tenant_id: Optional[str] = Field(
        None,
        alias="tenantId",
        description="Tenant identifier for multi-tenant support",
    )

    @field_validator("total_charge_amount", mode="before")
    @classmethod
    def parse_total(cls, v: Any) -> Decimal:
        """Parse total amount from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    @model_validator(mode="after")
    def validate_hospitalization(self) -> "ApplyContractRulesInput":
        """Validate hospitalization encounters have total_days."""
        if self.encounter_type == EncounterType.INTERNACAO and not self.total_days:
            # Default to 1 if not provided
            self.total_days = 1
        return self

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "payerId": "ANS-12345",
                    "consolidatedCharges": [
                        {
                            "chargeCode": "10101012",
                            "description": "Consulta Medica",
                            "amount": "200.00",
                            "category": "PROFESSIONAL",
                            "quantity": 1,
                        }
                    ],
                    "totalChargeAmount": "200.00",
                }
            ]
        },
    }


class AdjustedChargeItem(BaseModel):
    """
    Charge item after contract rules application.

    Contains original amount, discount information, and final adjusted amount.
    """

    charge_code: str = Field(
        ...,
        alias="chargeCode",
        description="Procedure/item code",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description",
    )
    category: str = Field(
        ...,
        description="Charge category",
    )
    quantity: int = Field(
        1,
        ge=1,
        description="Number of units",
    )
    original_amount: Decimal = Field(
        ...,
        alias="originalAmount",
        description="Original amount before discount",
    )
    contract_discount: Decimal = Field(
        ...,
        alias="contractDiscount",
        description="Discount amount applied",
    )
    amount: Decimal = Field(
        ...,
        description="Final amount after discount",
    )
    discount_rate: Decimal = Field(
        ...,
        alias="discountRate",
        description="Discount rate applied (0.0 to 1.0)",
    )
    rule_applied: Optional[str] = Field(
        None,
        alias="ruleApplied",
        description="Description of rule applied",
    )
    pricing_table: Optional[str] = Field(
        None,
        alias="pricingTable",
        description="Pricing table used",
    )

    model_config = {
        "populate_by_name": True,
        "json_encoders": {Decimal: lambda v: float(round(v, 2))},
    }


class DiscountApplied(BaseModel):
    """
    Information about a discount applied during contract rules processing.
    """

    discount_type: str = Field(
        ...,
        alias="discountType",
        description="Type of discount (CATEGORY, VOLUME, PACKAGE, CONTRACT)",
    )
    category: Optional[str] = Field(
        None,
        description="Category this discount applies to",
    )
    rate: Decimal = Field(
        ...,
        ge=0,
        le=1,
        description="Discount rate (0.0 to 1.0)",
    )
    amount: Decimal = Field(
        ...,
        description="Total discount amount",
    )
    description: str = Field(
        ...,
        description="Human-readable description of the discount",
    )

    model_config = {
        "populate_by_name": True,
        "json_encoders": {Decimal: lambda v: float(round(v, 2))},
    }


class ApplyContractRulesOutput(BaseModel):
    """
    Output model for ApplyContractRulesWorker.

    Contains adjusted charges, totals, and applied rules information.
    """

    contract_adjusted_charges: list[AdjustedChargeItem] = Field(
        ...,
        alias="contractAdjustedCharges",
        description="Charges after contract rules applied",
    )
    contract_adjusted_amount: Decimal = Field(
        ...,
        alias="contractAdjustedAmount",
        description="Total amount after adjustments",
    )
    contract_discount: Decimal = Field(
        ...,
        alias="contractDiscount",
        description="Total discount applied",
    )
    contract_rules_applied: list[str] = Field(
        ...,
        alias="contractRulesApplied",
        description="List of rules applied (descriptions)",
    )
    contract_id: Optional[str] = Field(
        None,
        alias="contractId",
        description="Contract identifier used",
    )
    pricing_table_used: Optional[str] = Field(
        None,
        alias="pricingTableUsed",
        description="Primary pricing table used",
    )
    discounts_applied: list[DiscountApplied] = Field(
        default_factory=list,
        alias="discountsApplied",
        description="Detailed list of discounts applied",
    )
    max_claim_amount: Optional[Decimal] = Field(
        None,
        alias="maxClaimAmount",
        description="Contract maximum claim amount",
    )
    within_contract_limits: bool = Field(
        True,
        alias="withinContractLimits",
        description="Whether adjusted amount is within contract limits",
    )

    model_config = {
        "populate_by_name": True,
        "json_encoders": {Decimal: lambda v: float(round(v, 2))},
    }


# Contract domain models for the service layer


class ContractDiscountRate(BaseModel):
    """
    Discount rate configuration for a specific category within a contract.
    """

    category: ChargeCategory
    discount_rate: Decimal = Field(..., ge=0, le=1)
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None

    @field_validator("discount_rate", mode="before")
    @classmethod
    def parse_rate(cls, v: Any) -> Decimal:
        """Parse rate from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v)
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")


class ContractProcedure(BaseModel):
    """
    Procedure coverage information within a contract.
    """

    procedure_code: str
    coverage_status: str = "COVERED"
    fixed_price: Optional[Decimal] = None
    special_discount: Optional[Decimal] = None


class Contract(BaseModel):
    """
    Contract information including discount rates and coverage.
    """

    contract_id: str
    payer_id: str
    payer_name: Optional[str] = None
    max_claim_amount: Optional[Decimal] = None
    effective_date: date
    expiration_date: Optional[date] = None
    status: str = "ACTIVE"
    pricing_table: PricingTableType = PricingTableType.TUSS
    discount_rates: dict[str, Decimal] = Field(default_factory=dict)
    covered_procedures: list[str] = Field(default_factory=list)
    tenant_id: Optional[str] = None

    @property
    def is_active(self) -> bool:
        """Check if contract is currently active."""
        today = date.today()
        if self.status != "ACTIVE":
            return False
        if self.effective_date > today:
            return False
        if self.expiration_date and self.expiration_date < today:
            return False
        return True

    def get_discount_rate(self, category: ChargeCategory) -> Decimal:
        """Get discount rate for a category, defaulting to 0 if not found."""
        return self.discount_rates.get(category.value, Decimal("0"))

    def is_procedure_covered(self, procedure_code: str) -> bool:
        """Check if a procedure is covered by this contract."""
        # If no covered_procedures list, assume all are covered
        if not self.covered_procedures:
            return True
        return procedure_code in self.covered_procedures

    model_config = {
        "json_encoders": {Decimal: lambda v: float(round(v, 4))},
    }


# =============================================================================
# Claim Generation Models (GenerateClaimWorker)
# =============================================================================


class ClaimType(str, Enum):
    """
    Types of TISS claims in the Brazilian healthcare system.

    Based on ANS TISS 4.0 specification:
    - SP_SADT: Servicos Profissionais - Servico Auxiliar de Diagnostico e Terapia
    - INTERNACAO: Hospitalization/Inpatient claims
    - CONSULTA: Outpatient consultation claims
    - OUTRAS_DESPESAS: Other expenses
    - HONORARIOS: Professional fees
    """

    SP_SADT = "SP_SADT"
    INTERNACAO = "INTERNACAO"
    CONSULTA = "CONSULTA"
    OUTRAS_DESPESAS = "OUTRAS_DESPESAS"
    HONORARIOS = "HONORARIOS"

    @property
    def tiss_code(self) -> str:
        """Get the TISS numeric code for this claim type."""
        code_mapping = {
            ClaimType.SP_SADT: "3",
            ClaimType.INTERNACAO: "4",
            ClaimType.CONSULTA: "2",
            ClaimType.OUTRAS_DESPESAS: "5",
            ClaimType.HONORARIOS: "6",
        }
        return code_mapping[self]


class ProcedureType(str, Enum):
    """
    Types of medical procedures.

    Based on TUSS/CBHPM classification.
    """

    SURGICAL = "SURGICAL"
    CLINICAL = "CLINICAL"
    DIAGNOSTIC = "DIAGNOSTIC"
    THERAPEUTIC = "THERAPEUTIC"
    HOSPITALIZATION = "HOSPITALIZATION"
    LABORATORY = "LABORATORY"
    IMAGING = "IMAGING"

    @classmethod
    def from_code_prefix(cls, code: str) -> "ProcedureType":
        """
        Determine procedure type from code prefix.

        Args:
            code: TUSS or CBHPM procedure code

        Returns:
            Appropriate ProcedureType
        """
        # Extract first digits for classification
        if TUSS_PATTERN.match(code):
            prefix = code[:2]
            prefix_mapping = {
                "10": cls.CLINICAL,
                "20": cls.DIAGNOSTIC,
                "30": cls.SURGICAL,
                "40": cls.THERAPEUTIC,
                "50": cls.LABORATORY,
                "60": cls.IMAGING,
                "80": cls.HOSPITALIZATION,
            }
            return prefix_mapping.get(prefix, cls.CLINICAL)
        elif CBHPM_PATTERN.match(code):
            first_digit = code[0]
            digit_mapping = {
                "1": cls.CLINICAL,
                "2": cls.DIAGNOSTIC,
                "3": cls.SURGICAL,
                "4": cls.THERAPEUTIC,
                "5": cls.LABORATORY,
            }
            return digit_mapping.get(first_digit, cls.CLINICAL)
        return cls.CLINICAL


class InsuranceTable(str, Enum):
    """
    Pricing tables used by Brazilian health insurers.

    Maps to PricingTableType but uses common insurance terminology.
    """

    SUS = "SUS"  # Sistema Unico de Saude
    AMB = "AMB"  # Associacao Medica Brasileira
    CBHPM = "CBHPM"  # Classificacao Brasileira Hierarquizada de Procedimentos Medicos
    BRASINDICE = "BRASINDICE"  # Price reference for medicines
    SIMPRO = "SIMPRO"  # Price reference for hospital supplies
    CUSTOM = "CUSTOM"  # Custom pricing table


class PricedItem(BaseModel):
    """
    A priced procedure item from contract rules application.

    Used as input to claim generation when priced items are pre-computed.
    """

    procedure_code: str = Field(..., alias="procedureCode")
    description: Optional[str] = None
    procedure_type: str = Field("CLINICAL", alias="procedureType")
    quantity: int = Field(1, ge=1)
    unit_price: Decimal = Field(..., alias="unitPrice", ge=0)
    total_price: Decimal = Field(..., alias="totalPrice", ge=0)

    @field_validator("unit_price", "total_price", mode="before")
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


class ClaimLineItem(BaseModel):
    """
    A single line item in a claim.

    Represents a procedure or service being billed.
    """

    line_number: int = Field(..., alias="lineNumber", ge=1)
    procedure_code: str = Field(..., alias="procedureCode")
    description: Optional[str] = None
    procedure_type: str = Field("CLINICAL", alias="procedureType")
    quantity: int = Field(1, ge=1)
    unit_price: Decimal = Field(..., alias="unitPrice", ge=0)
    total_price: Decimal = Field(..., alias="totalPrice", ge=0)

    @field_validator("unit_price", "total_price", mode="before")
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
        "json_encoders": {Decimal: lambda v: float(round(v, 2))},
    }


class GenerateClaimInput(BaseModel):
    """
    Input model for claim generation (GenerateClaimWorker).

    Validates all required fields for TISS claim creation.
    """

    encounter_id: str = Field(..., alias="encounterId", min_length=1)
    patient_id: str = Field(..., alias="patientId", min_length=1)
    payer_id: Optional[str] = Field(None, alias="payerId")
    insurance_id: Optional[str] = Field(None, alias="insuranceId")
    procedure_codes: List[str] = Field(..., alias="procedureCodes", min_length=1)
    claim_type: ClaimType = Field(ClaimType.SP_SADT, alias="claimType")
    priced_items: Optional[List[PricedItem]] = Field(None, alias="pricedItems")
    authorization_number: Optional[str] = Field(None, alias="authorizationNumber")
    has_glosa: bool = Field(False, alias="hasGlosa")
    glosa_percentage: float = Field(0.0, alias="glosaPercentage", ge=0.0, le=100.0)

    # Optional patient information for TISS XML
    patient_name: Optional[str] = Field(None, alias="patientName")
    patient_cpf: Optional[str] = Field(None, alias="patientCpf")
    patient_card_number: Optional[str] = Field(None, alias="patientCardNumber")

    # Optional provider information
    provider_cnes: Optional[str] = Field(None, alias="providerCnes")
    provider_name: Optional[str] = Field(None, alias="providerName")

    # Service date
    service_date: Optional[datetime] = Field(None, alias="serviceDate")

    @field_validator("procedure_codes")
    @classmethod
    def validate_procedure_codes(cls, v: List[str]) -> List[str]:
        """Validate each procedure code format (TUSS or CBHPM)."""
        validated_codes = []
        for code in v:
            if not code or not code.strip():
                raise ValueError("Procedure code cannot be empty")

            code = code.strip()

            if not (TUSS_PATTERN.match(code) or CBHPM_PATTERN.match(code)):
                raise ValueError(
                    f"Invalid procedure code format: {code}. "
                    f"Expected TUSS (8 digits) or CBHPM (X.XX.XX.XX-X)"
                )
            validated_codes.append(code)
        return validated_codes

    @model_validator(mode="after")
    def validate_glosa_consistency(self) -> "GenerateClaimInput":
        """Ensure glosa percentage is set only when hasGlosa is true."""
        if not self.has_glosa and self.glosa_percentage > 0:
            self.has_glosa = True
        return self

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "encounterId": "ENC-2026-001234",
                    "patientId": "PAT-789456",
                    "procedureCodes": ["10101012", "20101015"],
                    "claimType": "SP_SADT",
                    "insuranceId": "INS-UNIMED-001",
                },
            ]
        },
    }


class ValidationMessage(BaseModel):
    """
    A validation message from XML validation.
    """

    level: str = Field("WARNING")  # ERROR, WARNING, INFO
    code: Optional[str] = None
    message: str
    location: Optional[str] = None


class GenerateClaimOutput(BaseModel):
    """
    Output model for claim generation (GenerateClaimWorker).

    Contains the generated claim ID, amounts, and TISS XML.
    """

    claim_id: str = Field(..., alias="claimId")
    claim_amount: Decimal = Field(..., alias="claimAmount", ge=0)
    claim_items_count: int = Field(..., alias="claimItemsCount", ge=0)
    claim_items: List[ClaimLineItem] = Field(..., alias="claimItems")
    claim_generated_date: datetime = Field(..., alias="claimGeneratedDate")

    # DMN calculation results
    billable_amount: Decimal = Field(..., alias="billableAmount", ge=0)
    discount_applied: Decimal = Field(..., alias="discountApplied", ge=0)
    final_claim_amount: Decimal = Field(..., alias="finalClaimAmount", ge=0)
    calculation_rule: str = Field(..., alias="calculationRule")
    needs_audit: bool = Field(False, alias="needsAudit")

    # TISS XML output
    tiss_xml: str = Field(..., alias="tissXml")
    validation_status: str = Field("VALID", alias="validationStatus")  # VALID, WARNINGS, ERRORS
    validation_messages: List[str] = Field(default_factory=list, alias="validationMessages")

    @field_validator("claim_amount", "billable_amount", "discount_applied", "final_claim_amount", mode="before")
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
        "json_encoders": {
            Decimal: lambda v: float(round(v, 2)),
            datetime: lambda v: v.isoformat(),
        },
    }


# =============================================================================
# Retry Submission Models
# =============================================================================


class RetrySubmissionInput(BaseModel):
    """
    Input model for RetrySubmissionWorker.

    Validates retry submission process variables with backoff calculation.
    """

    claim_id: str = Field(..., alias="claimId", min_length=1)
    previous_error: str = Field(..., alias="previousError", min_length=1)
    retry_count: int = Field(0, alias="retryCount", ge=0)
    max_retries: int = Field(3, alias="maxRetries", gt=0)

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "claimId": "CLM-2026-001",
                    "previousError": "Connection timeout",
                    "retryCount": 0,
                    "maxRetries": 3,
                }
            ]
        },
    }


class RetrySubmissionOutput(BaseModel):
    """
    Output model for RetrySubmissionWorker.

    Contains retry timing and status information with backoff delay.
    """

    retry_status: str = Field(..., alias="retryStatus")  # PENDING|PENDING_FINAL|MAX_RETRIES
    next_retry_at: datetime = Field(..., alias="nextRetryAt")
    retry_attempt: int = Field(..., alias="retryAttempt", ge=1)
    backoff_seconds: int = Field(..., alias="backoffSeconds", ge=1)
    is_final_attempt: bool = Field(False, alias="isFinalAttempt")
    claim_id: str = Field(..., alias="claimId")
    max_retries: int = Field(..., alias="maxRetries")

    model_config = {
        "populate_by_name": True,
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
        },
    }


# =============================================================================
# Update Status Models
# =============================================================================


class EntityType(str, Enum):
    """
    Types of entities that can have status updates.

    Attributes:
        CLAIM: Claim entity
        BILLING: Billing statement
        ENCOUNTER: Patient encounter
    """

    CLAIM = "CLAIM"
    BILLING = "BILLING"
    ENCOUNTER = "ENCOUNTER"


class UpdateStatusInput(BaseModel):
    """
    Input model for UpdateStatusWorker.

    Validates status change request with state machine constraints.
    """

    entity_id: str = Field(..., alias="entityId", min_length=1)
    entity_type: str = Field(..., alias="entityType", min_length=1)
    current_status: str = Field(..., alias="currentStatus", min_length=1)
    new_status: str = Field(..., alias="newStatus", min_length=1)
    reason: str = Field(..., min_length=1)

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "entityId": "CLM-2026-001",
                    "entityType": "CLAIM",
                    "currentStatus": "PENDING",
                    "newStatus": "IN_PROGRESS",
                    "reason": "Submission initiated",
                }
            ]
        },
    }


class UpdateStatusOutput(BaseModel):
    """
    Output model for UpdateStatusWorker.

    Contains status change details and audit trail information.
    """

    previous_status: str = Field(..., alias="previousStatus")
    current_status: str = Field(..., alias="currentStatus")
    status_change_date: datetime = Field(..., alias="statusChangeDate")
    audit_trail_id: str = Field(..., alias="auditTrailId")
    entity_id: str = Field(..., alias="entityId")
    entity_type: str = Field(..., alias="entityType")
    reason: str
    audit_entry: dict[str, Any] = Field(..., alias="auditEntry")

    model_config = {
        "populate_by_name": True,
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
        },
    }
