# Migration Guide: Camunda8 → CIB7

**Version:** 1.0  
**Date:** February 2026  
**Status:** Active  

## Overview

This guide provides step-by-step instructions for migrating Python External Task workers from Camunda8 (Zeebe/gRPC) to CIB7 (REST API).

## Prerequisites

- Python 3.11+
- Existing Camunda8 workers using `pyzeebe`
- CIB7 engine running and accessible via REST API
- `camunda-external-task-client-python3` v4.5.0 installed

## Migration Checklist

### 1. Dependencies (requirements.txt)

**Remove:**
```python
pyzeebe>=3.x.x
grpcio>=1.x.x
```

**Add:**
```python
camunda-external-task-client-python3==4.5.0
```

### 2. Client Initialization

**Camunda8 (Zeebe):**
```python
from pyzeebe import ZeebeClient

client = ZeebeClient(
    hostname="zeebe-gateway.example.com",
    port=26500,
    credentials=credentials
)
```

**CIB7:**
```python
from camunda.external_task.external_task_worker import ExternalTaskWorker

worker = ExternalTaskWorker(
    worker_id="revenue-cycle-worker",
    base_url="http://cibseven-engine:8080/engine-rest",
    config={
        "maxTasks": 10,
        "lockDuration": 300000,  # 5 minutes
        "asyncResponseTimeout": 30000,
        "retries": 3,
        "retryTimeout": 5000
    }
)
```

### 3. Task Handler Pattern

**Camunda8 (Zeebe):**
```python
@client.job(task_type="generate-tiss-xml")
def generate_tiss_xml(job):
    patient_id = job.variables.get("patientId")
    
    # Business logic here
    xml_content = generate_xml(patient_id)
    
    return {"tissXml": xml_content, "status": "success"}
```

**CIB7:**
```python
def generate_tiss_xml(task):
    patient_id = task.get_variable("patientId")
    
    # Business logic here (same as Camunda8)
    xml_content = generate_xml(patient_id)
    
    return {"tissXml": xml_content, "status": "success"}

worker.subscribe("generate-tiss-xml", generate_tiss_xml)
```

### 4. Error Handling

**Camunda8 (Zeebe):**
```python
@client.job(task_type="validate-authorization")
def validate_auth(job):
    try:
        result = validate(job.variables)
        return result
    except ValidationError as e:
        # Technical error - retry
        job.set_failure(message=str(e), retries=3)
    except BusinessError as e:
        # Business error - don't retry
        job.throw_error(error_code="AUTH_INVALID", error_message=str(e))
```

**CIB7:**
```python
def validate_auth(task):
    try:
        result = validate(task.variables)
        return result
    except ValidationError as e:
        # Technical error - retry
        return task.failure(
            error_message=str(e),
            error_details={"trace": traceback.format_exc()},
            retries=3,
            retry_timeout=5000
        )
    except BusinessError as e:
        # Business error - BPMN error
        return task.bpmn_error(
            error_code="AUTH_INVALID",
            error_message=str(e)
        )
```

### 5. Variable Access

**Camunda8:**
```python
patient_id = job.variables.get("patientId")
encounter_data = job.variables.get("encounterData", {})
```

**CIB7:**
```python
patient_id = task.get_variable("patientId")
encounter_data = task.get_variable("encounterData", default={})
```

### 6. Multi-Tenancy Support (NEW in CIB7)

**Add tenant markers to subscription:**
```python
worker.subscribe(
    topic="generate-tiss-xml",
    handler=generate_tiss_xml,
    tenant_id="hospital-austa"  # Per ADR-002
)
```

### 7. Worker Lifecycle

**Camunda8:**
```python
client.run()  # Blocking call
```

**CIB7:**
```python
worker.start()  # Non-blocking

# For graceful shutdown:
import signal
signal.signal(signal.SIGTERM, lambda s, f: worker.stop())
```

## Common Pitfalls

### ❌ Mistake 1: Not updating variable access
```python
# Wrong - Zeebe style
patient_id = task.variables.get("patientId")
```
```python
# Correct - CIB7 style
patient_id = task.get_variable("patientId")
```

### ❌ Mistake 2: Using Zeebe error codes
```python
# Wrong - Zeebe codes
job.throw_error(error_code="RESOURCE_EXHAUSTED")
```
```python
# Correct - BPMN error codes
task.bpmn_error(error_code="GLOSA_INVALID")
```

### ❌ Mistake 3: Forgetting tenant ID
```python
# Wrong - no tenant
worker.subscribe("topic", handler)
```
```python
# Correct - with tenant
worker.subscribe("topic", handler, tenant_id="hospital-austa")
```

## Testing Strategy

1. **Unit tests** - Business logic should be unchanged, so existing tests mostly work
2. **Integration tests** - Mock the CIB7 client, not Zeebe client
3. **End-to-end tests** - Deploy BPMN to CIB7 and test full flow

## Deployment Changes

**Camunda8:**
- Workers connect to Zeebe Gateway
- OAuth2 required for Camunda Cloud
- gRPC port 26500

**CIB7:**
- Workers connect to Engine REST API
- Authentication optional (configure per environment)
- HTTP port 8080 (default)
- Add `CAMUNDA_BPM_URL` environment variable

## Performance Considerations

| Aspect | Camunda8 | CIB7 | Impact |
|--------|----------|------|---------|
| Fetch latency | <50ms (gRPC) | 100-200ms (REST long-poll) | ⚠️ Slightly higher |
| Throughput | Very high | High | ✅ Acceptable for healthcare |
| Connection overhead | Low (persistent gRPC) | Medium (HTTP) | ⚠️ Use connection pooling |
| Scalability | Excellent | Excellent | ✅ Both scale horizontally |

**Mitigation:** Configure appropriate `maxTasks` and `asyncResponseTimeout` based on worker capacity.

## Migration Timeline

**Recommended approach:**
1. ✅ Set up CIB7 engine in dev environment
2. ✅ Migrate 1-2 simple workers first (e.g., notification sender)
3. ✅ Test thoroughly
4. ✅ Migrate complex workers (TISS generation, glosa analysis)
5. ✅ Update BPMN files if needed (<10% changes expected)
6. ✅ Deploy to staging
7. ✅ Parallel run with Camunda8 for validation
8. ✅ Production cutover

**Estimated effort per worker:** 2-4 hours for migration + testing

## Resources

- [CIB7 REST API Documentation](https://cibseven.com/docs)
- [camunda-external-task-client-python3 GitHub](https://github.com/camunda/camunda-external-task-client-python)
- ADR-001: CIB Seven as BPM Engine
- ADR-003: Python External Task Workers
- Technical Specification: Section 3.5 (Workers)

---

**Next:** Review [refactor-checklist.md](./refactor-checklist.md) for detailed per-worker tasks.
