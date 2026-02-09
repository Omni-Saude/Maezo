"""
Pydantic models for worker input/output validation.

These models provide type-safe validation for Camunda process variables,
ensuring data integrity between the BPMN process and Python workers.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from revenue_cycle.domain import AppealStrategy, GlosaType, Priority
from revenue_cycle.validators.patient_id import validate_patient_id


class GlosaAnalysisInput(BaseModel):
    """
    Input model for AnalyzeGlosaWorker.

    Validates the process variables required for glosa analysis.
    """

    glosa_type: str = Field(
        ...,
        alias="glosaType",
        description="Type of glosa (FULL_DENIAL, PARTIAL_DENIAL, etc.)",
    )
    glosa_amount: Decimal = Field(
        ...,
        alias="glosaAmount",
        ge=0,
        description="Amount denied (must be non-negative)",
    )
    glosa_reason: Optional[str] = Field(
        None,
        alias="glosaReason",
        description="Reason for denial",
    )
    glosa_source: str = Field(
        "INSURANCE",
        alias="glosaSource",
        description="Source of glosa (INSURANCE, AUDIT, etc.)",
    )
    has_documentation: bool = Field(
        True,
        alias="hasDocumentation",
        description="Whether supporting documentation is available",
    )
    days_since_occurrence: int = Field(
        0,
        alias="daysSinceOccurrence",
        ge=0,
        description="Days since the glosa was identified",
    )

    @field_validator("glosa_amount", mode="before")
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

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "glosaType": "FULL_DENIAL",
                    "glosaAmount": "5000.00",
                    "glosaReason": "Missing prior authorization",
                },
            ]
        },
    }


class GlosaAnalysisOutput(BaseModel):
    """
    Output model for AnalyzeGlosaWorker.

    Defines the process variables returned after glosa analysis.
    """

    appeal_strategy: str = Field(
        ...,
        alias="appealStrategy",
        description="Recommended appeal strategy",
    )
    priority: str = Field(
        ...,
        alias="priority",
        description="Appeal priority (HIGH, MEDIUM, LOW)",
    )
    assigned_to: str = Field(
        ...,
        alias="assignedTo",
        description="Team/person assigned to handle appeal",
    )
    recovery_probability: int = Field(
        ...,
        alias="recoveryProbability",
        ge=0,
        le=100,
        description="Probability of recovering the denied amount (0-100%)",
    )
    glosa_analyzed: bool = Field(
        True,
        alias="glosaAnalyzed",
        description="Flag indicating analysis was completed",
    )
    deadline_days: Optional[int] = Field(
        None,
        alias="deadlineDays",
        description="Days until appeal deadline",
    )
    requires_legal: bool = Field(
        False,
        alias="requiresLegal",
        description="Whether legal review is required",
    )

    model_config = {
        "populate_by_name": True,
    }


class ClaimSubmissionInput(BaseModel):
    """
    Input model for claim submission workers.
    """

    claim_id: str = Field(..., alias="claimId", description="Unique claim identifier")
    patient_id: str = Field(..., alias="patientId", description="Patient identifier (CPF or CNJ)")
    encounter_id: str = Field(..., alias="encounterId", description="Encounter identifier")
    insurance_id: str = Field(..., alias="insuranceId", description="Insurance plan identifier")
    total_amount: Decimal = Field(
        ...,
        alias="totalAmount",
        ge=0,
        description="Total claim amount",
    )
    service_date: date = Field(..., alias="serviceDate", description="Date of service")
    procedures: list[str] = Field(
        default_factory=list,
        description="List of procedure codes",
    )
    diagnoses: list[str] = Field(
        default_factory=list,
        description="List of diagnosis codes (ICD-10)",
    )

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id_field(cls, v: str) -> str:
        """Validate patient ID format (CPF or CNJ)."""
        return validate_patient_id(v)

    @field_validator("total_amount", mode="before")
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

    model_config = {
        "populate_by_name": True,
    }


class PaymentProcessingInput(BaseModel):
    """
    Input model for payment processing workers.
    """

    payment_id: str = Field(..., alias="paymentId", description="Unique payment identifier")
    claim_id: str = Field(..., alias="claimId", description="Associated claim identifier")
    payment_amount: Decimal = Field(
        ...,
        alias="paymentAmount",
        ge=0,
        description="Payment amount",
    )
    payment_date: date = Field(..., alias="paymentDate", description="Payment date")
    payment_method: str = Field(
        "BANK_TRANSFER",
        alias="paymentMethod",
        description="Payment method (BANK_TRANSFER, CREDIT_CARD, etc.)",
    )
    payer_reference: Optional[str] = Field(
        None,
        alias="payerReference",
        description="Payer's reference number",
    )

    @field_validator("payment_amount", mode="before")
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

    model_config = {
        "populate_by_name": True,
    }


class NotificationInput(BaseModel):
    """
    Input model for notification workers.
    """

    recipient_id: str = Field(..., alias="recipientId", description="Recipient identifier")
    recipient_type: str = Field(
        "PATIENT",
        alias="recipientType",
        description="Recipient type (PATIENT, PROVIDER, STAFF)",
    )
    notification_type: str = Field(
        ...,
        alias="notificationType",
        description="Type of notification (APPOINTMENT_REMINDER, PAYMENT_DUE, etc.)",
    )
    channel: str = Field(
        "WHATSAPP",
        alias="channel",
        description="Notification channel (WHATSAPP, EMAIL, SMS)",
    )
    template_id: Optional[str] = Field(
        None,
        alias="templateId",
        description="Message template identifier",
    )
    template_variables: dict[str, Any] = Field(
        default_factory=dict,
        alias="templateVariables",
        description="Variables to substitute in template",
    )
    scheduled_at: Optional[datetime] = Field(
        None,
        alias="scheduledAt",
        description="Scheduled send time (if not immediate)",
    )

    model_config = {
        "populate_by_name": True,
    }


class NotificationOutput(BaseModel):
    """
    Output model for notification workers.
    """

    notification_sent: bool = Field(
        ...,
        alias="notificationSent",
        description="Whether notification was sent successfully",
    )
    message_id: Optional[str] = Field(
        None,
        alias="messageId",
        description="External message identifier",
    )
    sent_at: Optional[datetime] = Field(
        None,
        alias="sentAt",
        description="Actual send timestamp",
    )
    delivery_status: str = Field(
        "PENDING",
        alias="deliveryStatus",
        description="Delivery status (PENDING, DELIVERED, FAILED)",
    )

    model_config = {
        "populate_by_name": True,
    }
