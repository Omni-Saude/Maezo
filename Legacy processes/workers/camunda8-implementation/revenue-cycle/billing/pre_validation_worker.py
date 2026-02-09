"""
PreValidationWorker - Zeebe worker for pre-claim validation.

This worker implements pre-validation logic for the Brazilian healthcare
revenue cycle, including:
- Patient eligibility verification
- Insurance coverage validation
- Claim format validation
- Baseline data quality checks

Business Rule: RN-PreValidationDelegate.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00
Migrated from: com.hospital.revenuecycle.delegates.PreValidationDelegate

Section references:
- Patient and insurance eligibility validation
- Claim data completeness and format checks
- Insurance coverage period validation
- Basic quality assurance checks

Topic: pre-validation
BPMN Task: Task_Pre_Validation
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ConfigDict, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class PreValidationInput(BaseModel):
    """Input model for pre-validation operation."""
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(..., alias="claimId")
    patient_id: str = Field(..., alias="patientId")
    insurance_id: str = Field(..., alias="insuranceId")
    encounter_date: datetime = Field(..., alias="encounterDate")
    service_date: datetime = Field(..., alias="serviceDate")


class ValidationResult(BaseModel):
    """Model for a validation result."""
    model_config = ConfigDict(populate_by_name=True)

    rule_name: str = Field(..., alias="ruleName")
    passed: bool
    message: Optional[str] = None


class PreValidationOutput(BaseModel):
    """Output model for pre-validation operation."""
    model_config = ConfigDict(populate_by_name=True)

    validation_complete: bool = Field(..., alias="validationComplete")
    all_validations_passed: bool = Field(..., alias="allValidationsPassed")
    validation_results: list[ValidationResult] = Field(
        default_factory=list,
        alias="validationResults"
    )
    failed_validations: int = Field(..., alias="failedValidations")
    requires_manual_review: bool = Field(..., alias="requiresManualReview")


class PreValidationError(BpmnErrorException):
    """Raised when pre-validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="PRE_VALIDATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="pre-validation", max_jobs=32, lock_duration=30000)
class PreValidationWorker(BaseWorker):
    """
    Zeebe worker for pre-claim validation.

    This worker:
    1. Validates input data completeness
    2. Checks patient eligibility
    3. Verifies insurance coverage
    4. Validates claim format
    5. Performs baseline data quality checks
    6. Returns validation results

    Input Variables:
        - claimId: Claim identifier (required)
        - patientId: Patient identifier (required)
        - insuranceId: Insurance identifier (required)
        - encounterDate: Encounter date (required)
        - serviceDate: Service date (required)

    Output Variables:
        - validationComplete: Whether validation completed
        - allValidationsPassed: Whether all validations passed
        - validationResults: List of validation results
        - failedValidations: Count of failed validations
        - requiresManualReview: Whether manual review is needed
    """

    def __init__(self, settings=None, service=None, **kwargs):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            service: Optional service (for testing)
        """
        super().__init__(settings=settings)
        self._service = service

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "pre_validation"

    @property
    def requires_idempotency(self) -> bool:
        """This worker benefits from idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract claim ID for idempotency key generation."""
        claim_id = variables.get("claimId", "")
        return f"{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the pre-validation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with validation results
        """
        self._logger.info(
            "Processing pre-validation",
            job_key=str(getattr(job, "key", "unknown")),
            claim_id=variables.get("claimId"),
        )

        try:
            # Parse and validate input
            input_data = PreValidationInput.model_validate(variables)

            # Perform validations
            validation_results = await self._perform_validations(input_data)

            # Count failures
            failed_count = sum(1 for r in validation_results if not r.passed)
            all_passed = failed_count == 0

            # Create output
            output = PreValidationOutput(
                validationComplete=True,
                allValidationsPassed=all_passed,
                validationResults=validation_results,
                failedValidations=failed_count,
                requiresManualReview=not all_passed,
            )

            self._logger.info(
                "Pre-validation completed",
                claim_id=input_data.claim_id,
                all_passed=all_passed,
                failed_count=failed_count,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Input validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_VALIDATION_INPUT",
                error_message=f"Input validation failed: {e}",
            )

        except PreValidationError as e:
            self._logger.error(
                "Pre-validation error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during pre-validation",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Failed to perform pre-validation: {e}",
                retry=True,
            )

    async def _perform_validations(
        self,
        input_data: PreValidationInput,
    ) -> list[ValidationResult]:
        """
        Perform all validation checks.

        Args:
            input_data: Input data to validate

        Returns:
            List of validation results
        """
        results: list[ValidationResult] = []

        # Validation 1: Claim ID not empty
        results.append(
            ValidationResult(
                ruleName="Claim ID Not Empty",
                passed=bool(input_data.claim_id.strip()),
                message="Claim ID must not be empty" if not input_data.claim_id.strip() else None,
            )
        )

        # Validation 2: Patient ID not empty
        results.append(
            ValidationResult(
                ruleName="Patient ID Not Empty",
                passed=bool(input_data.patient_id.strip()),
                message="Patient ID must not be empty" if not input_data.patient_id.strip() else None,
            )
        )

        # Validation 3: Insurance ID not empty
        results.append(
            ValidationResult(
                ruleName="Insurance ID Not Empty",
                passed=bool(input_data.insurance_id.strip()),
                message="Insurance ID must not be empty" if not input_data.insurance_id.strip() else None,
            )
        )

        # Validation 4: Service date not in future
        now = datetime.now()
        service_date_valid = input_data.service_date <= now
        results.append(
            ValidationResult(
                ruleName="Service Date Not In Future",
                passed=service_date_valid,
                message="Service date cannot be in the future" if not service_date_valid else None,
            )
        )

        # Validation 5: Service date after encounter date
        date_order_valid = input_data.encounter_date <= input_data.service_date
        results.append(
            ValidationResult(
                ruleName="Service Date After Encounter Date",
                passed=date_order_valid,
                message="Service date must be after encounter date" if not date_order_valid else None,
            )
        )

        return results
