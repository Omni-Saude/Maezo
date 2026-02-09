"""
CompensationHandlerWorker - Generic SAGA orchestrator for managing compensation workflows.

This worker orchestrates SAGA compensation by:
- Executing compensation steps in reverse order
- Handling partial failures
- Tracking completed and failed compensations
- Maintaining overall compensation status

Business Rule: RN-COMP-INDEX-SagaCompensation.md
SAGA Pattern: Master orchestrator for all compensation steps
Regulatory Compliance: ADR-010 (distributed transactions)
Migrated from: com.hospital.revenuecycle.delegates.compensation.CompensationHandlerDelegate
Topic: compensation-orchestrator
BPMN Compensation: Compensation Boundary Event Handler
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.compensation.models import CompensationStatus, CompensationReason

logger = structlog.get_logger(__name__)


class CompensationStep(BaseModel):
    """Model for a single compensation step."""

    step_id: str = Field(
        ...,
        alias="stepId",
        min_length=1,
        description="Unique step identifier",
    )
    step_name: str = Field(
        ...,
        alias="stepName",
        min_length=1,
        description="Human-readable step name",
    )
    worker_topic: str = Field(
        ...,
        alias="workerTopic",
        min_length=1,
        description="Zeebe worker topic to invoke",
    )
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Variables to pass to worker",
    )

    model_config = {"populate_by_name": True}


class CompensationHandlerInput(BaseModel):
    """Input model for CompensationHandlerWorker."""

    saga_id: str = Field(
        ...,
        alias="sagaId",
        min_length=1,
        description="SAGA transaction ID",
    )
    compensation_steps: list[CompensationStep] = Field(
        ...,
        alias="compensationSteps",
        min_items=1,
        description="List of compensation steps in reverse order",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="SAGA context and state",
    )

    model_config = {"populate_by_name": True}


class CompensationResult(BaseModel):
    """Model for compensation step result."""

    step_id: str = Field(
        ...,
        alias="stepId",
        description="Step identifier",
    )
    success: bool = Field(
        ...,
        description="Whether step succeeded",
    )
    status: CompensationStatus = Field(
        ...,
        description="Compensation status for this step",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Error message if failed",
    )

    model_config = {"populate_by_name": True}


class CompensationHandlerOutput(BaseModel):
    """Output model for CompensationHandlerWorker."""

    handler_success: bool = Field(
        ...,
        alias="handlerSuccess",
        description="Whether compensation handler succeeded",
    )
    overall_status: CompensationStatus = Field(
        ...,
        alias="overallStatus",
        description="Overall compensation status",
    )
    completed_steps: list[CompensationResult] = Field(
        default_factory=list,
        alias="completedSteps",
        description="List of completed compensation steps",
    )
    failed_steps: list[CompensationResult] = Field(
        default_factory=list,
        alias="failedSteps",
        description="List of failed compensation steps",
    )
    completion_count: int = Field(
        default=0,
        alias="completionCount",
        description="Number of successfully completed steps",
    )
    failure_count: int = Field(
        default=0,
        alias="failureCount",
        description="Number of failed steps",
    )
    handler_date: datetime = Field(
        ...,
        alias="handlerDate",
        description="When handler was executed",
    )
    error_message: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Overall error message if failed",
    )

    model_config = {"populate_by_name": True}


class CompensationOrchestrationError(BpmnErrorException):
    """Raised when compensation orchestration fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="COMPENSATION_ORCHESTRATION_ERROR",
            message=message,
            details=details,
        )


@worker(topic="compensation-orchestrator", max_jobs=8, lock_duration=60000)
class CompensationHandlerWorker(BaseWorker):
    """
    Generic SAGA orchestrator for managing compensation workflows.

    This worker orchestrates compensation by:
    1. Validating compensation request
    2. Executing compensation steps in reverse order
    3. Handling partial failures
    4. Tracking completed and failed compensations
    5. Maintaining overall compensation status
    6. Creating compensation audit records

    Input Variables:
        - sagaId: SAGA transaction ID (required)
        - compensationSteps: List of compensation steps (required)
        - context: SAGA context and state (optional)

    Output Variables:
        - handlerSuccess: Whether compensation handler succeeded (boolean)
        - overallStatus: Overall compensation status
        - completedSteps: List of completed steps with results
        - failedSteps: List of failed steps with errors
        - completionCount: Number of successfully completed steps
        - failureCount: Number of failed steps
        - handlerDate: When handler was executed

    SAGA Pattern:
        - This is the main compensation orchestrator
        - Executes compensation steps in reverse order
        - Tolerates partial failures (PARTIAL status)
        - Tracks all compensation operations
        - Creates audit trail for compliance

    Compensation Step Execution:
        - Steps are executed in order as provided (should be reverse order)
        - Each step invokes a specific Zeebe worker topic
        - Failed steps don't prevent subsequent steps from executing
        - Results are tracked for each step
        - Overall status depends on failure count:
            * All succeed: SUCCESS
            * Some fail: PARTIAL
            * All fail: FAILED

    Example:
        Input:
        {
            "sagaId": "SAGA-2026-001",
            "compensationSteps": [
                {
                    "stepId": "step-1",
                    "stepName": "Undo Billing",
                    "workerTopic": "compensate-charge-calculation",
                    "variables": {"calculationId": "CALC-001", "claimId": "CLM-001"}
                },
                {
                    "stepId": "step-2",
                    "stepName": "Cancel Claim",
                    "workerTopic": "compensate-claim-submission",
                    "variables": {"submissionId": "SUB-001", "claimId": "CLM-001"}
                }
            ]
        }

        Output (Success):
        {
            "handlerSuccess": true,
            "overallStatus": "SUCCESS",
            "completedSteps": [
                {"stepId": "step-1", "success": true, "status": "SUCCESS"},
                {"stepId": "step-2", "success": true, "status": "SUCCESS"}
            ],
            "failedSteps": [],
            "completionCount": 2,
            "failureCount": 0,
            "handlerDate": "2026-02-04T14:30:00Z"
        }

        Output (Partial Failure):
        {
            "handlerSuccess": false,
            "overallStatus": "PARTIAL",
            "completedSteps": [
                {"stepId": "step-1", "success": true, "status": "SUCCESS"}
            ],
            "failedSteps": [
                {"stepId": "step-2", "success": false, "status": "FAILED", "errorMessage": "..."}
            ],
            "completionCount": 1,
            "failureCount": 1,
            "handlerDate": "2026-02-04T14:30:00Z"
        }
    """

    def __init__(self, settings=None, audit_service=None, **kwargs):
        """
        Initialize the compensation handler worker.

        Args:
            settings: Optional worker settings
            audit_service: Optional audit service (for testing)
        """
        super().__init__(settings=settings)
        self._audit_service = audit_service

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "compensation_handler"

    @property
    def requires_idempotency(self) -> bool:
        """Compensation handling should be idempotent."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract parameters for idempotency key generation."""
        saga_id = variables.get("sagaId", "")
        return f"saga:{saga_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process compensation orchestration.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with compensation outcome
        """
        self._logger.info(
            "Processing compensation orchestration",
            job_key=str(getattr(job, "key", "unknown")),
            saga_id=variables.get("sagaId"),
            step_count=len(variables.get("compensationSteps", [])),
        )

        try:
            # Parse and validate input
            input_data = CompensationHandlerInput.model_validate(variables)

            # Execute compensation
            handler_result = await self._execute_compensation_orchestration(input_data)

            # Create audit trail entry
            if self._audit_service and hasattr(self._audit_service, "log_compensation"):
                await self._audit_service.log_compensation(input_data, handler_result)

            if handler_result.handler_success:
                self._logger.info(
                    "Compensation orchestration completed successfully",
                    saga_id=input_data.saga_id,
                    status=handler_result.overall_status.value,
                    completed=handler_result.completion_count,
                    failed=handler_result.failure_count,
                )
                return WorkerResult.ok(handler_result.model_dump(by_alias=True))
            else:
                self._logger.warning(
                    "Compensation orchestration completed with failures",
                    saga_id=input_data.saga_id,
                    status=handler_result.overall_status.value,
                    completed=handler_result.completion_count,
                    failed=handler_result.failure_count,
                    error=handler_result.error_message,
                )
                # Return with PARTIAL or FAILED status, don't fail the job
                return WorkerResult.ok(handler_result.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Compensation orchestration validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_ORCHESTRATION_DATA",
                error_message=f"Orchestration validation failed: {e}",
            )

        except CompensationOrchestrationError as e:
            self._logger.error(
                "Compensation orchestration error",
                error=str(e),
                error_code=e.error_code,
            )
            output = CompensationHandlerOutput(
                handler_success=False,
                overall_status=CompensationStatus.FAILED,
                handler_date=datetime.utcnow(),
                error_message=e.message,
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Unexpected error during compensation orchestration",
                error=str(e),
                exc_info=True,
            )
            output = CompensationHandlerOutput(
                handler_success=False,
                overall_status=CompensationStatus.FAILED,
                handler_date=datetime.utcnow(),
                error_message=f"Unexpected error: {e}",
            )
            return WorkerResult.ok(output.model_dump(by_alias=True))

    async def _execute_compensation_orchestration(
        self,
        input_data: CompensationHandlerInput,
    ) -> CompensationHandlerOutput:
        """
        Execute compensation orchestration.

        In production:
        - For each compensation step:
          1. Prepare worker invocation
          2. Invoke Zeebe worker via client
          3. Collect step result
          4. Log success/failure
        - Track overall status based on step outcomes
        - Return comprehensive results

        Args:
            input_data: Orchestration input data

        Returns:
            Orchestration output data
        """
        self._logger.info(
            "Executing compensation orchestration (PRODUCTION: invoke Zeebe workers)",
            saga_id=input_data.saga_id,
            step_count=len(input_data.compensation_steps),
        )

        completed_steps: list[CompensationResult] = []
        failed_steps: list[CompensationResult] = []

        # Execute each compensation step
        for step in input_data.compensation_steps:
            self._logger.info(
                "Executing compensation step",
                saga_id=input_data.saga_id,
                step_id=step.step_id,
                step_name=step.step_name,
                worker_topic=step.worker_topic,
            )

            try:
                # TODO: PRODUCTION IMPLEMENTATION REQUIRED
                # In production, use Zeebe client to invoke the worker:
                # result = await zeebe_client.invoke_worker(
                #     topic=step.worker_topic,
                #     variables=step.variables,
                #     timeout=45000
                # )

                # STUB: Simulate successful step completion
                step_result = CompensationResult(
                    step_id=step.step_id,
                    success=True,
                    status=CompensationStatus.SUCCESS,
                    error_message=None,
                )
                completed_steps.append(step_result)

            except Exception as e:
                self._logger.error(
                    "Compensation step failed",
                    saga_id=input_data.saga_id,
                    step_id=step.step_id,
                    error=str(e),
                )
                step_result = CompensationResult(
                    step_id=step.step_id,
                    success=False,
                    status=CompensationStatus.FAILED,
                    error_message=str(e),
                )
                failed_steps.append(step_result)

        # Determine overall status
        completion_count = len(completed_steps)
        failure_count = len(failed_steps)
        total_steps = completion_count + failure_count

        if failure_count == 0:
            overall_status = CompensationStatus.SUCCESS
            handler_success = True
            error_message = None
        elif completion_count == 0:
            overall_status = CompensationStatus.FAILED
            handler_success = False
            error_message = f"All {failure_count} compensation steps failed"
        else:
            overall_status = CompensationStatus.PARTIAL
            handler_success = False
            error_message = f"{completion_count}/{total_steps} compensation steps completed, {failure_count} failed"

        return CompensationHandlerOutput(
            handler_success=handler_success,
            overall_status=overall_status,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            completion_count=completion_count,
            failure_count=failure_count,
            handler_date=datetime.utcnow(),
            error_message=error_message,
        )
