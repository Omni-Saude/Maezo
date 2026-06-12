"""
ValidateEligibilityWorker - CIB7 External Task Worker

EXAMPLE MIGRATION from Camunda8/pyzeebe to CIB7/camunda-external-task-client-python3

⚠️  NOTE: This is a documentation/example file showing migration patterns.
    Import warnings are expected - this code is not meant to run in this workspace.
    Copy this file to your workers/ directory and install dependencies to use it.

Business Rule: RN-ELI-001.md (Validate Eligibility)
Regulatory Compliance: ANS TISS, Resolution 2965, CDC, LGPD
BPMN Process: SUB_02_Patient_Registration
BPMN Task: Task_Validate_Eligibility
Topic: validate-eligibility

This worker verifies patient insurance eligibility before service delivery.

Migration Notes:
- Changed from pyzeebe gRPC (@worker decorator) to CIB7 REST (subscribe)
- Updated variable access: task.variables → task.get_variable()
- Changed completion: return dict → task.complete(dict)
- Updated BPMN errors: raise exception → task.bpmn_error()
- Updated failures: raise exception → task.failure()
- Preserved multi-tenant context support
- Maintained LGPD-compliant logging

Original File: revenue-cycle/billing/validate_eligibility_worker.py (Camunda8)
Migrated: 2026-02-09

Dependencies Required:
    pip install camunda-external-task-client-python3 pydantic structlog
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Protocol

import structlog
from camunda.external_task.external_task import ExternalTask, TaskResult
from camunda.external_task.external_task_worker import ExternalTaskWorker
from pydantic import BaseModel, Field, validator

from revenue_cycle.shared.exceptions import (
    BpmnErrorException,
    ExternalServiceException,
    EntityNotFoundException,
)
from revenue_cycle.shared.multi_tenant.context import TenantContext
from revenue_cycle.shared.observability.logging import get_logger
from revenue_cycle.shared.observability.metrics import track_task_execution

# Initialize logger
logger = get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class CoverageStatus(str, Enum):
    """Insurance coverage status."""
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    INACTIVE = "INACTIVE"


class CoverageLevel(str, Enum):
    """Level of coverage for a procedure."""
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NOT_COVERED = "NOT_COVERED"


class AuthorizationType(str, Enum):
    """Type of authorization required."""
    NONE = "NONE"
    PRIOR = "PRIOR"
    CONCURRENT = "CONCURRENT"
    RETROSPECTIVE = "RETROSPECTIVE"


# =============================================================================
# Custom Exceptions
# =============================================================================


class EligibilityServiceError(ExternalServiceException):
    """Raised when insurance eligibility service fails."""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            service_name="InsuranceEligibilityService",
            operation="verify_eligibility",
            message=message,
            details=details or {},
        )
        self.error_code = "ELIGIBILITY_SERVICE_ERROR"


class InvalidPatientDataError(BpmnErrorException):
    """Raised when patient data is invalid or missing."""
    
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            error_code="INVALID_PATIENT_DATA",
            message=message,
            details={"field": field} if field else {},
        )


# =============================================================================
# Data Models
# =============================================================================


class ValidateEligibilityInput(BaseModel):
    """Input variables for eligibility validation."""
    
    patient_id: str = Field(..., description="Patient identifier", alias="patientId")
    insurance_id: str = Field(..., description="Insurance plan identifier", alias="insuranceId")
    card_number: Optional[str] = Field(None, description="Insurance card number", alias="cardNumber")
    encounter_date: Optional[date] = Field(
        default_factory=date.today,
        description="Date of service/encounter",
        alias="encounterDate"
    )
    procedure_codes: list[str] = Field(
        default_factory=list,
        description="List of procedure codes to verify",
        alias="procedureCodes"
    )
    tenant_id: Optional[str] = Field(None, description="Tenant identifier", alias="tenantId")
    
    @validator("patient_id", "insurance_id")
    def validate_required_ids(cls, v):
        if not v or not v.strip():
            raise ValueError("Required ID cannot be empty")
        return v.strip()
    
    class Config:
        extra = "allow"
        populate_by_name = True


class EligibilityError(BaseModel):
    """Error detail from eligibility check."""
    
    error_code: str = Field(..., alias="errorCode")
    error_message: str = Field(..., alias="errorMessage")
    field: Optional[str] = None
    severity: str = "ERROR"


class CoverageDetail(BaseModel):
    """Detailed coverage information for a procedure."""
    
    procedure_code: str = Field(..., alias="procedureCode")
    coverage_level: CoverageLevel = Field(..., alias="coverageLevel")
    coverage_percentage: Decimal = Field(..., alias="coveragePercentage")
    annual_limit: Optional[Decimal] = Field(None, alias="annualLimit")
    remaining_limit: Optional[Decimal] = Field(None, alias="remainingLimit")
    notes: Optional[str] = None


class ValidateEligibilityOutput(BaseModel):
    """Output variables from eligibility validation."""
    
    eligible: bool = Field(..., description="Whether patient is eligible")
    eligibility_status: str = Field(..., alias="eligibilityStatus")
    coverage_start: Optional[date] = Field(None, alias="coverageStart")
    coverage_end: Optional[date] = Field(None, alias="coverageEnd")
    plan_name: Optional[str] = Field(None, alias="planName")
    member_id: Optional[str] = Field(None, alias="memberId")
    payer_id: Optional[str] = Field(None, alias="payerId")
    payer_name: Optional[str] = Field(None, alias="payerName")
    max_coverage: Optional[Decimal] = Field(None, alias="maxCoverage")
    deductible: Optional[Decimal] = None
    copay_percentage: Optional[float] = Field(None, alias="copayPercentage")
    copay_amount: Optional[Decimal] = Field(None, alias="copayAmount")
    authorization_required: bool = Field(False, alias="authorizationRequired")
    ineligibility_reason: Optional[str] = Field(None, alias="ineligibilityReason")
    
    def to_variables(self) -> dict[str, Any]:
        """Convert to CIB7 process variables."""
        return self.model_dump(by_alias=True, exclude_none=True)


# =============================================================================
# Insurance API Client Protocol
# =============================================================================


class InsuranceAPIClient(Protocol):
    """Protocol for insurance API integration."""
    
    async def verify_eligibility(
        self,
        patient_id: str,
        insurance_id: str,
        card_number: Optional[str],
        encounter_date: date,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Verify patient eligibility with insurance provider."""
        ...
    
    async def get_coverage_details(
        self,
        insurance_id: str,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> list[CoverageDetail]:
        """Get detailed coverage for procedures."""
        ...
    
    async def check_authorization_requirements(
        self,
        insurance_id: str,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> dict[str, AuthorizationType]:
        """Check authorization requirements for procedures."""
        ...


# =============================================================================
# Stub Implementation (for testing)
# =============================================================================


class StubInsuranceAPIClient:
    """
    Stub insurance API client for testing.
    
    Simulates Brazilian insurance providers (UNIMED, Bradesco Saúde, etc.)
    """
    
    def __init__(self):
        self._logger = logger.bind(client="StubInsuranceAPIClient")
    
    async def verify_eligibility(
        self,
        patient_id: str,
        insurance_id: str,
        card_number: Optional[str],
        encounter_date: date,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Mock eligibility verification."""
        self._logger.debug(
            "Stub eligibility verification",
            patient_id=patient_id,
            insurance_id=insurance_id,
        )
        
        # Simulate different scenarios
        if "EXPIRED" in insurance_id:
            return {
                "is_eligible": False,
                "coverage_status": "EXPIRED",
                "payer_id": "ANS123456",
                "payer_name": "UNIMED São Paulo",
                "plan_name": "Plano Hospitalar com Coparticipação",
                "coverage_start_date": date(2024, 1, 1),
                "coverage_end_date": date(2025, 12, 31),
                "errors": [{
                    "errorCode": "COVERAGE_EXPIRED",
                    "errorMessage": "Coverage expired on 2025-12-31",
                    "severity": "ERROR"
                }]
            }
        
        if "SUSPENDED" in insurance_id:
            return {
                "is_eligible": False,
                "coverage_status": "SUSPENDED",
                "payer_id": "ANS654321",
                "payer_name": "Bradesco Saúde",
                "plan_name": "Top Nacional",
                "errors": [{
                    "errorCode": "COVERAGE_SUSPENDED",
                    "errorMessage": "Coverage suspended due to non-payment",
                    "severity": "ERROR"
                }]
            }
        
        if "INVALID" in insurance_id:
            raise ExternalServiceException(
                service_name="InsuranceAPI",
                operation="verify_eligibility",
                message="Insurance not found",
                status_code=404,
            )
        
        # Default: eligible
        return {
            "is_eligible": True,
            "coverage_status": "ACTIVE",
            "payer_id": "ANS111222",
            "payer_name": "UNIMED São Paulo",
            "plan_name": "Plano Ambulatorial + Hospitalar",
            "coverage_start_date": date(2024, 1, 1),
            "coverage_end_date": date(2026, 12, 31),
            "copay_amount": Decimal("50.00"),
            "errors": []
        }
    
    async def get_coverage_details(
        self,
        insurance_id: str,
        procedure_codes: list[str],
        tenant_id: Optional[str] = None,
    ) -> list[CoverageDetail]:
        """Mock coverage details retrieval."""
        self._logger.debug(
            "Stub coverage details",
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
        """Mock authorization requirements check."""
        self._logger.debug(
            "Stub authorization requirements",
            insurance_id=insurance_id,
            procedure_count=len(procedure_codes),
        )
        
        authorization_map = {}
        
        for code in procedure_codes:
            if code.startswith("30"):
                # Surgical procedures need prior auth
                authorization_map[code] = AuthorizationType.PRIOR
            elif code.startswith("40"):
                # High-cost therapeutic procedures
                authorization_map[code] = AuthorizationType.PRIOR
            elif code.startswith("50"):
                # Hospitalization needs concurrent auth
                authorization_map[code] = AuthorizationType.CONCURRENT
            else:
                # No authorization required
                authorization_map[code] = AuthorizationType.NONE
        
        return authorization_map


# =============================================================================
# CIB7 Worker Implementation
# =============================================================================


class ValidateEligibilityWorker:
    """
    CIB7 external task worker for insurance eligibility validation.
    
    Topic: validate-eligibility
    
    Responsibilities:
    - Verify active insurance coverage
    - Check procedure-specific coverage
    - Calculate copay/coinsurance
    - Determine authorization requirements
    - Handle multi-tenant credentials
    """
    
    def __init__(
        self,
        insurance_api: Optional[InsuranceAPIClient] = None,
        tenant_context: Optional[TenantContext] = None,
    ):
        """
        Initialize worker with dependencies.
        
        Args:
            insurance_api: Insurance API client (or stub for testing)
            tenant_context: Multi-tenant context manager
        """
        self.insurance_api = insurance_api or StubInsuranceAPIClient()
        self.tenant_context = tenant_context or TenantContext()
        self.logger = logger.bind(worker="ValidateEligibilityWorker")
    
    @track_task_execution(metric_name="validate_eligibility_execution")
    async def execute(self, task: ExternalTask) -> TaskResult:
        """
        Execute eligibility validation task.
        
        Args:
            task: External task from CIB7 engine
            
        Returns:
            TaskResult with completion, BPMN error, or failure
        """
        # Extract task context
        task_id = task.get_task_id()
        business_key = task.get_business_key()
        
        # Bind logger with context
        task_logger = self.logger.bind(
            task_id=task_id,
            business_key=business_key,
        )
        
        task_logger.info("Starting eligibility validation")
        
        try:
            # 1. Parse and validate input
            input_data = self._parse_input(task)
            
            task_logger = task_logger.bind(
                patient_id=input_data.patient_id,
                insurance_id=input_data.insurance_id,
                tenant_id=input_data.tenant_id,
                procedure_count=len(input_data.procedure_codes),
            )
            
            # 2. Set multi-tenant context
            if input_data.tenant_id:
                self.tenant_context.set_current_tenant(input_data.tenant_id)
            
            # 3. Execute eligibility validation
            output = await self._validate_eligibility(input_data, task_logger)
            
            task_logger.info(
                "Eligibility validation completed",
                eligible=output.eligible,
                status=output.eligibility_status,
            )
            
            # 4. Complete task with output variables
            return task.complete(output.to_variables())
        
        except InvalidPatientDataError as e:
            # Invalid input - BPMN error (no retry)
            task_logger.warning(
                "Invalid patient data",
                error_code=e.error_code,
                error_message=str(e),
            )
            
            return task.bpmn_error(
                error_code=e.error_code,
                error_message=str(e),
                variables=e.details or {},
            )
        
        except EligibilityServiceError as e:
            # External service failure - retry
            task_logger.error(
                "Eligibility service error - will retry",
                error=str(e),
            )
            
            return task.failure(
                error_message=str(e),
                error_details=e.details or {},
                max_retries=3,
                retry_timeout=5000,  # 5 seconds
            )
        
        except BpmnErrorException as e:
            # Business error - throw BPMN error
            task_logger.warning(
                "BPMN error during eligibility validation",
                error_code=e.error_code,
                error_message=str(e),
            )
            
            return task.bpmn_error(
                error_code=e.error_code,
                error_message=str(e),
                variables=e.details or {},
            )
        
        except ExternalServiceException as e:
            # External service error - retry
            task_logger.error(
                "External service error",
                service=e.service_name,
                operation=e.operation,
                error=str(e),
            )
            
            return task.failure(
                error_message=f"Insurance service error: {e.message}",
                error_details=e.details or {},
                max_retries=3,
                retry_timeout=5000,
            )
        
        except Exception as e:
            # Unexpected error - fail without retry
            task_logger.exception(
                "Unexpected error during eligibility validation",
                error=str(e),
            )
            
            return task.failure(
                error_message=f"Unexpected error: {str(e)}",
                error_details={"error_type": type(e).__name__},
                max_retries=0,
            )
        
        finally:
            # Cleanup tenant context
            if input_data.tenant_id:
                self.tenant_context.clear_current_tenant()
    
    def _parse_input(self, task: ExternalTask) -> ValidateEligibilityInput:
        """
        Parse and validate input variables.
        
        Args:
            task: External task
            
        Returns:
            Validated input data
            
        Raises:
            InvalidPatientDataError: If validation fails
        """
        # Get all variables from task
        variables = task.get_variables()
        
        try:
            return ValidateEligibilityInput.model_validate(variables)
        except Exception as e:
            self.logger.error(
                "Input validation failed",
                error=str(e),
                variables=variables,
            )
            raise InvalidPatientDataError(
                message=f"Invalid eligibility input: {str(e)}",
            )
    
    async def _validate_eligibility(
        self,
        input_data: ValidateEligibilityInput,
        logger: structlog.BoundLogger,
    ) -> ValidateEligibilityOutput:
        """
        Execute eligibility validation business logic.
        
        Args:
            input_data: Validated input data
            logger: Bound logger with context
            
        Returns:
            Eligibility validation output
            
        Raises:
            BpmnErrorException: For business errors
            EligibilityServiceError: For service failures
        """
        logger.debug("Calling insurance API to verify eligibility")
        
        # 1. Call insurance API to verify eligibility
        try:
            eligibility_response = await self.insurance_api.verify_eligibility(
                patient_id=input_data.patient_id,
                insurance_id=input_data.insurance_id,
                card_number=input_data.card_number,
                encounter_date=input_data.encounter_date or date.today(),  # Use today if None
                procedure_codes=input_data.procedure_codes,
                tenant_id=input_data.tenant_id,
            )
        except ExternalServiceException as e:
            raise EligibilityServiceError(
                message=f"Insurance API call failed: {str(e)}",
                details={"original_error": str(e)},
            )
        
        # 2. Check eligibility status
        is_eligible = eligibility_response.get("is_eligible", False)
        coverage_status = eligibility_response.get("coverage_status", "INACTIVE")
        
        logger.debug(
            "Eligibility check result",
            is_eligible=is_eligible,
            coverage_status=coverage_status,
        )
        
        # 3. Handle ineligibility with BPMN errors
        if not is_eligible:
            errors = eligibility_response.get("errors", [])
            error_messages = "; ".join([e.get("errorMessage", "") for e in errors])
            
            # Determine BPMN error code based on status
            if coverage_status == "EXPIRED":
                error_code = "COVERAGE_EXPIRED"
            elif coverage_status == "SUSPENDED":
                error_code = "COVERAGE_SUSPENDED"
            elif coverage_status == "CANCELLED":
                error_code = "COVERAGE_CANCELLED"
            else:
                error_code = "INVALID_INSURANCE"
            
            logger.warning(
                "Patient not eligible",
                error_code=error_code,
                errors=error_messages,
            )
            
            # Throw BPMN error to trigger error boundary event
            raise BpmnErrorException(
                error_code=error_code,
                message=f"Patient not eligible: {error_messages}",
                details={
                    "coverageStatus": coverage_status,
                    "eligibilityErrors": errors,
                },
            )
        
        # 4. Build successful output
        output = ValidateEligibilityOutput(
            eligible=True,
            eligibility_status=coverage_status,
            coverage_start=eligibility_response.get("coverage_start_date"),
            coverage_end=eligibility_response.get("coverage_end_date"),
            plan_name=eligibility_response.get("plan_name"),
            member_id=eligibility_response.get("member_id"),
            payer_id=eligibility_response.get("payer_id"),
            payer_name=eligibility_response.get("payer_name"),
            copay_amount=eligibility_response.get("copay_amount"),
        )
        
        logger.debug("Eligibility validation successful")
        
        return output


# =============================================================================
# Worker Registration
# =============================================================================


def register_worker(
    worker_client: ExternalTaskWorker,
    insurance_api: Optional[InsuranceAPIClient] = None,
    tenant_context: Optional[TenantContext] = None,
) -> None:
    """
    Register ValidateEligibilityWorker with ExternalTaskWorker client.
    
    Args:
        worker_client: CIB7 external task worker client
        insurance_api: Insurance API client (optional, uses stub if None)
        tenant_context: Multi-tenant context manager
    """
    # Create worker instance
    worker = ValidateEligibilityWorker(
        insurance_api=insurance_api,
        tenant_context=tenant_context,
    )
    
    # Subscribe to topic
    worker_client.subscribe(
        topic="validate-eligibility",
        action=worker.execute,
        lock_duration=60000,  # 60 seconds
        variables=[
            "patientId",
            "insuranceId",
            "cardNumber",
            "encounterDate",
            "procedureCodes",
            "tenantId",
        ],
    )
    
    logger.info(
        "ValidateEligibilityWorker registered",
        topic="validate-eligibility",
        lock_duration=60000,
    )


# =============================================================================
# Standalone Execution (for testing)
# =============================================================================


if __name__ == "__main__":
    """
    Run worker standalone for local testing.
    
    Usage:
        python validate_eligibility_worker.py
    
    Configuration:
        Set environment variables:
        - CIB7_REST_URL: CIB7 REST API URL (default: http://localhost:8080/engine-rest)
        - WORKER_ID: Worker identifier (default: validate-eligibility-local)
    """
    import os
    
    # Get configuration from environment
    cib7_url = os.getenv("CIB7_REST_URL", "http://localhost:8080/engine-rest")
    worker_id = os.getenv("WORKER_ID", "validate-eligibility-local")
    
    # Create worker client
    worker_client = ExternalTaskWorker(
        worker_id=worker_id,
        base_url=cib7_url,
    )
    
    # Register worker
    register_worker(worker_client)
    
    # Start worker (blocking)
    print(f"Worker started: {worker_id}")
    print(f"CIB7 REST API: {cib7_url}")
    print(f"Topic: validate-eligibility")
    print("Press Ctrl+C to stop.")
    
    try:
        worker_client.start()
    except KeyboardInterrupt:
        print("\nWorker stopped.")
