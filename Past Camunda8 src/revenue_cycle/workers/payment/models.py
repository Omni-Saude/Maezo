"""
Pydantic models for payment workers input/output validation.

These models provide type-safe validation for payment recording,
reconciliation, and payment-related Camunda process variables.

Follows CPC 25 accounting standards for revenue recognition.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class PayerType(str, Enum):
    """
    Types of payers in the revenue cycle.

    Attributes:
        INSURANCE: Health insurance/convênio payment
        PATIENT: Direct patient payment
        COLLECTION_AGENCY: Payment via collection agency
        GOVERNMENT: SUS or other government payment
    """

    INSURANCE = "INSURANCE"
    PATIENT = "PATIENT"
    COLLECTION_AGENCY = "COLLECTION_AGENCY"
    GOVERNMENT = "GOVERNMENT"


class PaymentMethod(str, Enum):
    """
    Payment methods accepted in Brazilian healthcare.

    Attributes:
        PIX: Instant payment system
        BOLETO: Bank slip
        CREDIT_CARD: Credit card
        DEBIT_CARD: Debit card
        BANK_TRANSFER: Wire transfer/TED/DOC
        INSURANCE_REMITTANCE: Insurance remittance file
        CASH: Cash payment
        CHECK: Check payment
    """

    PIX = "PIX"
    BOLETO = "BOLETO"
    CREDIT_CARD = "CREDIT_CARD"
    DEBIT_CARD = "DEBIT_CARD"
    BANK_TRANSFER = "BANK_TRANSFER"
    INSURANCE_REMITTANCE = "INSURANCE_REMITTANCE"
    CASH = "CASH"
    CHECK = "CHECK"


class PaymentStatus(str, Enum):
    """
    Status of a payment after recording.

    Attributes:
        COMPLETE: Full payment received
        PARTIAL: Partial payment received
        PENDING_RECONCILIATION: Payment received but needs reconciliation
        OVERPAYMENT: Payment exceeds claim amount
        REVERSED: Payment was reversed/refunded
    """

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    PENDING_RECONCILIATION = "PENDING_RECONCILIATION"
    OVERPAYMENT = "OVERPAYMENT"
    REVERSED = "REVERSED"


class RecordPaymentInput(BaseModel):
    """
    Input model for RecordPaymentWorker.

    Validates all required fields for payment recording with accounting integration.
    """

    payment_id: str = Field(
        ...,
        alias="paymentId",
        min_length=1,
        description="Unique payment identifier (for idempotency)",
    )
    claim_id: str = Field(
        ...,
        alias="claimId",
        min_length=1,
        description="Associated claim identifier",
    )
    payer_type: PayerType = Field(
        ...,
        alias="payerType",
        description="Type of payer making payment",
    )
    payment_amount: Decimal = Field(
        ...,
        alias="paymentAmount",
        gt=0,
        description="Payment amount received",
    )
    payment_date: datetime = Field(
        ...,
        alias="paymentDate",
        description="Date payment was received",
    )
    payment_method: PaymentMethod = Field(
        ...,
        alias="paymentMethod",
        description="Method of payment",
    )
    remittance_reference: Optional[str] = Field(
        None,
        alias="remittanceReference",
        description="Remittance file reference (for insurance payments)",
    )
    partial_payment: bool = Field(
        False,
        alias="partialPayment",
        description="Whether this is a partial payment",
    )

    # Optional fields
    claim_amount: Optional[Decimal] = Field(
        None,
        alias="claimAmount",
        description="Original claim amount (for validation)",
    )
    previous_payments: Optional[Decimal] = Field(
        None,
        alias="previousPayments",
        description="Sum of previous payments on this claim",
    )
    payer_id: Optional[str] = Field(
        None,
        alias="payerId",
        description="Payer organization identifier",
    )
    payer_name: Optional[str] = Field(
        None,
        alias="payerName",
        description="Payer organization name",
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Additional payment notes",
    )
    accounting_period: Optional[str] = Field(
        None,
        alias="accountingPeriod",
        description="Accounting period (YYYY-MM format)",
    )

    # Multi-tenant support
    tenant_id: Optional[str] = Field(
        None,
        alias="tenantId",
        description="Tenant identifier",
    )

    @field_validator("payment_amount", "claim_amount", "previous_payments", mode="before")
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

    @field_validator("payment_date", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> datetime:
        """Parse datetime from various formats."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            # Try ISO format first
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                # Try common formats
                from dateutil import parser
                return parser.parse(v)
        raise ValueError(f"Cannot convert {type(v).__name__} to datetime")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "paymentId": "PAY-2026-001234",
                    "claimId": "CLM-2026-005678",
                    "payerType": "INSURANCE",
                    "paymentAmount": "15000.00",
                    "paymentDate": "2026-02-04T10:30:00Z",
                    "paymentMethod": "INSURANCE_REMITTANCE",
                    "remittanceReference": "REM-20260204-001",
                    "partialPayment": False,
                }
            ]
        },
    }


class RecordPaymentOutput(BaseModel):
    """
    Output model for RecordPaymentWorker.

    Contains payment recording results, accounting references, and status.
    """

    payment_recorded: bool = Field(
        ...,
        alias="paymentRecorded",
        description="Whether payment was successfully recorded",
    )
    payment_status: PaymentStatus = Field(
        ...,
        alias="paymentStatus",
        description="Status of the payment",
    )
    remaining_balance: Decimal = Field(
        ...,
        alias="remainingBalance",
        ge=0,
        description="Remaining balance on the claim",
    )
    accounting_reference: str = Field(
        ...,
        alias="accountingReference",
        description="Accounting entry reference (journal entry ID)",
    )
    receipt_number: str = Field(
        ...,
        alias="receiptNumber",
        description="Payment receipt number",
    )

    # Additional details
    payment_amount: Decimal = Field(
        ...,
        alias="paymentAmount",
        description="Amount recorded",
    )
    claim_amount: Decimal = Field(
        ...,
        alias="claimAmount",
        description="Original claim amount",
    )
    total_payments: Decimal = Field(
        ...,
        alias="totalPayments",
        description="Total payments received (including this one)",
    )
    overpayment_amount: Optional[Decimal] = Field(
        None,
        alias="overpaymentAmount",
        description="Overpayment amount if any",
    )
    accounting_period: str = Field(
        ...,
        alias="accountingPeriod",
        description="Accounting period used (YYYY-MM)",
    )
    recorded_date: datetime = Field(
        ...,
        alias="recordedDate",
        description="Timestamp when payment was recorded",
    )

    # Compensation support
    compensation_reference: Optional[str] = Field(
        None,
        alias="compensationReference",
        description="Reference for SAGA compensation/reversal",
    )

    @field_validator("remaining_balance", "payment_amount", "claim_amount", "total_payments", "overpayment_amount", mode="before")
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
        },
        "json_schema_extra": {
            "examples": [
                {
                    "paymentRecorded": True,
                    "paymentStatus": "COMPLETE",
                    "remainingBalance": "0.00",
                    "accountingReference": "JE-PAY-2026-001234",
                    "receiptNumber": "REC-2026-001234",
                    "paymentAmount": "15000.00",
                    "claimAmount": "15000.00",
                    "totalPayments": "15000.00",
                    "accountingPeriod": "2026-02",
                    "recordedDate": "2026-02-04T10:30:00Z",
                }
            ]
        },
    }


class PaymentReconciliationData(BaseModel):
    """
    Data model for payment reconciliation tracking.

    Used internally to track reconciliation status.
    """

    payment_id: str
    claim_id: str
    expected_amount: Decimal
    received_amount: Decimal
    variance: Decimal
    reconciled: bool
    reconciliation_notes: Optional[str] = None

    @property
    def variance_percentage(self) -> Decimal:
        """Calculate variance as percentage of expected amount."""
        if self.expected_amount == 0:
            return Decimal("0")
        return (self.variance / self.expected_amount) * 100
