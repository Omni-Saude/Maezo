"""
Pydantic models for medical coding operations.

Provides type-safe validation for ICD-10, TUSS codes, and medical coding audit results.
Follows Brazilian healthcare standards (ANS TISS, CFM, CBHPM).
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AuditResult(str, Enum):
    """Results of medical coding audit."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


class CodeType(str, Enum):
    """Types of medical codes."""

    ICD10 = "ICD10"
    TUSS = "TUSS"
    DRG = "DRG"
    CBHPM = "CBHPM"


class AuditFinding(BaseModel):
    """Individual audit finding for a code."""

    model_config = ConfigDict(populate_by_name=True)

    code: str = Field(
        ...,
        min_length=1,
        description="Medical code being audited",
    )
    code_type: CodeType = Field(
        ...,
        alias="codeType",
        description="Type of code (ICD10, TUSS, DRG, CBHPM)",
    )
    finding_type: str = Field(
        ...,
        alias="findingType",
        min_length=1,
        description="Type of finding (INVALID_CODE, INCOMPATIBLE_TUSS, DRG_MISMATCH, etc.)",
    )
    severity: str = Field(
        default="ERROR",
        min_length=1,
        description="Severity level (ERROR, WARNING, INFO)",
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Human-readable finding message",
    )
    suggested_correction: Optional[str] = Field(
        None,
        alias="suggestedCorrection",
        description="Suggested correction if applicable",
    )
    reference: Optional[str] = Field(
        None,
        description="Reference to regulatory document or rule",
    )


class SuggestedCode(BaseModel):
    """Suggested code with confidence score."""

    model_config = ConfigDict(populate_by_name=True)

    code: str = Field(
        ...,
        min_length=1,
        description="Suggested code",
    )
    code_type: CodeType = Field(
        ...,
        alias="codeType",
        description="Type of code",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Code description",
    )
    confidence: Decimal = Field(
        ...,
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Confidence score (0.0 to 1.0)",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Reason for suggestion",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def parse_decimal_confidence(cls, v: Any) -> Decimal:
        """Parse confidence from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")


class AssignCodesInput(BaseModel):
    """Input for AssignCodesWorker."""

    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(
        ...,
        alias="encounterId",
        min_length=1,
        description="Unique encounter identifier",
    )
    clinical_notes: str = Field(
        ...,
        alias="clinicalNotes",
        min_length=1,
        description="Clinical documentation with diagnoses and findings",
    )
    procedures: list[str] = Field(
        default_factory=list,
        min_items=0,
        description="List of procedures performed",
    )
    diagnoses: list[str] = Field(
        default_factory=list,
        min_items=0,
        description="List of diagnoses from clinical notes",
    )
    patient_age: Optional[int] = Field(
        None,
        alias="patientAge",
        ge=0,
        le=150,
        description="Patient age for age-specific coding rules",
    )
    admission_type: Optional[str] = Field(
        None,
        alias="admissionType",
        description="Type of admission (EMERGENCY, ELECTIVE, etc.)",
    )
    discharge_status: Optional[str] = Field(
        None,
        alias="dischargeStatus",
        description="Discharge status (DISCHARGED, EXPIRED, etc.)",
    )

    @field_validator("encounter_id", "clinical_notes")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        """Validate required text fields are not empty after strip."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()


class AssignCodesOutput(BaseModel):
    """Output from AssignCodesWorker."""

    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(
        ...,
        alias="encounterId",
        description="Encounter identifier from input",
    )
    icd10_codes: list[str] = Field(
        default_factory=list,
        alias="icd10Codes",
        description="Assigned ICD-10 diagnosis and procedure codes",
    )
    tuss_codes: list[str] = Field(
        default_factory=list,
        alias="tussCodes",
        description="Assigned TUSS procedure codes (Brazilian standard)",
    )
    drg_code: Optional[str] = Field(
        None,
        alias="drgCode",
        description="DRG code if applicable",
    )
    coding_confidence: Decimal = Field(
        default=Decimal("0.85"),
        alias="codingConfidence",
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Overall coding confidence score",
    )
    suggested_codes: list[SuggestedCode] = Field(
        default_factory=list,
        alias="suggestedCodes",
        description="Additional suggested codes with confidence scores",
    )
    coding_notes: Optional[str] = Field(
        None,
        alias="codingNotes",
        description="Additional notes from coder about coding decisions",
    )
    requires_review: bool = Field(
        default=False,
        alias="requiresReview",
        description="Whether coding requires physician review",
    )
    coding_rules_applied: list[str] = Field(
        default_factory=list,
        alias="codingRulesApplied",
        description="List of coding rules applied (audit trail)",
    )

    @field_validator("coding_confidence", mode="before")
    @classmethod
    def parse_decimal_confidence(cls, v: Any) -> Decimal:
        """Parse confidence from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")


class AuditRulesInput(BaseModel):
    """Input for AuditRulesWorker."""

    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(
        ...,
        alias="encounterId",
        min_length=1,
        description="Unique encounter identifier",
    )
    assigned_codes: dict[str, list[str]] = Field(
        ...,
        alias="assignedCodes",
        description="Codes by type: {'icd10': [...], 'tuss': [...], 'drg': [...]}",
    )
    coder_user_id: str = Field(
        ...,
        alias="coderUserId",
        min_length=1,
        description="ID of the coder who assigned codes",
    )
    patient_age: Optional[int] = Field(
        None,
        alias="patientAge",
        ge=0,
        le=150,
        description="Patient age for validation",
    )
    admission_type: Optional[str] = Field(
        None,
        alias="admissionType",
        description="Admission type for validation",
    )
    drg_weight: Optional[Decimal] = Field(
        None,
        alias="drgWeight",
        ge=Decimal("0"),
        description="DRG weight for validation",
    )

    @field_validator("encounter_id", "coder_user_id")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        """Validate required text fields."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()

    @field_validator("drg_weight", mode="before")
    @classmethod
    def parse_decimal_weight(cls, v: Any) -> Optional[Decimal]:
        """Parse weight from various formats."""
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")


class AuditRulesOutput(BaseModel):
    """Output from AuditRulesWorker."""

    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(
        ...,
        alias="encounterId",
        description="Encounter identifier from input",
    )
    audit_result: AuditResult = Field(
        ...,
        alias="auditResult",
        description="Overall audit result (PASS, FAIL, WARNING)",
    )
    findings: list[AuditFinding] = Field(
        default_factory=list,
        description="List of audit findings if any",
    )
    suggested_corrections: list[SuggestedCode] = Field(
        default_factory=list,
        alias="suggestedCorrections",
        description="Suggested code corrections",
    )
    audit_notes: Optional[str] = Field(
        None,
        alias="auditNotes",
        description="Additional audit notes",
    )
    requires_physician_review: bool = Field(
        default=False,
        alias="requiresPhysicianReview",
        description="Whether physician review is required",
    )
    audit_severity_level: str = Field(
        default="INFO",
        alias="auditSeverityLevel",
        description="Audit severity (INFO, WARNING, ERROR, CRITICAL)",
    )
    audit_rules_applied: list[str] = Field(
        default_factory=list,
        alias="auditRulesApplied",
        description="List of audit rules applied (audit trail)",
    )
    compliance_status: str = Field(
        default="COMPLIANT",
        alias="complianceStatus",
        description="ANS/TISS compliance status",
    )
