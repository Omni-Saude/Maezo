"""TISS/ANS integration data models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TissStatus(str, Enum):
    """TISS submission status."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    GLOSA = "glosa"


class TissGlosaType(str, Enum):
    """Types of glosas (denials)."""

    ADMINISTRATIVE = "administrative"  # Documentacao incorreta
    TECHNICAL = "technical"  # Procedimento nao autorizado
    CLINICAL = "clinical"  # Falta de justificativa clinica
    PRICING = "pricing"  # Valor divergente da tabela


class TissSubmissionResponse(BaseModel):
    """Response from TISS claim submission."""

    protocol_number: str = Field(description="ANS protocol number")
    batch_id: str = Field(description="Batch identifier")
    submission_date: datetime = Field(description="Submission timestamp")
    status: TissStatus = Field(description="Submission status")
    estimated_processing_days: int = Field(
        default=15,
        description="Estimated days until processing",
    )
    message: Optional[str] = Field(default=None, description="Response message")

    class Config:
        """Pydantic config."""

        frozen = False


class TissStatusResponse(BaseModel):
    """Status response for a TISS claim."""

    protocol_number: str = Field(description="ANS protocol number")
    status: TissStatus = Field(description="Current status")
    last_updated: datetime = Field(description="Last status update")
    glosa_count: int = Field(default=0, description="Number of glosas")
    approved_amount: Decimal = Field(default=Decimal(0), description="Approved amount")
    paid_amount: Decimal = Field(default=Decimal(0), description="Amount paid")
    glosa_amount: Decimal = Field(default=Decimal(0), description="Amount denied (glosa)")
    payment_date: Optional[datetime] = Field(default=None, description="Payment date if paid")
    observations: List[str] = Field(default_factory=list, description="Observations/notes")

    class Config:
        """Pydantic config."""

        frozen = False
        use_decimal = True


class TissGlosaDTO(BaseModel):
    """Glosa (denial) details from insurance."""

    glosa_id: str = Field(description="Glosa identifier")
    protocol_number: str = Field(description="Related protocol number")
    glosa_type: TissGlosaType = Field(description="Type of glosa")
    procedure_code: str = Field(description="Denied procedure code")
    procedure_description: str = Field(description="Procedure description")
    denied_amount: Decimal = Field(description="Amount denied")
    reason_code: str = Field(description="ANS reason code")
    reason_description: str = Field(description="Reason description")
    justification: Optional[str] = Field(default=None, description="Insurance justification")
    date_notified: datetime = Field(description="Date glosa was notified")
    appeal_deadline: datetime = Field(description="Deadline for appeal")
    is_appealable: bool = Field(default=True, description="Whether glosa can be appealed")

    class Config:
        """Pydantic config."""

        frozen = False
        use_decimal = True


class TissAppealRequest(BaseModel):
    """Glosa appeal submission."""

    glosa_id: str = Field(description="Glosa being appealed")
    protocol_number: str = Field(description="Original protocol number")
    appeal_reason: str = Field(description="Reason for appeal")
    clinical_justification: str = Field(description="Clinical justification")
    supporting_documents: List[str] = Field(
        default_factory=list,
        description="Document IDs/URLs for evidence",
    )
    medical_record_summary: str = Field(description="Summary of medical record")
    requested_amount: Decimal = Field(description="Amount being appealed")

    class Config:
        """Pydantic config."""

        frozen = False
        use_decimal = True


class TissAppealResponse(BaseModel):
    """Response from glosa appeal submission."""

    appeal_protocol: str = Field(description="Appeal protocol number")
    original_protocol: str = Field(description="Original claim protocol")
    glosa_id: str = Field(description="Glosa being appealed")
    submission_date: datetime = Field(description="Appeal submission date")
    status: str = Field(description="Appeal status")
    estimated_response_days: int = Field(
        default=30,
        description="Estimated days until response",
    )
    message: Optional[str] = Field(default=None, description="Response message")

    class Config:
        """Pydantic config."""

        frozen = False


class TissBatchSummary(BaseModel):
    """Summary of a TISS batch submission."""

    batch_id: str = Field(description="Batch identifier")
    submission_date: datetime = Field(description="Submission date")
    total_claims: int = Field(description="Number of claims in batch")
    total_amount: Decimal = Field(description="Total claimed amount")
    status: TissStatus = Field(description="Batch status")

    # Processing results
    accepted_claims: int = Field(default=0, description="Accepted claims")
    rejected_claims: int = Field(default=0, description="Rejected claims")
    claims_with_glosa: int = Field(default=0, description="Claims with glosas")

    # Financial summary
    approved_amount: Decimal = Field(default=Decimal(0), description="Approved amount")
    glosa_amount: Decimal = Field(default=Decimal(0), description="Total glosa amount")
    paid_amount: Decimal = Field(default=Decimal(0), description="Amount paid")

    class Config:
        """Pydantic config."""

        frozen = False
        use_decimal = True


class TissClaimDTO(BaseModel):
    """Single claim for TISS submission."""

    encounter_id: str = Field(description="Hospital encounter ID")
    patient_cpf: str = Field(description="Patient CPF")
    patient_name: str = Field(description="Patient name")
    insurance_card_number: str = Field(description="Insurance card number")
    insurance_name: str = Field(description="Insurance/payer name")

    # Clinical data
    primary_diagnosis_cid10: str = Field(description="Primary diagnosis CID-10 code")
    secondary_diagnoses: List[str] = Field(
        default_factory=list,
        description="Secondary diagnosis codes",
    )

    # Procedures
    procedure_codes: List[str] = Field(description="TUSS procedure codes")
    procedure_descriptions: List[str] = Field(description="Procedure descriptions")
    procedure_quantities: List[int] = Field(description="Quantities for each procedure")
    procedure_unit_prices: List[Decimal] = Field(description="Unit prices")

    # Dates
    service_date_start: datetime = Field(description="Start of service period")
    service_date_end: Optional[datetime] = Field(
        default=None,
        description="End of service period",
    )

    # Financial
    total_claimed_amount: Decimal = Field(description="Total amount claimed")

    # Metadata
    requesting_physician: Optional[str] = Field(default=None, description="Physician name")
    authorization_number: Optional[str] = Field(
        default=None,
        description="Prior authorization number",
    )

    class Config:
        """Pydantic config."""

        frozen = False
        use_decimal = True
