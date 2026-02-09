# API Mapping: Camunda8 (Zeebe) → CIB7

**Purpose:** Quick reference for converting Zeebe API calls to CIB7 REST API  
**Version:** 1.0  

## Client Initialization

| Operation | Camunda8 (pyzeebe) | CIB7 (camunda-external-task-client-python3) |
|-----------|-------------------|---------------------------------------------|
| **Import** | `from pyzeebe import ZeebeClient` | `from camunda.external_task.external_task_worker import ExternalTaskWorker` |
| **Create client** | `client = ZeebeClient(hostname="...", port=26500)` | `worker = ExternalTaskWorker(worker_id="...", base_url="http://...:8080/engine-rest")` |
| **Authentication** | OAuth2 via credentials object | Optional: Basic Auth, OAuth2, or None |

## Task Subscription

| Operation | Camunda8 (pyzeebe) | CIB7 |
|-----------|-------------------|------|
| **Subscribe** | `@client.job(task_type="my-topic")` decorator | `worker.subscribe("my-topic", handler_function, tenant_id="...")` |
| **Max tasks** | `maxJobsToActivate` in decorator | `config={"maxTasks": 10}` in worker init |
| **Lock duration** | `timeout_ms` parameter | `config={"lockDuration": 300000}` (5 min) |

## Task Handler

| Operation | Camunda8 (pyzeebe) | CIB7 |
|-----------|-------------------|------|
| **Handler signature** | `def handler(job)` | `def handler(task)` |
| **Get variable** | `job.variables.get("key")` | `task.get_variable("key")` |
| **Get all variables** | `job.variables` (dict) | `task.variables` (dict) |
| **Task ID** | `job.key` | `task.get_task_id()` |
| **Process instance ID** | `job.processInstanceKey` | `task.get_process_instance_id()` |
| **Activity ID** | `job.elementId` | `task.get_activity_id()` |
| **Worker ID** | `job.worker` | `task.get_worker_id()` |

## Task Completion

| Operation | Camunda8 (pyzeebe) | CIB7 |
|-----------|-------------------|------|
| **Complete success** | `return {"var1": "value"}` | `return {"var1": "value"}` (same) |
| **Complete with variables** | `job.set_success({"var": "val"})` | `return task.complete({"var": "val"})` |

## Error Handling

| Operation | Camunda8 (pyzeebe) | CIB7 |
|-----------|-------------------|------|
| **Technical failure** | `job.set_failure(message="...", retries=3)` | `return task.failure(error_message="...", retries=3, retry_timeout=5000)` |
| **Business error** | `job.throw_error(error_code="ERR_CODE", error_message="...")` | `return task.bpmn_error(error_code="ERR_CODE", error_message="...")` |
| **Include stack trace** | Not available | `error_details={"trace": traceback.format_exc()}` |

## Error Code Mapping

Common Zeebe error codes → BPMN error codes:

| Zeebe Error | BPMN Error Code | Description |
|-------------|-----------------|-------------|
| `RESOURCE_EXHAUSTED` | `RESOURCE_UNAVAILABLE` | External service unavailable |
| `DEADLINE_EXCEEDED` | `TIMEOUT` | Operation timeout |
| `INVALID_ARGUMENT` | `VALIDATION_ERROR` | Invalid input data |
| `PERMISSION_DENIED` | `AUTH_ERROR` | Authorization failed |
| `NOT_FOUND` | `RESOURCE_NOT_FOUND` | Resource doesn't exist |
| Custom codes | Keep same codes | Your business error codes (AUTH_INVALID, GLOSA_REJECTED, etc.) |

## Variables

| Operation | Camunda8 (pyzeebe) | CIB7 |
|-----------|-------------------|------|
| **Access variable** | `job.variables.get("key")` | `task.get_variable("key")` |
| **Default value** | `job.variables.get("key", "default")` | `task.get_variable("key", default="default")` |
| **Check existence** | `"key" in job.variables` | `task.get_variable("key") is not None` |
| **Set local variable** | Not directly supported | Return in completion dict |

## Logging

| Operation | Camunda8 (pyzeebe) | CIB7 |
|-----------|-------------------|------|
| **Process instance ID** | `job.processInstanceKey` | `task.get_process_instance_id()` |
| **Activity ID** | `job.elementId` | `task.get_activity_id()` |
| **Task ID** | `job.key` | `task.get_task_id()` |

**Recommended log format:**
```python
logger.info(
    "Processing task",
    extra={
        "process_instance_id": task.get_process_instance_id(),
        "activity_id": task.get_activity_id(),
        "task_id": task.get_task_id(),
        "tenant_id": task.get_tenant_id()
    }
)
```

## Multi-Tenancy

| Feature | Camunda8 (Zeebe) | CIB7 |
|---------|------------------|------|
| **Support** | Not available (Camunda Cloud regions) | ✅ Native tenant markers |
| **Subscribe with tenant** | N/A | `worker.subscribe("topic", handler, tenant_id="hospital-austa")` |
| **Get tenant ID** | N/A | `task.get_tenant_id()` |

## Configuration

| Setting | Camunda8 (pyzeebe) | CIB7 |
|---------|-------------------|------|
| **Base URL** | `hostname` + `port` (gRPC) | `base_url` (HTTP REST) |
| **Max concurrent tasks** | `maxJobsToActivate` | `config={"maxTasks": 10}` |
| **Lock duration** | `timeout_ms` | `config={"lockDuration": 300000}` |
| **Request timeout** | Default 30s | `config={"asyncResponseTimeout": 30000}` |
| **Retry backoff** | Zeebe controls | `config={"retries": 3, "retryTimeout": 5000}` |

## Worker Lifecycle

| Operation | Camunda8 (pyzeebe) | CIB7 |
|-----------|-------------------|------|
| **Start worker** | `client.run()` (blocking) | `worker.start()` (non-blocking) |
| **Stop worker** | Ctrl+C or exception | `worker.stop()` |
| **Graceful shutdown** | Handle SIGTERM | `signal.signal(signal.SIGTERM, lambda: worker.stop())` |

## Performance Tuning

| Parameter | Camunda8 | CIB7 | Notes |
|-----------|----------|------|-------|
| **Fetch latency** | ~20-50ms (gRPC) | ~100-200ms (REST long-poll) | CIB7 slightly higher, acceptable for healthcare |
| **Connection pooling** | Automatic (gRPC) | Configure via `urllib3` or `requests` | Recommended: 10-20 connections |
| **Batch fetch** | `maxJobsToActivate` | `maxTasks` | Set based on worker capacity |
| **Lock duration** | `timeout_ms` | `lockDuration` | 5 min recommended (300000ms) |

## Migration Examples

### Example 1: Simple Worker

**Camunda8:**
```python
from pyzeebe import ZeebeClient

client = ZeebeClient(hostname="zeebe", port=26500)

@client.job(task_type="notify-patient")
def notify_patient(job):
    patient_id = job.variables.get("patientId")
    message = job.variables.get("message")
    
    send_notification(patient_id, message)
    
    return {"notificationSent": True}

client.run()
```

**CIB7:**
```python
from camunda.external_task.external_task_worker import ExternalTaskWorker

worker = ExternalTaskWorker(
    worker_id="notification-worker",
    base_url="http://cibseven:8080/engine-rest",
    config={"maxTasks": 5, "lockDuration": 60000}
)

def notify_patient(task):
    patient_id = task.get_variable("patientId")
    message = task.get_variable("message")
    
    send_notification(patient_id, message)
    
    return {"notificationSent": True}

worker.subscribe("notify-patient", notify_patient, tenant_id="hospital-austa")
worker.start()
```

### Example 2: Worker with Error Handling

**Camunda8:**
```python
@client.job(task_type="validate-eligibility")
def validate_eligibility(job):
    try:
        patient_id = job.variables.get("patientId")
        result = check_eligibility(patient_id)
        return {"eligible": result.eligible, "plan": result.plan}
    except NetworkError as e:
        job.set_failure(message=str(e), retries=3)
    except EligibilityError as e:
        job.throw_error(error_code="NOT_ELIGIBLE", error_message=str(e))
```

**CIB7:**
```python
def validate_eligibility(task):
    try:
        patient_id = task.get_variable("patientId")
        result = check_eligibility(patient_id)
        return {"eligible": result.eligible, "plan": result.plan}
    except NetworkError as e:
        return task.failure(
            error_message=str(e),
            retries=3,
            retry_timeout=5000
        )
    except EligibilityError as e:
        return task.bpmn_error(
            error_code="NOT_ELIGIBLE",
            error_message=str(e)
        )

worker.subscribe("validate-eligibility", validate_eligibility, tenant_id="hospital-austa")
```

## Testing

### Mock Camunda8 Client

```python
from unittest.mock import Mock

mock_job = Mock()
mock_job.variables = {"patientId": "123"}
mock_job.key = "task-key"
mock_job.processInstanceKey = "proc-123"

result = handler(mock_job)
```

### Mock CIB7 Task

```python
from unittest.mock import Mock

mock_task = Mock()
mock_task.get_variable = Mock(side_effect=lambda k, default=None: {"patientId": "123"}.get(k, default))
mock_task.get_task_id = Mock(return_value="task-123")
mock_task.get_process_instance_id = Mock(return_value="proc-123")

result = handler(mock_task)
```

---

**Next Steps:**
1. Review this mapping when migrating each worker
2. Update imports and client initialization first
3. Convert task handlers one by one
4. Test each converted worker thoroughly

**Reference:** [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md) for detailed steps.
