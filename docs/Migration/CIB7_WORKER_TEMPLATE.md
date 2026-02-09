# CIB7 Worker Template - Python External Task Pattern

**Date:** 2026-02-09  
**Version:** 1.0  
**Target Engine:** CIB Seven 2.1.3  
**Client Library:** camunda-external-task-client-python3 v4.5.0

---

## Table of Contents

- [CIB7 Worker Template - Python External Task Pattern](#cib7-worker-template---python-external-task-pattern)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Template Structure](#template-structure)
  - [Key Differences from Camunda8](#key-differences-from-camunda8)
  - [Complete Worker Template](#complete-worker-template)
  - [Multi-Tenancy Pattern](#multi-tenancy-pattern)
  - [Error Handling Pattern](#error-handling-pattern)
    - [BPMN Errors (Business Errors)](#bpmn-errors-business-errors)
    - [Technical Errors (Retry-able)](#technical-errors-retry-able)
    - [Fatal Errors (No Retry)](#fatal-errors-no-retry)
  - [Testing Pattern](#testing-pattern)
  - [Migration Checklist](#migration-checklist)
  - [Additional Resources](#additional-resources)

---

## Overview

This template provides the standard structure for CIB7 Python external task workers. It incorporates:

- ✅ **REST API Communication** (vs Zeebe gRPC)
- ✅ **Multi-tenancy Support** (tenant_id in variables)
- ✅ **BPMN Error Handling** (throwBpmnError)
- ✅ **Structured Logging** (LGPD-compliant)
- ✅ **Type Safety** (Pydantic models)
- ✅ **Dependency Injection** (optional)

---

## Template Structure

```text
workers/
├── revenue-cycle/
│   ├── billing/
│   │   ├── __init__.py
│   │   ├── validate_eligibility_worker.py    # Worker implementation
│   │   └── models.py                         # Pydantic models
├── shared/
│   ├── base_worker.py                        # Base worker class
│   ├── exceptions.py                         # Custom exceptions
│   └── multi_tenant/
│       └── context.py                        # Tenant context
└── main.py                                    # Worker registration
```

---

## Key Differences from Camunda8

| Aspect | Camunda8 (pyzeebe) | CIB7 (camunda-external-task-client-python3) |
|--------|-------------------|---------------------------------------------|
| **Communication** | gRPC | REST API (HTTP/HTTPS) |
| **Task Subscription** | `@worker(task_type="...")` | `ExternalTaskWorker().subscribe(...)` |
| **Variables Access** | `task.variables` | `task.get_variable(name)` |
| **Complete Task** | `return {"key": value}` | `return task.complete({"key": value})` |
| **BPMN Error** | Raise `BpmnErrorException` | `return task.bpmn_error(error_code, msg)` |
| **Failure** | Raise `Exception` | `return task.failure(msg, details, retries)` |
| **Client Init** | `ZeebeWorker(hostname, port)` | `ExternalTaskWorker(worker_id, base_url)` |
| **Variable Setting** | Direct dict return | `task.complete(variables)` |
| **Lock Duration** | Configured per task type | Passed in `subscribe()` |
| **Multi-tenancy** | Process instance variables | Task variables `tenant_id` |

---

## Complete Worker Template

```python
"""
{WorkerName} - {Brief Description}

Business Rule: {RN-XXX-YYY.md reference}
Regulatory Compliance: {ANS, TISS, LGPD requirements}
BPMN Process: {Process name and task ID}

{Detailed description of what this worker does}

Migration Notes:
- Migrated from Camunda8/pyzeebe to CIB7/camunda-external-task-client-python3
- Changed from gRPC to REST API communication
- Updated error handling to use task.bpmn_error() and task.failure()
- Added multi-tenant context support via tenant_id variable
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog
from camunda.external_task.external_task import ExternalTask, TaskResult
from camunda.external_task.external_task_worker import ExternalTaskWorker
from pydantic import BaseModel, Field, validator

from revenue_cycle.shared.exceptions import (
    BpmnErrorException,
    ExternalServiceException,
)
from revenue_cycle.shared.multi_tenant.context import TenantContext
from revenue_cycle.shared.observability.logging import get_logger
from revenue_cycle.shared.observability.metrics import track_task_execution

# Initialize logger
logger = get_logger(__name__)


# =============================================================================
# Input/Output Models (Pydantic for validation)
# =============================================================================


class WorkerInput(BaseModel):
    """Input variables expected by this worker."""
    
    # Required fields
    patient_id: str = Field(..., description="Patient identifier")
    encounter_id: str = Field(..., description="Encounter/visit identifier")
    
    # Optional fields
    tenant_id: Optional[str] = Field(None, description="Tenant identifier for multi-tenancy")
    
    # Add validators
    @validator("patient_id")
    def validate_patient_id(cls, v):
        if not v or not v.strip():
            raise ValueError("patient_id cannot be empty")
        return v.strip()
    
    class Config:
        # Allow extra fields that might be passed by process
        extra = "allow"


class WorkerOutput(BaseModel):
    """Output variables produced by this worker."""
    
    # Result fields
    result_status: str = Field(..., description="Processing status: SUCCESS, FAILED, PARTIAL")
    result_message: str = Field(..., description="Human-readable result message")
    
    # Business data
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Convert to dict for CIB7 variables
    def to_variables(self) -> dict[str, Any]:
        """Convert output model to CIB7 process variables."""
        return self.dict(exclude_none=True, by_alias=True)


# =============================================================================
# Worker Implementation
# =============================================================================


class WorkerNameWorker:
    """
    External task worker for {task type}.
    
    Subscribes to: {task-topic-name}
    """
    
    def __init__(
        self,
        # Inject dependencies here
        # example: insurance_client: InsuranceAPIClient,
        tenant_context: Optional[TenantContext] = None,
    ):
        """
        Initialize worker with dependencies.
        
        Args:
            tenant_context: Multi-tenant context manager
        """
        self.tenant_context = tenant_context or TenantContext()
        self.logger = logger.bind(worker="WorkerNameWorker")
    
    @track_task_execution(metric_name="worker_name_execution")
    async def execute(self, task: ExternalTask) -> TaskResult:
        """
        Execute the external task.
        
        Args:
            task: External task from CIB7 engine
            
        Returns:
            TaskResult with completed task, BPMN error, or failure
        """
        # Extract task context
        task_id = task.get_task_id()
        business_key = task.get_business_key()
        
        # Bind logger with context
        task_logger = self.logger.bind(
            task_id=task_id,
            business_key=business_key,
        )
        
        task_logger.info("Starting task execution")
        
        try:
            # 1. Parse and validate input variables
            input_data = self._parse_input(task)
            
            task_logger = task_logger.bind(
                patient_id=input_data.patient_id,
                tenant_id=input_data.tenant_id,
            )
            
            # 2. Set multi-tenant context (if applicable)
            if input_data.tenant_id:
                self.tenant_context.set_current_tenant(input_data.tenant_id)
            
            # 3. Execute business logic
            result = await self._execute_business_logic(input_data, task_logger)
            
            # 4. Prepare output variables
            output = WorkerOutput(
                result_status="SUCCESS",
                result_message="Task completed successfully",
                # Add business-specific fields
            )
            
            task_logger.info(
                "Task execution completed successfully",
                result_status=output.result_status,
            )
            
            # 5. Complete task with output variables
            return task.complete(output.to_variables())
        
        except BpmnErrorException as e:
            # Business error - throw BPMN error to trigger error event
            task_logger.warning(
                "BPMN error occurred",
                error_code=e.error_code,
                error_message=str(e),
            )
            
            # Return BPMN error (will trigger boundary error event in BPMN)
            return task.bpmn_error(
                error_code=e.error_code,
                error_message=str(e),
                variables=e.details or {},
            )
        
        except ExternalServiceException as e:
            # External service failure - retry with backoff
            task_logger.error(
                "External service error - will retry",
                service_name=e.service_name,
                error=str(e),
            )
            
            # Return failure (task will be retried by engine)
            return task.failure(
                error_message=str(e),
                error_details=e.details or {},
                max_retries=3,
                retry_timeout=5000,  # 5 seconds
            )
        
        except Exception as e:
            # Unexpected error - log and fail
            task_logger.exception(
                "Unexpected error during task execution",
                error=str(e),
            )
            
            # Return failure without retries for unexpected errors
            return task.failure(
                error_message=f"Unexpected error: {str(e)}",
                error_details={"error_type": type(e).__name__},
                max_retries=0,
            )
        
        finally:
            # Cleanup (if needed)
            if input_data.tenant_id:
                self.tenant_context.clear_current_tenant()
    
    def _parse_input(self, task: ExternalTask) -> WorkerInput:
        """
        Parse and validate input variables from task.
        
        Args:
            task: External task
            
        Returns:
            Validated input data
            
        Raises:
            ValueError: If input validation fails
        """
        # Get all variables from task
        variables = task.get_variables()
        
        # Parse using Pydantic model
        try:
            return WorkerInput(**variables)
        except Exception as e:
            self.logger.error(
                "Input validation failed",
                error=str(e),
                variables=variables,
            )
            raise ValueError(f"Invalid input variables: {str(e)}") from e
    
    async def _execute_business_logic(
        self,
        input_data: WorkerInput,
        logger: structlog.BoundLogger,
    ) -> dict[str, Any]:
        """
        Execute the core business logic.
        
        Args:
            input_data: Validated input data
            logger: Bound logger with context
            
        Returns:
            Business logic results
            
        Raises:
            BpmnErrorException: For business errors
            ExternalServiceException: For external service failures
        """
        logger.debug("Executing business logic")
        
        # TODO: Implement actual business logic here
        
        # Example: Call external service
        # result = await self.insurance_client.verify_eligibility(...)
        
        # Example: Throw BPMN error for business condition
        # if not result.is_eligible:
        #     raise BpmnErrorException(
        #         error_code="ELIGIBILITY_FAILED",
        #         message="Patient not eligible for procedure",
        #         details={"reason": result.reason}
        #     )
        
        logger.debug("Business logic completed")
        
        return {}


# =============================================================================
# Worker Registration
# =============================================================================


def register_worker(
    worker_client: ExternalTaskWorker,
    # Add service dependencies here
    tenant_context: Optional[TenantContext] = None,
) -> None:
    """
    Register this worker with the ExternalTaskWorker client.
    
    Args:
        worker_client: CIB7 external task worker client
        tenant_context: Multi-tenant context
    """
    # Create worker instance
    worker = WorkerNameWorker(tenant_context=tenant_context)
    
    # Subscribe to topic
    worker_client.subscribe(
        topic="worker-topic-name",  # Must match BPMN task topic
        action=worker.execute,
        lock_duration=10000,  # 10 seconds lock
        variables=["patient_id", "encounter_id", "tenant_id"],  # Variables to fetch
    )
    
    logger.info(
        "Worker registered",
        topic="worker-topic-name",
        lock_duration=10000,
    )


# =============================================================================
# Standalone Execution (for testing)
# =============================================================================


if __name__ == "__main__":
    import asyncio
    from camunda.external_task.external_task_worker import ExternalTaskWorker
    
    # Configure worker
    worker_client = ExternalTaskWorker(
        worker_id="worker-name-local",
        base_url="http://localhost:8080/engine-rest",  # CIB7 REST API
    )
    
    # Register worker
    register_worker(worker_client)
    
    # Start worker (blocking)
    print("Worker started. Press Ctrl+C to stop.")
    worker_client.start()
```

---

## Multi-Tenancy Pattern

```python
# In your worker execute method:

# 1. Extract tenant_id from task variables
tenant_id = task.get_variable("tenant_id")

if tenant_id:
    # 2. Set tenant context (thread-local)
    self.tenant_context.set_current_tenant(tenant_id)
    
    # 3. Get tenant-specific credentials
    credentials = self.tenant_context.get_credentials(
        service="insurance_api",
        tenant_id=tenant_id,
    )
    
    # 4. Use tenant-specific database connection
    db = self.tenant_context.get_database(tenant_id)
    
    # 5. Apply tenant-specific business rules
    rules = self.tenant_context.get_business_rules(tenant_id)

# Always cleanup in finally block
finally:
    if tenant_id:
        self.tenant_context.clear_current_tenant()
```

---

## Error Handling Pattern

### BPMN Errors (Business Errors)

```python
# Use for expected business conditions that should be handled by BPMN

# 1. Define custom exception
class EligibilityFailedError(BpmnErrorException):
    def __init__(self, reason: str, details: dict):
        super().__init__(
            error_code="ELIGIBILITY_FAILED",  # Must match BPMN error event
            message=f"Eligibility check failed: {reason}",
            details=details,
        )

# 2. Raise in business logic
if not eligibility_result.is_eligible:
    raise EligibilityFailedError(
        reason=eligibility_result.reason,
        details={
            "patient_id": input_data.patient_id,
            "insurance_id": input_data.insurance_id,
        }
    )

# 3. Catch in execute() and return BPMN error
except BpmnErrorException as e:
    return task.bpmn_error(
        error_code=e.error_code,
        error_message=str(e),
        variables=e.details or {},
    )
```

### Technical Errors (Retry-able)

```python
# Use for transient failures that should be retried

# 1. Raise external service exception
if api_response.status_code >= 500:
    raise ExternalServiceException(
        service_name="InsuranceAPI",
        operation="verify_eligibility",
        message=f"API returned {api_response.status_code}",
        status_code=api_response.status_code,
    )

# 2. Catch and return failure with retries
except ExternalServiceException as e:
    return task.failure(
        error_message=str(e),
        error_details=e.details or {},
        max_retries=3,          # Retry 3 times
        retry_timeout=5000,     # Wait 5 seconds between retries
    )
```

### Fatal Errors (No Retry)

```python
# Use for permanent failures that shouldn't be retried

except ValueError as e:
    return task.failure(
        error_message=f"Invalid input: {str(e)}",
        error_details={"validation_error": str(e)},
        max_retries=0,  # No retries
    )
```

---

## Testing Pattern

```python
# tests/workers/test_worker_name_worker.py

import pytest
from unittest.mock import AsyncMock, Mock
from camunda.external_task.external_task import ExternalTask

from revenue_cycle.workers.billing.worker_name_worker import (
    WorkerNameWorker,
    WorkerInput,
)


@pytest.fixture
def mock_task():
    """Create a mock ExternalTask."""
    task = Mock(spec=ExternalTask)
    task.get_task_id.return_value = "task-123"
    task.get_business_key.return_value = "encounter-456"
    task.get_variables.return_value = {
        "patient_id": "patient-789",
        "encounter_id": "encounter-456",
        "tenant_id": "hospital-austa",
    }
    task.get_variable.side_effect = lambda key: task.get_variables().get(key)
    return task


@pytest.fixture
def worker():
    """Create worker instance."""
    return WorkerNameWorker()


@pytest.mark.asyncio
async def test_execute_success(worker, mock_task):
    """Test successful task execution."""
    # Execute
    result = await worker.execute(mock_task)
    
    # Verify task completion was called
    mock_task.complete.assert_called_once()
    
    # Verify output variables
    output_vars = mock_task.complete.call_args[0][0]
    assert output_vars["result_status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_execute_bpmn_error(worker, mock_task):
    """Test BPMN error handling."""
    # TODO: Mock service to raise BpmnErrorException
    
    # Execute
    result = await worker.execute(mock_task)
    
    # Verify BPMN error was thrown
    mock_task.bpmn_error.assert_called_once()
    args = mock_task.bpmn_error.call_args[1]
    assert args["error_code"] == "EXPECTED_ERROR_CODE"


@pytest.mark.asyncio
async def test_execute_service_failure_retry(worker, mock_task):
    """Test retry on external service failure."""
    # TODO: Mock service to raise ExternalServiceException
    
    # Execute
    result = await worker.execute(mock_task)
    
    # Verify failure with retries
    mock_task.failure.assert_called_once()
    args = mock_task.failure.call_args[1]
    assert args["max_retries"] == 3


def test_parse_input_valid(worker, mock_task):
    """Test input parsing with valid data."""
    input_data = worker._parse_input(mock_task)
    
    assert input_data.patient_id == "patient-789"
    assert input_data.encounter_id == "encounter-456"
    assert input_data.tenant_id == "hospital-austa"


def test_parse_input_invalid(worker, mock_task):
    """Test input parsing with invalid data."""
    mock_task.get_variables.return_value = {}
    
    with pytest.raises(ValueError, match="Invalid input"):
        worker._parse_input(mock_task)
```

---

## Migration Checklist

When migrating a Camunda8 worker to CIB7:

- [ ] Update imports: `pyzeebe` → `camunda.external_task`
- [ ] Change decorator: `@worker(task_type="...")` → `worker_client.subscribe(...)`
- [ ] Update variable access: `task.variables` → `task.get_variable(name)`
- [ ] Change completion: `return dict` → `return task.complete(dict)`
- [ ] Update BPMN errors: raise exception → `return task.bpmn_error(...)`
- [ ] Update failures: raise exception → `return task.failure(...)`
- [ ] Add multi-tenancy: Extract `tenant_id` from variables
- [ ] Update client initialization in main.py
- [ ] Update tests: Mock `ExternalTask` instead of Zeebe task
- [ ] Verify BPMN task topic name matches subscription
- [ ] Test with local CIB7 instance
- [ ] Update documentation

---

## Additional Resources

- [CIB Seven Documentation](https://docs.camunda.org/manual/7.21/)
- [camunda-external-task-client-python3 on PyPI](https://pypi.org/project/camunda-external-task-client-python3/)
- [BPMN 2.0 Error Events](https://docs.camunda.org/manual/7.21/reference/bpmn20/events/error-events/)
- [External Task Pattern](https://docs.camunda.org/manual/7.21/user-guide/process-engine/external-tasks/)

---

**Generated:** 2026-02-09  
**Migration Tool:** Claude-flow Intelligence System  
**Project:** Healthcare Revenue Cycle Orchestration - CIB7 Migration
