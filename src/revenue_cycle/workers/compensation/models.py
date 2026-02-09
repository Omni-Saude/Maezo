"""
Pydantic models for SAGA compensation workers.

These models provide type-safe validation for compensation operations
that reverse previously executed business transactions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class CompensationStatus(str, Enum):
    """
    Status of compensation operation.

    Attributes:
        SUCCESS: Compensation completed successfully
        FAILED: Compensation failed
        PARTIAL: Compensation partially completed
        SKIPPED: Compensation skipped (operation not found)
        ALREADY_COMPENSATED: Operation already compensated
    """

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"
    ALREADY_COMPENSATED = "ALREADY_COMPENSATED"


class CompensationReason(str, Enum):
    """
    Reason for compensation operation.

    Attributes:
        TRANSACTION_FAILED: Parent transaction failed
        BUSINESS_ERROR: Business rule violation
        TIMEOUT: Operation timeout
        MANUAL_ROLLBACK: Manual intervention required
        SYSTEM_ERROR: System/technical error
    """

    TRANSACTION_FAILED = "TRANSACTION_FAILED"
    BUSINESS_ERROR = "BUSINESS_ERROR"
    TIMEOUT = "TIMEOUT"
    MANUAL_ROLLBACK = "MANUAL_ROLLBACK"
    SYSTEM_ERROR = "SYSTEM_ERROR"


# ========================================================================
# Reverse Payment Models
# ========================================================================


class ReversePaymentInput(BaseModel):
    """Input model for ReversePaymentWorker."""

    transaction_id: str = Field(
        ...,
        alias="transactionId",
        min_length=1,
        description="Original payment transaction ID to reverse",
    )
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
    payment_amount: Decimal = Field(
        ...,
        alias="paymentAmount",
        gt=0,
        description="Payment amount to reverse",
    )
    reason: CompensationReason = Field(
        ...,
        description="Reason for reversal",
    )
    notes: Optional[str] = Field(
        None,
        max_length=500,
        description="Additional reversal notes",
    )

    @field_validator("payment_amount", mode="before")
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

    model_config = {"populate_by_name": True}


class ReversePaymentOutput(BaseModel):
    """Output model for ReversePaymentWorker."""

    reversal_success: bool = Field(
        ...,
        alias="reversalSuccess",
        description="Whether reversal was successful",
    )
    reversal_transaction_id: str = Field(
        ...,
        alias="reversalTransactionId",
        description="New reversal transaction ID",
    )
    compensation_status: CompensationStatus = Field(
        ...,
        alias="compensationStatus",
        description="Compensation operation status",
    )
    reversed_amount: Decimal = Field(
        ...,
        alias="reversedAmount",
        description="Amount successfully reversed",
    )
    reversal_date: datetime = Field(
        ...,
        alias="reversalDate",
        description="When reversal was executed",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Error message if failed",
    )

    model_config = {"populate_by_name": True}


# ========================================================================
# Cancel Claim Models
# ========================================================================


class CancelClaimInput(BaseModel):
    """Input model for CancelClaimWorker."""

    claim_id: str = Field(
        ...,
        alias="claimId",
        min_length=1,
        description="Claim identifier to cancel",
    )
    encounter_id: str = Field(
        ...,
        alias="encounterId",
        min_length=1,
        description="Associated encounter identifier",
    )
    patient_id: str = Field(
        ...,
        alias="patientId",
        min_length=1,
        description="Patient identifier",
    )
    reason: CompensationReason = Field(
        ...,
        description="Reason for cancellation",
    )
    cancel_note: Optional[str] = Field(
        None,
        alias="cancelNote",
        max_length=500,
        description="Cancellation notes",
    )

    model_config = {"populate_by_name": True}


class CancelClaimOutput(BaseModel):
    """Output model for CancelClaimWorker."""

    cancellation_success: bool = Field(
        ...,
        alias="cancellationSuccess",
        description="Whether cancellation was successful",
    )
    compensation_status: CompensationStatus = Field(
        ...,
        alias="compensationStatus",
        description="Compensation operation status",
    )
    cancellation_id: str = Field(
        ...,
        alias="cancellationId",
        description="Cancellation record ID",
    )
    cancellation_date: datetime = Field(
        ...,
        alias="cancellationDate",
        description="When cancellation was executed",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Error message if failed",
    )

    model_config = {"populate_by_name": True}


# ========================================================================
# Rollback Allocation Models
# ========================================================================


class RollbackAllocationInput(BaseModel):
    """Input model for RollbackAllocationWorker."""

    allocation_id: str = Field(
        ...,
        alias="allocationId",
        min_length=1,
        description="Payment allocation ID to rollback",
    )
    payment_id: str = Field(
        ...,
        alias="paymentId",
        min_length=1,
        description="Associated payment identifier",
    )
    claim_id: str = Field(
        ...,
        alias="claimId",
        min_length=1,
        description="Claim identifier",
    )
    allocated_amount: Decimal = Field(
        ...,
        alias="allocatedAmount",
        gt=0,
        description="Amount that was allocated",
    )
    reason: CompensationReason = Field(
        ...,
        description="Reason for rollback",
    )

    @field_validator("allocated_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {"populate_by_name": True}


class RollbackAllocationOutput(BaseModel):
    """Output model for RollbackAllocationWorker."""

    rollback_success: bool = Field(
        ...,
        alias="rollbackSuccess",
        description="Whether rollback was successful",
    )
    compensation_status: CompensationStatus = Field(
        ...,
        alias="compensationStatus",
        description="Compensation operation status",
    )
    unallocated_amount: Optional[Decimal] = Field(
        None,
        alias="unallocatedAmount",
        description="Amount successfully unallocated",
    )
    released_amount: Optional[Decimal] = Field(
        None,
        alias="releasedAmount",
        description="Amount successfully released (same as unallocated_amount)",
    )
    rollback_date: datetime = Field(
        ...,
        alias="rollbackDate",
        description="When rollback was executed",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Error message if failed",
    )
    allocation_id: Optional[str] = Field(
        None,
        alias="allocationId",
        description="Allocation ID for reference",
    )

    @field_validator("released_amount", mode="before")
    @classmethod
    def set_released_from_unallocated(cls, v: Any, info) -> Optional[Decimal]:
        """If released_amount not set, use unallocated_amount."""
        if v is None and "unallocated_amount" in info.data:
            return info.data["unallocated_amount"]
        return v

    model_config = {"populate_by_name": True}


# ========================================================================
# Undo Billing Models
# ========================================================================


class UndoBillingInput(BaseModel):
    """Input model for UndoBillingWorker."""

    billing_id: str = Field(
        ...,
        alias="billingId",
        min_length=1,
        description="Billing entry ID to undo",
    )
    claim_id: str = Field(
        ...,
        alias="claimId",
        min_length=1,
        description="Associated claim identifier",
    )
    encounter_id: str = Field(
        ...,
        alias="encounterId",
        min_length=1,
        description="Associated encounter identifier",
    )
    billing_amount: Decimal = Field(
        ...,
        alias="billingAmount",
        gt=0,
        description="Billing amount to undo",
    )
    reason: CompensationReason = Field(
        ...,
        description="Reason for undo",
    )

    @field_validator("billing_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {"populate_by_name": True}


class UndoBillingOutput(BaseModel):
    """Output model for UndoBillingWorker."""

    undo_success: bool = Field(
        ...,
        alias="undoSuccess",
        description="Whether undo was successful",
    )
    compensation_status: CompensationStatus = Field(
        ...,
        alias="compensationStatus",
        description="Compensation operation status",
    )
    reversal_entry_id: str = Field(
        ...,
        alias="reversalEntryId",
        description="Reversal entry ID in accounting",
    )
    reversed_amount: Decimal = Field(
        default=Decimal("0.00"),
        alias="reversedAmount",
        description="Amount that was reversed",
    )
    undo_date: datetime = Field(
        ...,
        alias="undoDate",
        description="When undo was executed",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Error message if failed",
    )

    model_config = {"populate_by_name": True}


# ========================================================================
# Revert Eligibility Models
# ========================================================================


class RevertEligibilityInput(BaseModel):
    """Input model for RevertEligibilityWorker."""

    eligibility_check_id: str = Field(
        ...,
        alias="eligibilityCheckId",
        min_length=1,
        description="Eligibility check ID to revert",
    )
    patient_id: str = Field(
        ...,
        alias="patientId",
        min_length=1,
        description="Patient identifier",
    )
    insurance_id: str = Field(
        ...,
        alias="insuranceId",
        min_length=1,
        description="Insurance identifier",
    )
    reason: CompensationReason = Field(
        ...,
        description="Reason for revert",
    )

    model_config = {"populate_by_name": True}


class RevertEligibilityOutput(BaseModel):
    """Output model for RevertEligibilityWorker."""

    reversion_success: bool = Field(
        ...,
        alias="reversionSuccess",
        description="Whether reversion was successful",
    )
    compensation_status: CompensationStatus = Field(
        ...,
        alias="compensationStatus",
        description="Compensation operation status",
    )
    reversion_date: datetime = Field(
        ...,
        alias="reversionDate",
        description="When reversion was executed",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Error message if failed",
    )
    eligibility_id: Optional[str] = Field(
        None,
        alias="eligibilityId",
        description="Eligibility check ID for reference",
    )

    # Legacy aliases for backward compatibility
    @property
    def revert_success(self) -> bool:
        """Alias for reversion_success for backward compatibility."""
        return self.reversion_success

    @property
    def revert_date(self) -> datetime:
        """Alias for reversion_date for backward compatibility."""
        return self.reversion_date

    model_config = {"populate_by_name": True}


# ========================================================================
# Cancel Notification Models
# ========================================================================


class CancelNotificationInput(BaseModel):
    """Input model for CancelNotificationWorker."""

    notification_id: str = Field(
        ...,
        alias="notificationId",
        min_length=1,
        description="Notification ID to cancel",
    )
    recipient: str = Field(
        ...,
        min_length=1,
        description="Notification recipient (email/phone)",
    )
    notification_type: str = Field(
        ...,
        alias="notificationType",
        description="Type of notification (EMAIL, SMS, PUSH)",
    )
    reason: CompensationReason = Field(
        ...,
        description="Reason for cancellation",
    )

    model_config = {"populate_by_name": True}


class CancelNotificationOutput(BaseModel):
    """Output model for CancelNotificationWorker."""

    cancellation_success: bool = Field(
        ...,
        alias="cancellationSuccess",
        description="Whether cancellation was successful",
    )
    compensation_status: CompensationStatus = Field(
        ...,
        alias="compensationStatus",
        description="Compensation operation status",
    )
    cancellation_date: datetime = Field(
        ...,
        alias="cancellationDate",
        description="When cancellation was executed",
    )
    was_already_sent: bool = Field(
        ...,
        alias="wasAlreadySent",
        description="Whether notification was already sent",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Error message if failed",
    )

    model_config = {"populate_by_name": True}


# ========================================================================
# Abort Collection Models
# ========================================================================


class AbortCollectionInput(BaseModel):
    """Input model for AbortCollectionWorker."""

    collection_id: str = Field(
        ...,
        alias="collectionId",
        min_length=1,
        description="Collection process ID to abort",
    )
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
    outstanding_amount: Decimal = Field(
        ...,
        alias="outstandingAmount",
        gt=0,
        description="Outstanding collection amount",
    )
    reason: CompensationReason = Field(
        ...,
        description="Reason for abort",
    )

    @field_validator("outstanding_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {"populate_by_name": True}


class AbortCollectionOutput(BaseModel):
    """Output model for AbortCollectionWorker."""

    abort_success: bool = Field(
        ...,
        alias="abortSuccess",
        description="Whether abort was successful",
    )
    compensation_status: CompensationStatus = Field(
        ...,
        alias="compensationStatus",
        description="Compensation operation status",
    )
    abort_date: datetime = Field(
        ...,
        alias="abortDate",
        description="When abort was executed",
    )
    collection_was_active: bool = Field(
        ...,
        alias="collectionWasActive",
        description="Whether collection was still active",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Error message if failed",
    )
    collection_id: Optional[str] = Field(
        None,
        alias="collectionId",
        description="Collection ID for reference",
    )
    aborted_items_count: Optional[int] = Field(
        None,
        alias="abortedItemsCount",
        description="Number of collection items aborted",
    )

    # Support both naming conventions for backward compatibility
    @property
    def abortion_success(self) -> bool:
        """Alias for abort_success for backward compatibility."""
        return self.abort_success

    model_config = {"populate_by_name": True}
