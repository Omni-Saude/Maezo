"""
Base domain exceptions for Hospital Revenue Cycle.

These exceptions provide a hierarchy for handling different
types of errors in the domain layer, with BPMN error mapping.
"""

from typing import Any, Optional


class DomainException(Exception):
    """
    Base exception for all domain errors.

    Attributes:
        message: Human-readable error message
        code: Machine-readable error code for BPMN mapping
        details: Additional error details
    """

    def __init__(
        self,
        message: str,
        code: str = "DOMAIN_ERROR",
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r})"

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for serialization."""
        return {
            "error_type": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ValidationException(DomainException):
    """
    Exception for validation errors.

    Raised when input data fails validation rules.

    BPMN Error Code: VALIDATION_ERROR
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        code = "VALIDATION_ERROR"
        if field:
            code = f"INVALID_{field.upper()}"

        full_details = {"field": field, **(details or {})}
        super().__init__(message=message, code=code, details=full_details)
        self.field = field


class BusinessRuleException(DomainException):
    """
    Exception for business rule violations.

    Raised when a business rule is violated during processing.

    BPMN Error Codes vary by rule type:
    - MISSING_AUTHORIZATION
    - EXCEEDED_LIMIT
    - INVALID_STATUS_TRANSITION
    - etc.
    """

    def __init__(
        self,
        message: str,
        rule_name: str,
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        error_code = code or f"RULE_VIOLATION_{rule_name.upper()}"
        full_details = {"rule_name": rule_name, **(details or {})}
        super().__init__(message=message, code=error_code, details=full_details)
        self.rule_name = rule_name


class EntityNotFoundException(DomainException):
    """
    Exception for entity not found errors.

    Raised when a required entity cannot be found.

    BPMN Error Code: ENTITY_NOT_FOUND or {ENTITY_TYPE}_NOT_FOUND
    """

    def __init__(
        self,
        entity_type: str,
        entity_id: Any,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        error_message = message or f"{entity_type} with id '{entity_id}' not found"
        code = f"{entity_type.upper()}_NOT_FOUND"
        full_details = {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            **(details or {}),
        }
        super().__init__(message=error_message, code=code, details=full_details)
        self.entity_type = entity_type
        self.entity_id = entity_id


class ConcurrencyException(DomainException):
    """
    Exception for concurrency/optimistic locking errors.

    Raised when a concurrent modification is detected.

    BPMN Error Code: CONCURRENCY_ERROR
    """

    def __init__(
        self,
        entity_type: str,
        entity_id: Any,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        error_message = (
            message or f"Concurrent modification detected for {entity_type} '{entity_id}'"
        )
        full_details = {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            **(details or {}),
        }
        super().__init__(message=error_message, code="CONCURRENCY_ERROR", details=full_details)
        self.entity_type = entity_type
        self.entity_id = entity_id


class IntegrationException(DomainException):
    """
    Exception for external integration errors.

    Raised when an external system integration fails.

    BPMN Error Codes:
    - INTEGRATION_ERROR
    - TASY_ERROR
    - TISS_ERROR
    - LIS_ERROR
    - PACS_ERROR
    """

    def __init__(
        self,
        system: str,
        message: str,
        original_error: Optional[Exception] = None,
        retryable: bool = True,
        details: Optional[dict[str, Any]] = None,
    ):
        code = f"{system.upper()}_ERROR"
        full_details = {
            "system": system,
            "retryable": retryable,
            "original_error": str(original_error) if original_error else None,
            **(details or {}),
        }
        super().__init__(message=message, code=code, details=full_details)
        self.system = system
        self.original_error = original_error
        self.retryable = retryable


class BpmnErrorException(DomainException):
    """
    Exception that maps directly to BPMN error events.

    Use this when you need to trigger a specific BPMN error
    boundary event in the process definition.

    Example:
        raise BpmnErrorException(
            error_code="GLOSA_ANALYSIS_FAILED",
            message="Failed to analyze glosa: missing documentation"
        )
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        error_message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize BPMN error exception.

        Args:
            error_code: BPMN error code (matches errorCode in BPMN model)
            message: Human-readable error description
            error_message: Optional error message for BPMN error event
            details: Additional error details
        """
        super().__init__(message=message, code=error_code, details=details)
        self.error_code = error_code
        self.error_message = error_message or message

    @classmethod
    def missing_variable(cls, variable_name: str) -> "BpmnErrorException":
        """Create exception for missing required variable."""
        return cls(
            error_code="MISSING_VARIABLE",
            message=f"Required variable '{variable_name}' not found",
            details={"variable_name": variable_name},
        )

    @classmethod
    def invalid_glosa_data(cls, reason: str) -> "BpmnErrorException":
        """Create exception for invalid glosa data."""
        return cls(
            error_code="INVALID_GLOSA_DATA",
            message=f"Invalid glosa data: {reason}",
        )

    @classmethod
    def analysis_failed(cls, reason: str) -> "BpmnErrorException":
        """Create exception for failed analysis."""
        return cls(
            error_code="ANALYSIS_FAILED",
            message=f"Analysis failed: {reason}",
        )

    @classmethod
    def worker_failure(cls, worker_name: str, reason: str) -> "BpmnErrorException":
        """Create exception for worker failure after retries exhausted."""
        return cls(
            error_code="WORKER_FAILURE",
            message=f"Worker '{worker_name}' failed: {reason}",
            details={"worker_name": worker_name},
        )


class ExternalServiceException(IntegrationException):
    """
    Exception for external service communication errors.

    Raised when an external service call fails.

    BPMN Error Code: EXTERNAL_SERVICE_ERROR or {SERVICE}_ERROR
    """

    def __init__(
        self,
        service: str,
        message: str,
        original_error: Optional[Exception] = None,
        retryable: bool = True,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(
            system=service,
            message=message,
            original_error=original_error,
            retryable=retryable,
            details=details,
        )
        self.service = service


class CalculationError(BpmnErrorException):
    """
    Exception for calculation-related errors.

    Raised when a financial or mathematical calculation fails.

    BPMN Error Code: CALCULATION_ERROR
    """

    def __init__(
        self,
        message: str,
        calculation_type: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        full_details = {"calculation_type": calculation_type, **(details or {})}
        super().__init__(
            error_code="CALCULATION_ERROR",
            message=message,
            details=full_details,
        )
        self.calculation_type = calculation_type


class PricingError(BusinessRuleException):
    """
    Exception for pricing-related errors.

    Raised when pricing lookup or calculation fails.

    BPMN Error Code: PRICING_ERROR
    """

    def __init__(
        self,
        message: str,
        procedure_code: Optional[str] = None,
        pricing_table: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        full_details = {
            "procedure_code": procedure_code,
            "pricing_table": pricing_table,
            **(details or {}),
        }
        super().__init__(
            message=message,
            rule_name="PRICING",
            code="PRICING_ERROR",
            details=full_details,
        )
        self.procedure_code = procedure_code
        self.pricing_table = pricing_table


class PaymentAllocationException(BusinessRuleException):
    """
    Exception for payment allocation errors.

    Raised when payment cannot be allocated to claims.

    BPMN Error Code: PAYMENT_ALLOCATION_ERROR
    """

    def __init__(
        self,
        message: str,
        payment_id: Optional[str] = None,
        claim_ids: Optional[list[str]] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        full_details = {
            "payment_id": payment_id,
            "claim_ids": claim_ids or [],
            **(details or {}),
        }
        super().__init__(
            message=message,
            rule_name="PAYMENT_ALLOCATION",
            code="PAYMENT_ALLOCATION_ERROR",
            details=full_details,
        )
        self.payment_id = payment_id
        self.claim_ids = claim_ids or []
