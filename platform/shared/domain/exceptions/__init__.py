"""Domain exceptions with BPMN error codes for CIB7 integration."""
from __future__ import annotations

from typing import Any

from platform.shared.i18n import _


class DomainException(Exception):
    """Base domain exception with BPMN error code support."""

    bpmn_error_code: str = "DOMAIN_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        bpmn_error_code: str | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        if bpmn_error_code is not None:
            self.bpmn_error_code = bpmn_error_code
        if retryable is not None:
            self.retryable = retryable
        self.details = details or {}


# ── Billing Exceptions ──────────────────────────────────────────────────


class BillingException(DomainException):
    """Billing-related business errors."""

    bpmn_error_code: str = "BILLING_ERROR"


class ClaimValidationError(BillingException):
    """Claim failed validation rules."""

    bpmn_error_code: str = "CLAIM_VALIDATION_FAILED"


class DuplicateClaimError(BillingException):
    """Duplicate claim detected."""

    bpmn_error_code: str = "DUPLICATE_CLAIM"


class ClaimSubmissionError(BillingException):
    """Claim submission to payer failed."""

    bpmn_error_code: str = "CLAIM_SUBMISSION_FAILED"
    retryable: bool = True


class ContractRuleViolation(BillingException):
    """Contract rule violation detected during billing."""

    bpmn_error_code: str = "CONTRACT_RULE_VIOLATION"


# ── Coding Exceptions ───────────────────────────────────────────────────


class CodingException(DomainException):
    """Clinical coding errors."""

    bpmn_error_code: str = "CODING_ERROR"


class InvalidProcedureCode(CodingException):
    """Procedure code is invalid or not found in TUSS/CBHPM."""

    bpmn_error_code: str = "INVALID_PROCEDURE_CODE"


class IncompatibleCodes(CodingException):
    """Procedure codes are incompatible with each other."""

    bpmn_error_code: str = "INCOMPATIBLE_CODES"


class MissingDiagnosisCode(CodingException):
    """Required diagnosis code (CID-10) is missing."""

    bpmn_error_code: str = "MISSING_DIAGNOSIS"


# ── Glosa (Denial) Exceptions ──────────────────────────────────────────


class GlosaException(DomainException):
    """Glosa/denial-related errors."""

    bpmn_error_code: str = "GLOSA_ERROR"


class GlosaAppealDeadlineExpired(GlosaException):
    """Appeal deadline for glosa has passed."""

    bpmn_error_code: str = "APPEAL_DEADLINE_EXPIRED"


class GlosaNotAppealable(GlosaException):
    """This glosa type cannot be appealed."""

    bpmn_error_code: str = "GLOSA_NOT_APPEALABLE"


# ── Authorization Exceptions ───────────────────────────────────────────


class AuthorizationException(DomainException):
    """Prior authorization errors."""

    bpmn_error_code: str = "AUTH_ERROR"


class AuthorizationDenied(AuthorizationException):
    """Authorization request was denied by payer."""

    bpmn_error_code: str = "AUTH_DENIED"


class AuthorizationExpired(AuthorizationException):
    """Authorization has expired."""

    bpmn_error_code: str = "AUTH_EXPIRED"


class AuthorizationNotFound(AuthorizationException):
    """Referenced authorization not found."""

    bpmn_error_code: str = "AUTH_NOT_FOUND"


# ── Eligibility Exceptions ─────────────────────────────────────────────


class EligibilityException(DomainException):
    """Patient eligibility errors."""

    bpmn_error_code: str = "ELIGIBILITY_ERROR"


class PatientNotEligible(EligibilityException):
    """Patient is not eligible for the requested service."""

    bpmn_error_code: str = "PATIENT_NOT_ELIGIBLE"


class CoverageInactive(EligibilityException):
    """Patient's coverage/convênio is inactive or suspended."""

    bpmn_error_code: str = "COVERAGE_INACTIVE"


# ── TISS Exceptions ────────────────────────────────────────────────────


class TISSException(DomainException):
    """TISS standard validation errors."""

    bpmn_error_code: str = "TISS_ERROR"


class TISSValidationError(TISSException):
    """TISS guide validation failed."""

    bpmn_error_code: str = "TISS_VALIDATION_FAILED"


class TISSSchemaError(TISSException):
    """TISS XML schema validation failed."""

    bpmn_error_code: str = "TISS_SCHEMA_ERROR"


# ── External Service Exceptions ────────────────────────────────────────


class ExternalServiceException(DomainException):
    """External service integration errors."""

    bpmn_error_code: str = "EXTERNAL_SERVICE_ERROR"
    retryable: bool = True

    def __init__(
        self,
        message: str,
        *,
        service_name: str = "",
        operation: str = "",
        status_code: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.service_name = service_name
        self.operation = operation
        self.status_code = status_code


# ── Tenant Exceptions ──────────────────────────────────────────────────


class TenantException(DomainException):
    """Multi-tenancy errors."""

    bpmn_error_code: str = "TENANT_ERROR"


class InvalidTenant(TenantException):
    """Tenant identifier is invalid or not recognized."""

    bpmn_error_code: str = "INVALID_TENANT"


class TenantAccessDenied(TenantException):
    """Cross-tenant access attempted."""

    bpmn_error_code: str = "TENANT_ACCESS_DENIED"


# ── BPMN Error Helper ──────────────────────────────────────────────────


class BpmnErrorException(DomainException):
    """Direct BPMN error for CIB7 throwBpmnError integration."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, bpmn_error_code=error_code, details=details)
        self.error_code = error_code
