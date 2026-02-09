# Migration Comparison: Camunda8 (pyzeebe) → CIB7 (camunda-external-task-client-python3)

**Date:** 2026-02-09  
**Example Worker:** ValidateEligibilityWorker  
**Migration Tool:** Claude-flow Intelligence System

---

## Table of Contents

1. [Overview](#overview)
2. [Client Initialization](#client-initialization)
3. [Worker Registration](#worker-registration)
4. [Variable Access](#variable-access)
5. [Task Completion](#task-completion)
6. [BPMN Error Handling](#bpmn-error-handling)
7. [Task Failure (Retries)](#task-failure-retries)
8. [Multi-Tenancy](#multi-tenancy)
9. [Logging](#logging)
10. [Testing](#testing)
11. [Complete Example Comparison](#complete-example-comparison)

---

## Overview

| Aspect | Camunda8 (pyzeebe) | CIB7 (camunda-external-task-client-python3) |
|--------|-------------------|---------------------------------------------|
| **Communication** | gRPC (binary protocol) | REST API (HTTP/JSON) |
| **Client Library** | `pyzeebe` v3.x | `camunda-external-task-client-python3` v4.5.0 |
| **Architecture** | Push-based (Zeebe pushes tasks) | Pull-based (Worker polls for tasks) |
| **Worker Declaration** | `@worker` decorator | `worker_client.subscribe()` method |
| **Task Object** | Zeebe job object | CIB7 ExternalTask object |
| **Result Pattern** | Return dict or raise exception | Return TaskResult object |

---

## Client Initialization

### Camunda8 (pyzeebe)

```python
from pyzeebe import ZeebeWorker, create_insecure_channel

# Create gRPC channel
channel = create_insecure_channel(
    hostname="zeebe-gateway.default.svc.cluster.local",
    port=26500
)

# Create worker client
worker = ZeebeWorker(channel)

# Start worker (registers all @worker decorated functions)
worker.work()
```

### CIB7 (camunda-external-task-client-python3)

```python
from camunda.external_task.external_task_worker import ExternalTaskWorker

# Create worker client
worker_client = ExternalTaskWorker(
    worker_id="validate-eligibility-worker",
    base_url="http://localhost:8080/engine-rest",  # REST API endpoint
    config={
        "maxTasks": 10,            # Max tasks to fetch per poll
        "asyncResponseTimeout": 5000,  # Long polling timeout (ms)
        "lockDuration": 10000,     # Default task lock duration (ms)
    }
)

# Register workers (explicit subscription)
register_worker(worker_client)

# Start worker (blocking, polls for tasks)
worker_client.start()
```

**Key Differences:**
- ✅ CIB7 uses HTTP REST instead of gRPC
- ✅ CIB7 requires explicit worker registration (no decorator magic)
- ✅ CIB7 configuration is more explicit (polling intervals, batch sizes)

---

## Worker Registration

### Camunda8 (pyzeebe)

```python
from pyzeebe import worker

@worker(
    topic="validate-eligibility",
    lock_duration=60000,  # 60 seconds
    max_jobs=20,
)
class ValidateEligibilityWorker(BaseWorker):
    """Worker implementation."""
    
    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """Process task."""
        # Business logic here
        return WorkerResult.ok(output_dict)
```

**How it works:**
- Decorator automatically registers worker with Zeebe
- Worker is discovered at runtime
- `process_task` method is called for each job

### CIB7 (camunda-external-task-client-python3)

```python
from camunda.external_task.external_task import ExternalTask, TaskResult
from camunda.external_task.external_task_worker import ExternalTaskWorker

class ValidateEligibilityWorker:
    """Worker implementation."""
    
    async def execute(self, task: ExternalTask) -> TaskResult:
        """Execute task."""
        # Business logic here
        return task.complete(output_dict)

def register_worker(worker_client: ExternalTaskWorker) -> None:
    """Register worker with client."""
    worker = ValidateEligibilityWorker()
    
    worker_client.subscribe(
        topic="validate-eligibility",
        action=worker.execute,
        lock_duration=60000,  # 60 seconds
        variables=["patientId", "insuranceId", "tenantId"],  # Variables to fetch
    )
```

**Key Differences:**
- ✅ CIB7 requires explicit `subscribe()` call
- ✅ CIB7 lets you specify which variables to fetch (optimization)
- ✅ CIB7 registration is centralized in `register_worker()` function
- ✅ No inheritance required (can be plain class)

---

## Variable Access

### Camunda8 (pyzeebe)

```python
# Variables passed as dictionary
async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
    # Direct dictionary access
    patient_id = variables.get("patientId")
    insurance_id = variables.get("insuranceId")
    tenant_id = variables.get("tenantId")
    procedure_codes = variables.get("procedureCodes", [])
    
    # Or use job object
    # patient_id = job.variables.get("patientId")
```

### CIB7 (camunda-external-task-client-python3)

```python
# Variables accessed via task methods
async def execute(self, task: ExternalTask) -> TaskResult:
    # Get individual variable
    patient_id = task.get_variable("patientId")
    insurance_id = task.get_variable("insuranceId")
    tenant_id = task.get_variable("tenantId")
    
    # Get with default value
    procedure_codes = task.get_variable("procedureCodes", default=[])
    
    # Get all variables as dict
    all_vars = task.get_variables()
```

**Key Differences:**
- ✅ CIB7 uses `task.get_variable(name)` method
- ✅ CIB7 supports default values: `task.get_variable(name, default=value)`
- ✅ CIB7 can fetch all variables: `task.get_variables()`

**Best Practice:**
```python
# Use Pydantic for validation (works with both)
class WorkerInput(BaseModel):
    patient_id: str = Field(..., alias="patientId")
    insurance_id: str = Field(..., alias="insuranceId")
    tenant_id: Optional[str] = Field(None, alias="tenantId")

# Camunda8
input_data = WorkerInput.model_validate(variables)

# CIB7
input_data = WorkerInput.model_validate(task.get_variables())
```

---

## Task Completion

### Camunda8 (pyzeebe)

```python
async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
    # Process...
    
    # Return success with output variables
    return WorkerResult.ok({
        "eligible": True,
        "eligibilityStatus": "ACTIVE",
        "coverageStart": "2024-01-01",
        "coverageEnd": "2026-12-31",
    })
```

Or with helper:

```python
from pyzeebe import WorkerResult

# Success
return WorkerResult.ok(output_dict)

# Also works: direct dict return
return {
    "eligible": True,
    "eligibilityStatus": "ACTIVE",
}
```

### CIB7 (camunda-external-task-client-python3)

```python
async def execute(self, task: ExternalTask) -> TaskResult:
    # Process...
    
    # Complete task with output variables
    return task.complete({
        "eligible": True,
        "eligibilityStatus": "ACTIVE",
        "coverageStart": "2024-01-01",
        "coverageEnd": "2026-12-31",
    })
```

Or with local variables:

```python
# Complete with local variables (only visible to this scope)
return task.complete(
    global_variables={"eligible": True},
    local_variables={"internalFlag": True}
)
```

**Key Differences:**
- ✅ CIB7 uses `task.complete(variables)` method
- ✅ CIB7 returns `TaskResult` object (not dict)
- ✅ CIB7 supports local variables (scoped to task)

---

## BPMN Error Handling

BPMN errors are **business errors** that should be handled by the BPMN process (error boundary events).

### Camunda8 (pyzeebe)

```python
from pyzeebe import BpmnErrorException

async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
    if not eligibility_response.is_eligible:
        # Raise BPMN error
        raise BpmnErrorException(
            error_code="COVERAGE_EXPIRED",
            message="Insurance coverage has expired",
            variables={
                "coverageStatus": "EXPIRED",
                "expirationDate": "2025-12-31",
            }
        )
    
    # Or use WorkerResult
    return WorkerResult.bpmn_error(
        error_code="COVERAGE_EXPIRED",
        error_message="Insurance coverage has expired",
        variables={"coverageStatus": "EXPIRED"}
    )
```

### CIB7 (camunda-external-task-client-python3)

```python
from revenue_cycle.shared.exceptions import BpmnErrorException

async def execute(self, task: ExternalTask) -> TaskResult:
    if not eligibility_response.is_eligible:
        # Return BPMN error (preferred)
        return task.bpmn_error(
            error_code="COVERAGE_EXPIRED",
            error_message="Insurance coverage has expired",
            variables={
                "coverageStatus": "EXPIRED",
                "expirationDate": "2025-12-31",
            }
        )
    
    # Or catch exception and convert
    try:
        # Business logic
        pass
    except BpmnErrorException as e:
        return task.bpmn_error(
            error_code=e.error_code,
            error_message=str(e),
            variables=e.details or {}
        )
```

**Key Differences:**
- ✅ CIB7 prefers returning `task.bpmn_error()` over raising exceptions
- ✅ CIB7 method signature is consistent: `error_code`, `error_message`, `variables`
- ✅ Both support passing additional variables to process

**Common BPMN Error Codes (Healthcare):**
```python
# Eligibility errors
"COVERAGE_EXPIRED"
"COVERAGE_SUSPENDED"
"COVERAGE_CANCELLED"
"INVALID_INSURANCE"

# Coding errors
"ICD_CODE_NOT_FOUND"
"INVALID_PROCEDURE_CODE"
"AUDIT_FAILED"

# Billing errors
"GLOSA_DETECTED"
"CLAIM_REJECTED"
"INVALID_TISS_XML"
```

---

## Task Failure (Retries)

Task failures are **technical errors** that should be retried by the engine.

### Camunda8 (pyzeebe)

```python
async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
    try:
        # Call external service
        response = await insurance_api.verify_eligibility(...)
    except ExternalServiceException as e:
        # Return failure with retry
        return WorkerResult.failure(
            error_message=f"Insurance API failed: {str(e)}",
            retry=True,
            retry_timeout=5000,  # 5 seconds
        )
    
    # Or raise exception (automatic retry)
    except Exception as e:
        raise  # Zeebe will retry based on process configuration
```

### CIB7 (camunda-external-task-client-python3)

```python
async def execute(self, task: ExternalTask) -> TaskResult:
    try:
        # Call external service
        response = await insurance_api.verify_eligibility(...)
    except ExternalServiceException as e:
        # Return failure with retry configuration
        return task.failure(
            error_message=f"Insurance API failed: {str(e)}",
            error_details={"service": e.service_name, "status": e.status_code},
            max_retries=3,        # Retry up to 3 times
            retry_timeout=5000,   # 5 seconds between retries
        )
```

**Key Differences:**
- ✅ CIB7 uses `task.failure()` method
- ✅ CIB7 requires explicit `max_retries` count
- ✅ CIB7 supports `error_details` dict for structured error data
- ✅ CIB7 doesn't automatically retry on exception (must return failure)

**Retry Strategies:**

```python
# Transient errors - retry
return task.failure(
    error_message="Database connection timeout",
    max_retries=3,
    retry_timeout=5000,  # Exponential backoff handled by engine
)

# Permanent errors - no retry
return task.failure(
    error_message="Invalid patient ID format",
    max_retries=0,  # Don't retry
)

# Custom retry logic
if attempt < 3:
    return task.failure(
        error_message=f"API rate limit exceeded (attempt {attempt}/3)",
        max_retries=3,
        retry_timeout=60000,  # Wait 60 seconds (rate limit cooldown)
    )
```

---

## Multi-Tenancy

### Camunda8 (pyzeebe)

```python
# In Zeebe, tenant context usually passed as process variable
async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
    tenant_id = variables.get("tenantId")
    
    if tenant_id:
        # Set thread-local tenant context
        self.tenant_context.set_current_tenant(tenant_id)
        
        # Get tenant-specific credentials
        credentials = self.tenant_context.get_credentials("insurance_api", tenant_id)
        
        # Use tenant-specific database
        db = self.tenant_context.get_database(tenant_id)
    
    try:
        # Business logic with tenant context
        pass
    finally:
        if tenant_id:
            self.tenant_context.clear_current_tenant()
```

### CIB7 (camunda-external-task-client-python3)

```python
# Same pattern - tenant_id as process variable
async def execute(self, task: ExternalTask) -> TaskResult:
    tenant_id = task.get_variable("tenantId")
    
    if tenant_id:
        # Set thread-local tenant context
        self.tenant_context.set_current_tenant(tenant_id)
        
        # Get tenant-specific credentials
        credentials = self.tenant_context.get_credentials("insurance_api", tenant_id)
        
        # Use tenant-specific database
        db = self.tenant_context.get_database(tenant_id)
    
    try:
        # Business logic with tenant context
        pass
    finally:
        if tenant_id:
            self.tenant_context.clear_current_tenant()
```

**Key Differences:**
- ✅ Pattern is identical in both engines
- ✅ CIB7 has native tenant support in engine (can filter by tenant)
- ✅ CIB7 allows tenant-specific deployments

**Multi-Tenant Database Pattern:**

```python
# shared/multi_tenant/database.py
class TenantDatabaseManager:
    def get_database(self, tenant_id: str) -> Database:
        """Get tenant-specific database connection."""
        return self._connection_pool[tenant_id]

# shared/multi_tenant/credentials.py
class TenantCredentialManager:
    def get_credentials(self, service: str, tenant_id: str) -> dict:
        """Get tenant-specific API credentials."""
        # Hospital AUSTA uses UNIMED credentials
        # Hospital AMH uses Bradesco Saúde credentials
        return self._credential_vault.get(f"{tenant_id}:{service}")
```

---

## Logging

### Camunda8 (pyzeebe)

```python
import structlog

logger = structlog.get_logger(__name__)

async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
    job_key = str(getattr(job, "key", "unknown"))
    tenant_id = variables.get("tenantId")
    
    # Bind context to logger
    task_logger = logger.bind(
        job_key=job_key,
        tenant_id=tenant_id,
        patient_id=variables.get("patientId"),
    )
    
    task_logger.info("Starting eligibility validation")
    
    # Business logic...
    
    task_logger.info(
        "Eligibility validation completed",
        eligible=True,
        status="ACTIVE",
    )
```

### CIB7 (camunda-external-task-client-python3)

```python
import structlog

logger = structlog.get_logger(__name__)

async def execute(self, task: ExternalTask) -> TaskResult:
    task_id = task.get_task_id()
    business_key = task.get_business_key()
    tenant_id = task.get_variable("tenantId")
    
    # Bind context to logger
    task_logger = logger.bind(
        task_id=task_id,
        business_key=business_key,
        tenant_id=tenant_id,
        patient_id=task.get_variable("patientId"),
    )
    
    task_logger.info("Starting eligibility validation")
    
    # Business logic...
    
    task_logger.info(
        "Eligibility validation completed",
        eligible=True,
        status="ACTIVE",
    )
```

**Key Differences:**
- ✅ CIB7 uses `task.get_task_id()` instead of `job.key`
- ✅ CIB7 provides `task.get_business_key()` method
- ✅ Logging pattern is otherwise identical

**LGPD-Compliant Logging:**

```python
# shared/observability/logging.py
from revenue_cycle.shared.observability.redaction import redact_sensitive_data

def get_logger(name: str) -> structlog.BoundLogger:
    """Get logger with LGPD redaction."""
    return structlog.get_logger(name).bind(
        processor=redact_sensitive_data,  # Automatic PII redaction
    )

# Usage
logger.info(
    "Patient data",
    patient_name="João Silva",  # Will be redacted to "J***o S***a"
    cpf="123.456.789-00",       # Will be redacted to "***.***.***-**"
)
```

---

## Testing

### Camunda8 (pyzeebe)

```python
import pytest
from unittest.mock import AsyncMock, Mock, patch

@pytest.fixture
def mock_job():
    """Create mock Zeebe job."""
    job = Mock()
    job.key = 12345
    job.variables = {
        "patientId": "patient-123",
        "insuranceId": "insurance-456",
        "tenantId": "hospital-austa",
    }
    return job

@pytest.mark.asyncio
async def test_process_task_success(mock_job):
    """Test successful eligibility validation."""
    # Create worker
    worker = ValidateEligibilityWorker()
    
    # Mock insurance API
    worker._insurance_api = AsyncMock()
    worker._insurance_api.verify_eligibility.return_value = {
        "is_eligible": True,
        "coverage_status": "ACTIVE",
    }
    
    # Execute
    result = await worker.process_task(mock_job, mock_job.variables)
    
    # Verify
    assert result.is_success
    assert result.variables["eligible"] is True
```

### CIB7 (camunda-external-task-client-python3)

```python
import pytest
from unittest.mock import AsyncMock, Mock
from camunda.external_task.external_task import ExternalTask

@pytest.fixture
def mock_task():
    """Create mock CIB7 ExternalTask."""
    task = Mock(spec=ExternalTask)
    task.get_task_id.return_value = "task-123"
    task.get_business_key.return_value = "encounter-456"
    task.get_variables.return_value = {
        "patientId": "patient-123",
        "insuranceId": "insurance-456",
        "tenantId": "hospital-austa",
    }
    task.get_variable.side_effect = lambda key, default=None: (
        task.get_variables().get(key, default)
    )
    return task

@pytest.mark.asyncio
async def test_execute_success(mock_task):
    """Test successful eligibility validation."""
    # Create worker
    worker = ValidateEligibilityWorker()
    
    # Mock insurance API
    worker.insurance_api = AsyncMock()
    worker.insurance_api.verify_eligibility.return_value = {
        "is_eligible": True,
        "coverage_status": "ACTIVE",
    }
    
    # Execute
    result = await worker.execute(mock_task)
    
    # Verify task completion
    mock_task.complete.assert_called_once()
    output = mock_task.complete.call_args[0][0]
    assert output["eligible"] is True
```

**Key Differences:**
- ✅ CIB7 mocks `ExternalTask` spec
- ✅ CIB7 mocks `get_variable()` and `get_variables()` methods
- ✅ CIB7 verifies `task.complete()` was called
- ✅ Both use same AsyncMock pattern for external services

---

## Complete Example Comparison

### Camunda8 (pyzeebe) - Full Worker

```python
from pyzeebe import worker, WorkerResult, BpmnErrorException
from typing import Any
import structlog

logger = structlog.get_logger(__name__)

@worker(topic="validate-eligibility", lock_duration=60000, max_jobs=20)
class ValidateEligibilityWorker(BaseWorker):
    """Validate patient insurance eligibility."""
    
    def __init__(self, settings=None, insurance_service=None):
        super().__init__(settings=settings)
        self._insurance_api = insurance_service or StubInsuranceAPIClient()
        self._logger = logger.bind(worker=self.worker_name)
    
    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """Process eligibility validation."""
        tenant_id = variables.get("tenantId")
        
        self._logger.info(
            "Starting eligibility validation",
            job_key=str(getattr(job, "key", "unknown")),
            tenant_id=tenant_id,
        )
        
        try:
            # Parse input
            patient_id = variables.get("patientId")
            insurance_id = variables.get("insuranceId")
            
            # Call insurance API
            response = await self._insurance_api.verify_eligibility(
                patient_id=patient_id,
                insurance_id=insurance_id,
                tenant_id=tenant_id,
            )
            
            # Check eligibility
            if not response.get("is_eligible"):
                raise BpmnErrorException(
                    error_code="COVERAGE_EXPIRED",
                    message="Patient not eligible",
                    variables={"coverageStatus": response.get("coverage_status")}
                )
            
            # Return success
            return WorkerResult.ok({
                "eligible": True,
                "eligibilityStatus": response.get("coverage_status"),
                "payerId": response.get("payer_id"),
            })
        
        except BpmnErrorException:
            raise  # Re-raise BPMN errors
        
        except ExternalServiceException as e:
            return WorkerResult.failure(
                error_message=str(e),
                retry=True,
                retry_timeout=5000,
            )
        
        except Exception as e:
            self._logger.exception("Unexpected error", error=str(e))
            return WorkerResult.failure(
                error_message=f"Unexpected error: {str(e)}",
                retry=False,
            )
```

### CIB7 (camunda-external-task-client-python3) - Full Worker

```python
from camunda.external_task.external_task import ExternalTask, TaskResult
from camunda.external_task.external_task_worker import ExternalTaskWorker
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

class ValidateEligibilityWorker:
    """Validate patient insurance eligibility."""
    
    def __init__(
        self,
        insurance_api: Optional[InsuranceAPIClient] = None,
        tenant_context: Optional[TenantContext] = None,
    ):
        self.insurance_api = insurance_api or StubInsuranceAPIClient()
        self.tenant_context = tenant_context or TenantContext()
        self.logger = logger.bind(worker="ValidateEligibilityWorker")
    
    async def execute(self, task: ExternalTask) -> TaskResult:
        """Execute eligibility validation."""
        task_id = task.get_task_id()
        tenant_id = task.get_variable("tenantId")
        
        self.logger.info(
            "Starting eligibility validation",
            task_id=task_id,
            tenant_id=tenant_id,
        )
        
        try:
            # Parse input
            patient_id = task.get_variable("patientId")
            insurance_id = task.get_variable("insuranceId")
            
            # Call insurance API
            response = await self.insurance_api.verify_eligibility(
                patient_id=patient_id,
                insurance_id=insurance_id,
                tenant_id=tenant_id,
            )
            
            # Check eligibility
            if not response.get("is_eligible"):
                return task.bpmn_error(
                    error_code="COVERAGE_EXPIRED",
                    error_message="Patient not eligible",
                    variables={"coverageStatus": response.get("coverage_status")}
                )
            
            # Return success
            return task.complete({
                "eligible": True,
                "eligibilityStatus": response.get("coverage_status"),
                "payerId": response.get("payer_id"),
            })
        
        except BpmnErrorException as e:
            return task.bpmn_error(
                error_code=e.error_code,
                error_message=str(e),
                variables=e.details or {}
            )
        
        except ExternalServiceException as e:
            return task.failure(
                error_message=str(e),
                error_details=e.details or {},
                max_retries=3,
                retry_timeout=5000,
            )
        
        except Exception as e:
            self.logger.exception("Unexpected error", error=str(e))
            return task.failure(
                error_message=f"Unexpected error: {str(e)}",
                error_details={"error_type": type(e).__name__},
                max_retries=0,
            )

def register_worker(worker_client: ExternalTaskWorker) -> None:
    """Register worker with client."""
    worker = ValidateEligibilityWorker()
    
    worker_client.subscribe(
        topic="validate-eligibility",
        action=worker.execute,
        lock_duration=60000,
        variables=["patientId", "insuranceId", "tenantId"],
    )
```

---

## Migration Checklist

When migrating a Camunda8 worker to CIB7, follow this checklist:

### 1. Imports
- [ ] Change `from pyzeebe import ...` → `from camunda.external_task import ...`
- [ ] Update: `ZeebeWorker` → `ExternalTaskWorker`
- [ ] Update: `@worker` → manual `subscribe()` call
- [ ] Keep: `structlog`, `pydantic`, domain models

### 2. Worker Class
- [ ] Remove `BaseWorker` inheritance (optional in CIB7)
- [ ] Rename: `process_task()` → `execute()`
- [ ] Change signature: `(job, variables)` → `(task)`
- [ ] Update return type: `WorkerResult` → `TaskResult`

### 3. Variable Access
- [ ] Change: `variables.get("key")` → `task.get_variable("key")`
- [ ] Change: `job.variables` → `task.get_variables()`
- [ ] Add default values: `task.get_variable("key", default=value)`

### 4. Task Completion
- [ ] Change: `return WorkerResult.ok(dict)` → `return task.complete(dict)`
- [ ] Change: `return dict` → `return task.complete(dict)`

### 5. BPMN Errors
- [ ] Change: `raise BpmnErrorException(...)` → `return task.bpmn_error(...)`
- [ ] Or: catch exception and convert to `task.bpmn_error()`
- [ ] Preserve error codes and messages

### 6. Task Failures
- [ ] Change: `return WorkerResult.failure(...)` → `return task.failure(...)`
- [ ] Add: `max_retries` parameter
- [ ] Add: `retry_timeout` parameter
- [ ] Optional: `error_details` dict

### 7. Logging
- [ ] Change: `job.key` → `task.get_task_id()`
- [ ] Add: `task.get_business_key()`
- [ ] Keep: structured logging with `bind()`

### 8. Registration
- [ ] Remove: `@worker` decorator
- [ ] Create: `register_worker(worker_client)` function
- [ ] Add: `worker_client.subscribe(topic, action, ...)`
- [ ] Specify: variables to fetch

### 9. Client Initialization
- [ ] Change: `ZeebeWorker(channel)` → `ExternalTaskWorker(worker_id, base_url)`
- [ ] Update: hostname/port → REST URL
- [ ] Configure: `maxTasks`, `asyncResponseTimeout`, `lockDuration`

### 10. Testing
- [ ] Mock: `ExternalTask` instead of Zeebe job
- [ ] Mock: `get_variable()`, `get_variables()`, `complete()`
- [ ] Verify: `task.complete()` called with expected variables

---

## Quick Reference

| Operation | Camunda8 | CIB7 |
|-----------|----------|------|
| **Get variable** | `variables.get("key")` | `task.get_variable("key")` |
| **Get all variables** | `variables` (dict) | `task.get_variables()` |
| **Complete task** | `return WorkerResult.ok(dict)` | `return task.complete(dict)` |
| **BPMN error** | `raise BpmnErrorException(...)` | `return task.bpmn_error(...)` |
| **Task failure** | `return WorkerResult.failure(...)` | `return task.failure(...)` |
| **Task ID** | `job.key` | `task.get_task_id()` |
| **Business key** | `job.business_key` | `task.get_business_key()` |
| **Worker registration** | `@worker(topic="...")` | `worker_client.subscribe(topic="...")` |

---

## Additional Resources

- **CIB7 External Task Pattern:** https://docs.camunda.org/manual/7.21/user-guide/process-engine/external-tasks/
- **Python Client Library:** https://pypi.org/project/camunda-external-task-client-python3/
- **BPMN Error Events:** https://docs.camunda.org/manual/7.21/reference/bpmn20/events/error-events/
- **Multi-Instance Tasks:** https://docs.camunda.org/manual/7.21/reference/bpmn20/tasks/task-markers/

---

**Generated:** 2026-02-09  
**Migration Tool:** Claude-flow Intelligence System  
**Project:** Healthcare Revenue Cycle Orchestration - CIB7 Migration  
**Example Worker:** ValidateEligibilityWorker (880 lines)
