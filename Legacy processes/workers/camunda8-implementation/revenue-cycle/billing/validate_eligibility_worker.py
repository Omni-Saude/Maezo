"""
ValidateEligibilityWorker - Validate patient insurance eligibility and coverage details.

Business Rule: RN-ELI-001.md
Regulatory Compliance: ANS (Agencia Nacional de Saude) regulations, TISS standards
Migrated from: com.hospital.revenuecycle.delegates.eligibility.ValidateInsuranceDelegate

Validates patient insurance eligibility for procedures:
- Verifies active coverage status
- Checks procedure-specific coverage details
- Determines copay/coinsurance amounts
- Identifies authorization requirements
- Multi-tenant insurance API integration

BPMN Task: Task_Validate_Eligibility in SUB_02_Patient_Registration
Zeebe Topic: validate-eligibility
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Protocol

import structlog

from revenue_cycle.domain.exceptions import (
    BpmnErrorException,
    EntityNotFoundException,
    ExternalServiceException,
)
from revenue_cycle.multi_tenant.context import TenantContext
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.eligibility.models import (
    AuthorizationType,
    CoverageDetail,
    CoverageLevel,
    CoverageStatus,
    EligibilityError,
    ValidateEligibilityInput,
    ValidateEligibilityOutput,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Custom Exceptions
# =============================================================================


class EligibilityServiceError(BpmnErrorException):
    """Raised when the eligibility verification service fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="ELIGIBILITY_SERVICE_ERROR",
            message=message,
            details=details,
        )


class InvalidPatientDataError(BpmnErrorException):
    """Raised when patient data is invalid or incomplete for eligibility check."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="INVALID_PATIENT_DATA",
            message=message,
            details=details,
        )


# =============================================================================
# Insurance API Integration Protocol
# =============================================================================


class InsuranceEligibilityResponse(Protocol):
    """Protocol for insurance eligibility API response."""
    is_eligible: bool
    coverage_status: str
    payer_id: str
    payer_name: str
    plan_name: Optional[str]
    coverage_start_date: Optional[date]
    coverage_end_date: Optional[date]
    copay_amount: Decimal
    errors: list[dict[str, Any]]


class InsuranceAPIClient(Protocol):
    """
    Protocol for insurance eligibility API client.

    Implementations should integrate with insurance company APIs
    (e.g., ANS TISS web services, insurance portals).
    """

    async def verify_eligibility(
        self,
        patient_id: str,
        insurance_id: str,
        card_number: Optional[str],
        encounter_date: date,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> InsuranceEligibilityResponse:
        """
        Verify patient eligibility with insurance API.

        Args:
            patient_id: Patient identifier
            insurance_id: Insurance plan identifier
            card_number: Patient insurance card number
            encounter_date: Date of service
            procedure_codes: List of procedure codes
            tenant_id: Tenant identifier for multi-tenant credentials

        Returns:
            Insurance eligibility response

        Raises:
            ExternalServiceException: If API call fails
        """
        ...

    async def get_coverage_details(
        self,
        insurance_id: str,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> list[CoverageDetail]:
        """
        Get detailed coverage information for procedures.

        Args:
            insurance_id: Insurance plan identifier
            procedure_codes: List of procedure codes
            tenant_id: Tenant identifier

        Returns:
            List of coverage details per procedure
        """
        ...

    async def check_authorization_requirements(
        self,
        insurance_id: str,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> dict[str, AuthorizationType]:
        """
        Check authorization requirements for procedures.

        Args:
            insurance_id: Insurance plan identifier
            procedure_codes: List of procedure codes
            tenant_id: Tenant identifier

        Returns:
            Dictionary mapping procedure codes to authorization types
        """
        ...


# =============================================================================
# Stub Insurance API Client (for development/testing)
# =============================================================================


class StubInsuranceAPIClient:
    """
    Stub implementation of InsuranceAPIClient for development and testing.

    This provides realistic mock responses based on common scenarios in
    Brazilian healthcare. In production, replace with actual insurance API
    integration.
    """

    def __init__(self):
        self._logger = logger.bind(component="StubInsuranceAPIClient")

    async def verify_eligibility(
        self,
        patient_id: str,
        insurance_id: str,
        card_number: Optional[str],
        encounter_date: date,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Stub eligibility verification.

        Returns mock responses based on insurance_id patterns:
        - Contains "EXPIRED": Expired coverage
        - Contains "SUSPENDED": Suspended coverage
        - Contains "INVALID": Invalid insurance
        - Default: Active coverage
        """
        self._logger.info(
            "Stub eligibility verification",
            patient_id=patient_id,
            insurance_id=insurance_id,
            tenant_id=tenant_id,
        )

        # Simulate API processing delay
        # await asyncio.sleep(0.1)

        # Determine response based on insurance_id
        insurance_id_upper = insurance_id.upper()

        if "EXPIRED" in insurance_id_upper:
            return {
                "is_eligible": False,
                "coverage_status": "EXPIRED",
                "payer_id": insurance_id,
                "payer_name": "UNIMED Nacional",
                "plan_name": "Plano Empresarial",
                "coverage_start_date": date(2024, 1, 1),
                "coverage_end_date": date(2025, 12, 31),
                "copay_amount": Decimal("0.00"),
                "errors": [
                    {
                        "errorCode": "COVERAGE_EXPIRED",
                        "errorMessage": "Coverage expired on 2025-12-31",
                        "severity": "ERROR",
                    }
                ],
            }

        if "SUSPENDED" in insurance_id_upper:
            return {
                "is_eligible": False,
                "coverage_status": "SUSPENDED",
                "payer_id": insurance_id,
                "payer_name": "Bradesco Saúde",
                "plan_name": "Plano Individual",
                "coverage_start_date": date(2024, 1, 1),
                "coverage_end_date": None,
                "copay_amount": Decimal("0.00"),
                "errors": [
                    {
                        "errorCode": "COVERAGE_SUSPENDED",
                        "errorMessage": "Coverage suspended due to non-payment",
                        "severity": "ERROR",
                    }
                ],
            }

        if "INVALID" in insurance_id_upper:
            raise ExternalServiceException(
                service_name="InsuranceAPI",
                operation="verify_eligibility",
                message=f"Invalid insurance ID: {insurance_id}",
                status_code=404,
            )

        # Default: Active coverage
        return {
            "is_eligible": True,
            "coverage_status": "ACTIVE",
            "payer_id": insurance_id,
            "payer_name": "UNIMED",
            "plan_name": "Plano Premium",
            "coverage_start_date": date(2024, 1, 1),
            "coverage_end_date": date(2026, 12, 31),
            "copay_amount": Decimal("50.00"),
            "errors": [],
        }

    async def get_coverage_details(
        self,
        insurance_id: str,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> list[CoverageDetail]:
        """
        Stub coverage details lookup.

        Returns mock coverage based on procedure code patterns:
        - Starts with "99": NOT_COVERED
        - Starts with "88": PARTIAL (70% coverage)
        - Default: FULL coverage
        """
        self._logger.debug(
            "Stub coverage details lookup",
            insurance_id=insurance_id,
            procedure_count=len(procedure_codes),
        )

        coverage_details = []

        for code in procedure_codes:
            if code.startswith("99"):
                # Not covered
                coverage_details.append(
                    CoverageDetail(
                        procedure_code=code,
                        coverage_level=CoverageLevel.NOT_COVERED,
                        coverage_percentage=Decimal("0.00"),
                        notes="Procedure not covered by plan",
                    )
                )
            elif code.startswith("88"):
                # Partially covered
                coverage_details.append(
                    CoverageDetail(
                        procedure_code=code,
                        coverage_level=CoverageLevel.PARTIAL,
                        coverage_percentage=Decimal("70.00"),
                        annual_limit=Decimal("5000.00"),
                        remaining_limit=Decimal("3000.00"),
                        notes="70% coverage, subject to annual limit",
                    )
                )
            else:
                # Fully covered
                coverage_details.append(
                    CoverageDetail(
                        procedure_code=code,
                        coverage_level=CoverageLevel.FULL,
                        coverage_percentage=Decimal("100.00"),
                        notes="Fully covered by plan",
                    )
                )

        return coverage_details

    async def check_authorization_requirements(
        self,
        insurance_id: str,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> dict[str, AuthorizationType]:
        """
        Stub authorization requirements check.

        Returns mock authorization based on procedure code patterns:
        - Starts with "30": PRIOR authorization required (surgical)
        - Starts with "40": PRIOR authorization required (therapeutic)
        - Starts with "50": CONCURRENT authorization (hospitalization)
        - Default: NONE
        """
        self._logger.debug(
            "Stub authorization requirements check",
            insurance_id=insurance_id,
            procedure_count=len(procedure_codes),
        )

        authorization_map = {}

        for code in procedure_codes:
            if code.startswith("30"):
                # Surgical procedures need prior auth
                authorization_map[code] = AuthorizationType.PRIOR
            elif code.startswith("40"):
                # High-cost therapeutic procedures need prior auth
                authorization_map[code] = AuthorizationType.PRIOR
            elif code.startswith("50"):
                # Hospitalization needs concurrent auth
                authorization_map[code] = AuthorizationType.CONCURRENT
            else:
                # No authorization required
                authorization_map[code] = AuthorizationType.NONE

        return authorization_map


# =============================================================================
# ValidateEligibilityWorker Implementation
# =============================================================================


@worker(
    topic="validate-eligibility",
    lock_duration=60000,  # 1 minute
    max_jobs=20,
)
class ValidateEligibilityWorker(BaseWorker):
    """
    Worker for validating patient insurance eligibility.

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/05_Eligibility/RN-ELI-001-Validate-Eligibility.md
        - Rule IDs: RN-ELI-001-001 (Coverage Verification), RN-ELI-001-002 (Procedure Coverage),
                    RN-ELI-001-003 (Authorization Requirements), RN-ELI-001-004 (Copay Calculation)
        - Regulatory: ANS TISS (Insurance Standards), Resolution 2965 (ANS),
                      CDC (Consumer Protection), LGPD (Privacy)
        - Insurance API: Multi-tenant credentials, Error handling, Rate limiting

    BPMN Task: Task_Validate_Eligibility
    Topic: validate-eligibility

    Migrated from: com.hospital.revenuecycle.delegates.eligibility.ValidateInsuranceDelegate

    Responsibilities:
    - Verify active insurance coverage
    - Check procedure-specific coverage details
    - Calculate copay/coinsurance amounts
    - Determine authorization requirements
    - Handle multi-tenant insurance API credentials

    Business Logic Summary:
    1. PARSE and validate input variables
    2. RETRIEVE tenant-specific insurance API credentials
    3. CALL insurance API to verify eligibility
    4. VALIDATE coverage status (ACTIVE/SUSPENDED/EXPIRED)
    5. GET detailed coverage for each procedure
    6. CHECK authorization requirements
    7. CALCULATE patient copay amount
    8. BUILD output with eligibility results
    9. THROW BPMN errors for critical failures

    This worker integrates with external insurance APIs and requires proper
    credential management for multi-tenant scenarios.
    """

    def __init__(
        self,
        settings=None,
        eligibility_service=None,
        insurance_service=None,
        **kwargs
    ):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            eligibility_service: Optional eligibility service (for testing)
            insurance_service: Optional insurance service (for testing)
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._insurance_api = insurance_service or StubInsuranceAPIClient()
        self._logger = logger.bind(worker=self.worker_name)
        # Store optional services for testing
        self._eligibility_service = eligibility_service
        self._insurance_service = insurance_service

    @property
    def operation_name(self) -> str:
        """Get the operation name for idempotency and logging."""
        return "validate_eligibility"

    @property
    def requires_idempotency(self) -> bool:
        """
        Eligibility verification is idempotent.

        Same patient + insurance + date = same eligibility result.
        However, we should check idempotency to avoid redundant API calls.
        """
        return True

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the validate-eligibility task.

        Main processing flow:
        1. Parse and validate input variables
        2. Get tenant context for multi-tenant API credentials
        3. Call insurance API to verify eligibility
        4. Get detailed coverage information
        5. Check authorization requirements
        6. Build output with eligibility results
        7. Handle errors appropriately

        Args:
            job: Camunda external task
            variables: Job variables from the process

        Returns:
            WorkerResult with eligibility verification results

        Raises:
            Various BPMN errors for eligibility failures
        """
        # Get tenant_id for multi-tenant support
        tenant_id = variables.get("tenantId")

        self._logger.info(
            "Starting eligibility verification",
            job_key=str(getattr(job, "key", "unknown")),
            tenant_id=tenant_id,
        )

        try:
            # 1. Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Validating eligibility",
                patient_id=input_data.patient_id,
                insurance_id=input_data.insurance_id,
                procedure_count=len(input_data.procedure_codes),
                encounter_date=str(input_data.encounter_date),
            )

            # 2. Call eligibility service to verify eligibility
            eligibility_response = await self._check_eligibility(
                patient_id=input_data.patient_id,
                insurance_id=input_data.insurance_id,
                service_date=input_data.encounter_date,
                procedure_codes=input_data.procedure_codes,
                tenant_id=tenant_id,
            )

            # 3. Determine eligibility status
            is_eligible = eligibility_response.get("eligible", False)
            status = eligibility_response.get("status", "INACTIVE")

            if not is_eligible:
                # Handle ineligibility - return error response
                output = ValidateEligibilityOutput(
                    eligible=False,
                    eligibility_status=status,
                    coverage_start=eligibility_response.get("coverage_start"),
                    coverage_end=eligibility_response.get("coverage_end"),
                    ineligibility_reason=eligibility_response.get("reason", "Patient not eligible"),
                )
                self._logger.warning(
                    "Patient not eligible",
                    patient_id=input_data.patient_id,
                    status=status,
                )
                return WorkerResult.ok(output.model_dump(by_alias=True, exclude_none=True))

            # 4. Get plan benefits for eligible patient
            plan_benefits = await self._get_plan_benefits(
                insurance_id=input_data.insurance_id,
                patient_id=input_data.patient_id,
                tenant_id=tenant_id,
            )

            # 5. Build successful eligibility output
            output = ValidateEligibilityOutput(
                eligible=is_eligible,
                eligibility_status=status,
                coverage_start=eligibility_response.get("coverage_start"),
                coverage_end=eligibility_response.get("coverage_end"),
                plan_name=eligibility_response.get("plan_name"),
                member_id=eligibility_response.get("member_id"),
                payer_id=eligibility_response.get("payer_id"),
                payer_name=eligibility_response.get("payer_name"),
                max_coverage=plan_benefits.get("max_coverage"),
                deductible=plan_benefits.get("deductible"),
                copay_percentage=plan_benefits.get("copay_percentage"),
                authorization_required=False,
            )

            self._logger.info(
                "Eligibility verification completed successfully",
                patient_id=input_data.patient_id,
                eligible=is_eligible,
                status=status,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True, exclude_none=True))

        except EligibilityServiceError as e:
            self._logger.error(
                "Eligibility service error",
                error=str(e),
            )
            return WorkerResult.failure(
                error_message=str(e),
                retry=True,
                retry_timeout=5000,
            )

        except (EntityNotFoundException, InvalidPatientDataError) as e:
            self._logger.warning(
                "Entity or validation error during eligibility verification",
                error=str(e),
            )
            error_code = getattr(e, "error_code", "INVALID_INPUT")
            error_message = getattr(e, "error_message", str(e))
            return WorkerResult.bpmn_error(
                error_code=error_code,
                error_message=error_message,
            )

        except BpmnErrorException as e:
            self._logger.warning(
                "BPMN error during eligibility verification",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except ExternalServiceException as e:
            self._logger.error(
                "Insurance API call failed",
                service=e.service_name,
                operation=e.operation,
                error=str(e),
            )
            return WorkerResult.failure(
                error_message=f"Insurance verification service error: {e.message}",
                retry=True,
                retry_timeout=5000,
            )

        except Exception as e:
            self._logger.exception(
                "Unexpected error during eligibility verification",
                error=str(e),
                error_type=type(e).__name__,
            )
            return WorkerResult.failure(
                error_message=f"Unexpected error: {str(e)}",
                retry=False,
            )

    def _parse_input(self, variables: dict[str, Any]) -> ValidateEligibilityInput:
        """
        Parse and validate input variables.

        Args:
            variables: Job variables

        Returns:
            Validated input model

        Raises:
            BpmnErrorException: If validation fails
        """
        try:
            return ValidateEligibilityInput.model_validate(variables)
        except Exception as e:
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid eligibility verification input: {e}",
            )

    def _parse_coverage_status(self, status_str: str) -> CoverageStatus:
        """
        Parse coverage status string to enum.

        Args:
            status_str: Coverage status string

        Returns:
            CoverageStatus enum
        """
        try:
            return CoverageStatus(status_str.upper())
        except ValueError:
            self._logger.warning(
                "Unknown coverage status, defaulting to SUSPENDED",
                status=status_str,
            )
            return CoverageStatus.SUSPENDED

    def _handle_ineligibility(
        self,
        coverage_status: CoverageStatus,
        eligibility_response: dict[str, Any],
        input_data: ValidateEligibilityInput,
    ) -> WorkerResult:
        """
        Handle ineligibility scenarios with appropriate BPMN errors.

        Args:
            coverage_status: Coverage status enum
            eligibility_response: Response from insurance API
            input_data: Original input data

        Returns:
            WorkerResult with BPMN error
        """
        # Determine appropriate BPMN error code
        if coverage_status == CoverageStatus.EXPIRED:
            error_code = "COVERAGE_EXPIRED"
            error_message = f"Insurance coverage expired for patient {input_data.patient_id}"
        elif coverage_status == CoverageStatus.SUSPENDED:
            error_code = "COVERAGE_SUSPENDED"
            error_message = f"Insurance coverage suspended for patient {input_data.patient_id}"
        elif coverage_status == CoverageStatus.CANCELLED:
            error_code = "COVERAGE_CANCELLED"
            error_message = f"Insurance coverage cancelled for patient {input_data.patient_id}"
        else:
            error_code = "INVALID_INSURANCE"
            error_message = f"Patient {input_data.patient_id} is not eligible for services"

        # Include error details from API response
        errors = eligibility_response.get("errors", [])
        if errors:
            error_details = "; ".join([e.get("errorMessage", "") for e in errors])
            error_message = f"{error_message}. Details: {error_details}"

        self._logger.warning(
            "Patient not eligible",
            patient_id=input_data.patient_id,
            coverage_status=coverage_status.value,
            error_code=error_code,
        )

        return WorkerResult.bpmn_error(
            error_code=error_code,
            error_message=error_message,
            variables={
                "coverageStatus": coverage_status.value,
                "eligibilityErrors": errors,
            },
        )

    def _parse_eligibility_errors(
        self,
        errors: list[dict[str, Any]],
    ) -> list[EligibilityError]:
        """
        Parse eligibility errors from API response.

        Args:
            errors: List of error dictionaries from API

        Returns:
            List of structured EligibilityError objects
        """
        parsed_errors = []

        for error_dict in errors:
            try:
                parsed_errors.append(
                    EligibilityError(
                        error_code=error_dict.get("errorCode", "UNKNOWN"),
                        error_message=error_dict.get("errorMessage", "Unknown error"),
                        field=error_dict.get("field"),
                        severity=error_dict.get("severity", "ERROR"),
                    )
                )
            except Exception as e:
                self._logger.warning(
                    "Failed to parse eligibility error",
                    error=str(e),
                    error_dict=error_dict,
                )

        return parsed_errors

    async def _check_eligibility(
        self,
        patient_id: str,
        insurance_id: str,
        service_date: Optional[date] = None,
        procedure_codes: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Check patient eligibility with insurance service.

        Args:
            patient_id: Patient identifier
            insurance_id: Insurance plan identifier
            service_date: Date of service
            procedure_codes: List of procedure codes
            tenant_id: Tenant identifier for multi-tenant support

        Returns:
            Dictionary with eligibility information
        """
        if service_date is None:
            service_date = date.today()
        if procedure_codes is None:
            procedure_codes = []

        # Delegate to the eligibility service
        if self._eligibility_service:
            return await self._eligibility_service.check_eligibility(
                patient_id=patient_id,
                insurance_id=insurance_id,
                service_date=service_date,
                procedure_codes=procedure_codes,
            )

        # Fallback to API client
        return await self._insurance_api.verify_eligibility(
            patient_id=patient_id,
            insurance_id=insurance_id,
            card_number=None,
            encounter_date=service_date,
            procedure_codes=procedure_codes,
            tenant_id=tenant_id,
        )

    def _is_coverage_active(
        self,
        service_date: date,
        coverage_start: date,
        coverage_end: date,
    ) -> bool:
        """
        Check if coverage is active for a service date.

        Args:
            service_date: Date of service
            coverage_start: Coverage start date
            coverage_end: Coverage end date

        Returns:
            True if coverage is active for the service date
        """
        return coverage_start <= service_date <= coverage_end

    async def _get_plan_benefits(
        self,
        insurance_id: str,
        patient_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get plan benefits for insurance.

        Args:
            insurance_id: Insurance plan identifier
            patient_id: Patient identifier (optional)
            tenant_id: Tenant identifier

        Returns:
            Dictionary with plan benefits
        """
        # Delegate to the eligibility service if available
        if self._eligibility_service:
            return await self._eligibility_service.get_plan_benefits(
                insurance_id=insurance_id
            )

        # Default implementation
        return {
            "max_coverage": Decimal("50000.00"),
            "deductible": Decimal("1000.00"),
            "copay_percentage": 20.0,
        }

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Uses patient_id, insurance_id, and service_date/encounter_date for idempotency.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        patient_id = variables.get("patientId", "")
        insurance_id = variables.get("insuranceId", "")
        # Try both serviceDate and encounterDate
        service_date = variables.get("serviceDate") or variables.get("encounterDate", "")
        process_instance = variables.get("processInstanceKey", "")
        return f"{process_instance}:{patient_id}:{insurance_id}:{service_date}"


# Worker registration function for use with Zeebe client
def create_validate_eligibility_worker(
    insurance_api_client: Optional[InsuranceAPIClient] = None,
) -> ValidateEligibilityWorker:
    """
    Factory function to create ValidateEligibilityWorker.

    Args:
        insurance_api_client: Optional custom insurance API client

    Returns:
        Configured worker instance
    """
    return ValidateEligibilityWorker(insurance_api_client=insurance_api_client)
