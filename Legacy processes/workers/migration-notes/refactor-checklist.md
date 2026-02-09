# Refactor Checklist: Camunda8 → CIB7

**Purpose:** Per-worker checklist to track migration progress  
**Estimated effort:** 2-4 hours per worker  

## Worker Migration Template

Copy this section for each worker you migrate:

---

### Worker: [WORKER_NAME]
**File:** `[path/to/worker.py]`  
**Topic:** `[topic-name]`  
**Complexity:** ☐ Low ☐ Medium ☐ High  
**Business Logic Changes:** ☐ None ☐ Minor ☐ Significant  

#### Checklist

- [ ] **Dependencies updated** (pyzeebe → camunda-external-task-client-python3)
- [ ] **Client initialization refactored** (ZeebeClient → ExternalTaskWorker)
- [ ] **Task handler signature updated** (job → task parameter)
- [ ] **Variable access updated** (job.variables.get → task.get_variable)
- [ ] **Return pattern updated** (dict return → task.complete with variables)
- [ ] **Error handling updated** (job.set_failure → task.failure)
- [ ] **BPMN error codes mapped** (job.throw_error → task.bpmn_error)
- [ ] **Tenant ID added** to subscription (per ADR-002)
- [ ] **Logging updated** (include processInstanceId, activityId)
- [ ] **Unit tests updated** (mock CIB7 client instead of Zeebe)
- [ ] **Integration tests passing**
- [ ] **Code review completed**
- [ ] **Deployed to dev environment**
- [ ] **End-to-end testing completed**

#### Notes
<!-- Add any worker-specific notes, challenges, or decisions here -->

---

## Example: Completed Worker Migration

### Worker: TISS XML Generation ✅
**File:** `revenue-cycle/billing/worker_tiss_xml_generation.py`  
**Topic:** `generate-tiss-xml`  
**Complexity:** ☑ Medium  
**Business Logic Changes:** ☑ None (only client layer)  

#### Checklist

- [x] **Dependencies updated**
- [x] **Client initialization refactored**
- [x] **Task handler signature updated**
- [x] **Variable access updated**
- [x] **Return pattern updated**
- [x] **Error handling updated**
- [x] **BPMN error codes mapped**
- [x] **Tenant ID added** (hospital-austa)
- [x] **Logging updated**
- [x] **Unit tests updated**
- [x] **Integration tests passing**
- [x] **Code review completed**
- [x] **Deployed to dev environment**
- [x] **End-to-end testing completed**

#### Notes
- ANS 4.01 XML schema generation unchanged
- Added retry logic for SOAP endpoint timeout (new in CIB7)
- Performance: 850ms avg → 920ms avg (70ms overhead from REST acceptable)

---

## Revenue Cycle Workers

### Billing Domain

#### Worker: Generate TISS XML
- [ ] Complete checklist above
- **Specific considerations:**
  - ANS 4.01 schema generation (no changes needed)
  - SOAP endpoint integration
  - Large XML payloads (>5MB) - test timeout settings

#### Worker: Apply Contract Rules
- [ ] Complete checklist above
- **Specific considerations:**
  - DMN decision evaluation (ensure tenant-specific rules)
  - Contract version handling
  - Percentage calculations (precision maintained)

#### Worker: Submit Claim
- [ ] Complete checklist above
- **Specific considerations:**
  - Operator portal API integration
  - Retry logic for network failures
  - Claim number generation (idempotency)

### Coding Domain

#### Worker: Assign Codes
- [ ] Complete checklist above
- **Specific considerations:**
  - ML model inference (TensorFlow/PyTorch versions)
  - ICD-10, TUSS code lookups
  - Fallback to manual coding on low confidence

#### Worker: Audit Coding
- [ ] Complete checklist above
- **Specific considerations:**
  - Rule engine integration
  - Documentation completeness checks
  - Alert generation for coding team

### Glosa (Denials) Domain

#### Worker: Analyze Glosa
- [ ] Complete checklist above
- **Specific considerations:**
  - ML model for denial prediction
  - Historical data analysis
  - Confidence scoring

#### Worker: Apply Corrections
- [ ] Complete checklist above
- **Specific considerations:**
  - ERP write-back via CDC
  - Audit trail creation
  - Notification triggers

### Collection Domain

#### Worker: Allocate Payment
- [ ] Complete checklist above
- **Specific considerations:**
  - Bank reconciliation data
  - Payment matching algorithms
  - Partial payment handling

#### Worker: Process Reconciliation
- [ ] Complete checklist above
- **Specific considerations:**
  - Multi-operator payment splits
  - Accounting system integration
  - Period closing rules

## Clinical Workers

### Alerts Domain

#### Worker: Sepsis Detection
- [ ] Complete checklist above
- **Specific considerations:**
  - qSOFA/SOFA score calculations
  - Real-time FHIR observation monitoring
  - Alert urgency levels

#### Worker: Clinical Trigger
- [ ] Complete checklist above
- **Specific considerations:**
  - Rule-based alert generation
  - Physician notification routing
  - Escalation policies

### Documentation Domain

#### Worker: FHIR Sync
- [ ] Complete checklist above
- **Specific considerations:**
  - FHIR R4 resource mapping
  - HAPI FHIR server integration
  - Differential sync (only changed data)

## Shared Utilities

### Base Worker Class
- [ ] Complete checklist above
- **Specific considerations:**
  - Common error handling patterns
  - Logging configuration
  - Metrics/tracing setup

### Error Handlers
- [ ] Complete checklist above
- **Specific considerations:**
  - Error code mapping (Zeebe → BPMN)
  - Retry strategy configuration
  - Dead letter queue handling

## Testing Strategy

### Unit Tests
- [ ] Update mocks (ZeebeClient → ExternalTaskWorker)
- [ ] Test error handling paths
- [ ] Test tenant ID propagation
- [ ] Test variable transformations

### Integration Tests
- [ ] CIB7 engine running in test mode
- [ ] BPMN deployed to test engine
- [ ] Workers connect to test engine
- [ ] End-to-end process execution

### Performance Tests
- [ ] Measure latency impact (REST vs gRPC)
- [ ] Load test with 100+ concurrent tasks
- [ ] Memory profiling
- [ ] Connection pool optimization

## Deployment Checklist

### Infrastructure
- [ ] CIB7 engine deployed
- [ ] PostgreSQL database configured
- [ ] Kubernetes HPA configured for workers
- [ ] Environment variables set (CAMUNDA_BPM_URL, tenant IDs)

### Monitoring
- [ ] Prometheus metrics endpoint
- [ ] Grafana dashboards updated
- [ ] Elasticsearch log aggregation
- [ ] Alert rules configured

### Documentation
- [ ] Worker inventory updated
- [ ] Runbook updated
- [ ] Troubleshooting guide updated
- [ ] Team training completed

## Sign-off

**Migrated by:** ___________________  
**Reviewed by:** ___________________  
**Date:** ___________________  
**Production deployment date:** ___________________  

---

**Note:** Use this checklist as you migrate each worker. Track progress in project management tool.
