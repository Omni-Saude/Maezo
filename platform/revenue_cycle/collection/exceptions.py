"""Domain exceptions for Revenue Collection subprocess."""
from __future__ import annotations

from platform.shared.domain.exceptions import DomainException


class CollectionException(DomainException):
    """Base exception for collection subprocess."""
    bpmn_error_code: str = "COLLECTION_ERROR"


class PaymentValidationError(CollectionException):
    """Payment data failed validation."""
    bpmn_error_code: str = "PAYMENT_VALIDATION_FAILED"


class DuplicatePaymentError(CollectionException):
    """Duplicate payment detected."""
    bpmn_error_code: str = "DUPLICATE_PAYMENT"


class PaymentAllocationError(CollectionException):
    """Payment could not be allocated to claims."""
    bpmn_error_code: str = "PAYMENT_ALLOCATION_FAILED"


class CNABParsingError(CollectionException):
    """CNAB file parsing failed."""
    bpmn_error_code: str = "CNAB_PARSING_ERROR"


class ReconciliationError(CollectionException):
    """Reconciliation process failed."""
    bpmn_error_code: str = "RECONCILIATION_ERROR"


class OverpaymentError(CollectionException):
    """Overpayment detected — requires manual review."""
    bpmn_error_code: str = "OVERPAYMENT_DETECTED"


class UnderpaymentError(CollectionException):
    """Underpayment / glosa residual detected."""
    bpmn_error_code: str = "UNDERPAYMENT_DETECTED"


class UnmatchedPaymentError(CollectionException):
    """Payment could not be matched to any claim."""
    bpmn_error_code: str = "UNMATCHED_PAYMENT"


class ERPSyncError(CollectionException):
    """Failed to sync with ERP (Tasy/MV Soul)."""
    bpmn_error_code: str = "ERP_SYNC_ERROR"
    retryable: bool = True


class CollectionLetterError(CollectionException):
    """Failed to generate or send collection letter."""
    bpmn_error_code: str = "COLLECTION_LETTER_ERROR"


class PenaltyCalculationError(CollectionException):
    """Failed to calculate late fees/penalties."""
    bpmn_error_code: str = "PENALTY_CALCULATION_ERROR"


class WriteOffError(CollectionException):
    """Write-off validation failed."""
    bpmn_error_code: str = "WRITE_OFF_ERROR"
