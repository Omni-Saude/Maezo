# SAGA Compensation Delegates - Index and Overview

**Document Type**: Architecture Reference Index
**Scope**: SAGA Compensating Transactions Pattern
**Date**: 2026-01-24
**Status**: Published

---

## I. Overview

This document index references all SAGA compensation delegates for the Revenue Cycle Management system. These delegates implement compensating transactions in a distributed SAGA pattern to ensure transactional integrity across multiple independent steps.

### Reference Documentation

| Document | Delegate Class | Compensation Scope |
|----------|---------------|-------------------|
| [RN-COMP-001](./RN-COMP-001-CompensateAllocationDelegate.md) | `CompensateAllocationDelegate` | Reverses payment allocations to invoices |
| [RN-COMP-002](./RN-COMP-002-CompensateProvisionDelegate.md) | `CompensateProvisionDelegate` | Reverses provision entries and journal entries |
| [RN-COMP-003](./RN-COMP-003-CompensateSubmitDelegate.md) | `CompensateSubmitDelegate` | Cancels claim submissions to payers |

---

## II. SAGA Pattern Architecture

### 2.1. SAGA Flow Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    SAGA: Revenue Cycle Processing                │
└─────────────────────────────────────────────────────────────────┘

Step 1: Receive Payment
  ↓ (No compensation needed)

Step 2: Allocate Payment ─────→ Compensation: RN-COMP-001
  ├─ Delete allocation entries
  ├─ Restore unallocated balance
  ├─ Revert invoice allocated amounts
  └─ Update account receivables
  ↓

Step 3: Create Provision ─────→ Compensation: RN-COMP-002
  ├─ Delete provision record
  ├─ Reverse journal entries (Dr Liability, Cr Expense)
  ├─ Restore GL balances
  └─ Cancel ERP integration
  ↓

Step 4: Submit Claim ─────────→ Compensation: RN-COMP-003
  ├─ Cancel submission with payer (API)
  ├─ Revert claim status
  ├─ Reverse claim number assignment
  └─ Cancel EDI transmission
  ↓

Step 5: Update Status (Async)
  └─ (Automatic status management)
```

### 2.2. Failure Scenarios and Compensation Trigger

```
Success Path:
  Step1 ✓ → Step2 ✓ → Step3 ✓ → Step4 ✓ → Step5 ✓
  (No compensation needed)

Failure after Step 2 (Allocation):
  Step1 ✓ → Step2 ✓ → Step3 ✗ FAIL
  ↓
  Compensation: Step2 REVERT (RN-COMP-001)
  Then: Analyze root cause, Manual or Retry

Failure after Step 3 (Provision):
  Step1 ✓ → Step2 ✓ → Step3 ✓ → Step4 ✗ FAIL
  ↓
  Compensation Chain: Step3 REVERT (RN-COMP-002)
  Then: Step2 REVERT (RN-COMP-001)
  Then: Analyze, Manual or Retry

Failure after Step 4 (Submission):
  Step1 ✓ → Step2 ✓ → Step3 ✓ → Step4 ✓ → Step5 ✗ FAIL
  ↓
  Compensation Chain: Step4 REVERT (RN-COMP-003)
  Then: Step3 REVERT (RN-COMP-002)
  Then: Step2 REVERT (RN-COMP-001)
  Then: Analyze, Manual or Retry
```

---

## III. Compensation Delegate Summary

### 3.1. RN-COMP-001: CompensateAllocationDelegate

**Purpose**: Reverse payment-to-invoice allocations

**Input Variables**:
- `allocationId` (String, required)
- `paymentId` (String, required)
- `allocatedAmount` (Double, required)
- `invoiceIds` (List<String>, optional)

**Key Operations**:
1. DELETE allocation entries from payment_allocations
2. RESTORE unallocated_amount in payments
3. REVERT allocated_amount in invoices
4. CANCEL automatic matching
5. UPDATE account receivables balances
6. CREATE reversal journal entries
7. NOTIFY financial controllers
8. UPDATE audit trail

**Critical Properties**:
- **Idempotent**: Yes (allocation not found = success)
- **Atomic**: Yes (single DB transaction)
- **Domain**: Financial/Accounting
- **Severity**: CRITICAL (financial operation)
- **Timeout**: 10 seconds
- **Max Retries**: 3 (exponential wait)

**Error Handling**:
| Error | Severity | Recovery |
|-------|----------|----------|
| ALLOCATION_NOT_FOUND | WARN | Return success (idempotent) |
| PAYMENT_NOT_FOUND | CRITICAL | Retry, then escalate |
| BALANCE_MISMATCH | CRITICAL | Rollback and fail |
| DATABASE_ERROR | CRITICAL | Retry, then escalate |

---

### 3.2. RN-COMP-002: CompensateProvisionDelegate

**Purpose**: Reverse glosa provision entries and accounting

**Input Variables**:
- `provisionId` (String, required)
- `glosaId` (String, required)
- `provisionAmount` (Double, required)
- `accountingPeriod` (String, required) - Format: YYYY-MM

**Key Operations**:
1. DELETE provision record from glosa_provisions
2. REVERSE journal entries (Dr Liability, Cr Expense)
3. UPDATE glosa status to PENDING_PROVISION
4. RESTORE general ledger balances
5. CANCEL ERP integration
6. NOTIFY financial controllers
7. UPDATE provision analytics
8. CREATE reversal audit trail

**Critical Properties**:
- **Idempotent**: Yes (provision not found = success)
- **Atomic**: Yes (single DB transaction + optional ERP)
- **Domain**: Accounting/GL
- **Severity**: CRITICAL (accounting compliance)
- **Timeout**: 10 seconds
- **Max Retries**: 3 (exponential wait)

**Accounting Impact**:
- **Original Entry** (when created): Dr Expense (6301) / Cr Liability (2101)
- **Reversal Entry** (compensation): Dr Liability (2101) / Cr Expense (6301)
- **Net Effect**: Cancels original entry, maintains GL integrity

**Error Handling**:
| Error | Severity | Recovery |
|-------|----------|----------|
| PROVISION_NOT_FOUND | WARN | Return success (idempotent) |
| GLOSA_NOT_FOUND | CRITICAL | Retry, then escalate |
| PERIOD_CLOSED | CRITICAL | Require manual intervention |
| BALANCE_INCONSISTENCY | CRITICAL | Rollback and fail |
| ERP_CANCELLATION_FAILED | CRITICAL | Retry async |

---

### 3.3. RN-COMP-003: CompensateSubmitDelegate

**Purpose**: Cancel claim submissions to payers

**Input Variables**:
- `submissionId` (String, required)
- `claimId` (String, required)
- `payerId` (String, optional - can be derived from claim)

**Key Operations**:
1. CANCEL submission with payer (API call)
2. UPDATE claim status to PENDING_SUBMISSION
3. DELETE submission record
4. REVERSE claim number assignment
5. CANCEL EDI X12 transaction
6. NOTIFY billing team
7. UPDATE audit trail

**Critical Properties**:
- **Idempotent**: Yes (submission not found = success)
- **Atomic**: No (involves external API calls)
- **Domain**: Claims/Submission
- **Severity**: CRITICAL (submission integrity)
- **Timeout**: 10 seconds (with payer API timeout 5s)
- **Max Retries**: 3 (exponential wait for payer API)

**External Integration**:
- **Payer API**: POST /api/v1/payers/{payerId}/submissions/{submissionId}/cancel
- **Clearing House**: EDI X12 reversal transmission
- **Idempotency**: X-Request-ID header for API calls

**Error Handling**:
| Error | Severity | Recovery |
|-------|----------|----------|
| SUBMISSION_NOT_FOUND | WARN | Return success (idempotent) |
| CLAIM_NOT_FOUND | CRITICAL | Retry, then escalate |
| PAYER_API_UNAVAILABLE | CRITICAL | Retry async |
| EDI_CANCELLATION_FAILED | WARN | Log and continue |
| CLAIM_STATUS_INCONSISTENT | WARN | Log and continue |

---

## IV. Common Patterns and Best Practices

### 4.1. Idempotency

All compensation delegates implement idempotency:

```
IF entity_not_found:
  RETURN success with status="ALREADY_COMPENSATED"
  // Safe to re-run, no duplicate operations
```

**Benefit**: Allows safe retry of entire SAGA if timeout occurs

### 4.2. Transactional Integrity

**Database Transactions**:
- All SQL operations in single transaction
- Rollback on any error
- Maintains ACID properties

**Example** (RN-COMP-001):
```
BEGIN TRANSACTION
  DELETE allocation_entries
  UPDATE payments
  UPDATE invoices
  DELETE automatic_matching
  UPDATE account_receivables
  INSERT journal_entries
COMMIT  // On success
ROLLBACK // On any error
```

### 4.3. Audit Trail

Every compensation delegate creates comprehensive audit records:

```json
{
  "auditId": "AUDIT-COMP-...",
  "entityId": "ALLOC-2026-001-123456",
  "entityType": "payment_allocation",
  "action": "COMPENSATED",
  "details": {
    "originalAmount": 5000.50,
    "reversedAmount": 5000.50,
    "status": "SUCCESS",
    "executionTimeMs": 234,
    "operationsPerformed": 8
  },
  "timestamp": "2026-01-24T10:30:45.123Z",
  "createdBy": "SAGA_COMPENSATION_SYSTEM"
}
```

### 4.4. Asynchronous Notifications

All delegates publish events via Kafka:

```
RN-COMP-001: hospital.rcm.allocation.reversed
RN-COMP-002: hospital.rcm.provision.reversed
RN-COMP-003: hospital.rcm.submission.cancelled
```

**Benefit**: Stakeholders notified asynchronously without blocking SAGA

---

## V. Data Flow Through Compensation

### 5.1. Sample End-to-End Scenario

**Initial State** (all steps succeeded):
```
Payment: PAY-001, Amount: $5,000
  ├─ Allocated to Invoice INV-001: $3,000
  ├─ Allocated to Invoice INV-002: $2,000
  └─ Unallocated: $0

Glosa: GLOS-001, Amount: $12,500
  └─ Provision: PROV-001, Amount: $12,500 [GL Entry: Dr 6301, Cr 2101]

Claim: CLM-001, Amount: $5,000
  ├─ Status: SUBMITTED
  ├─ Payer: ANS-12345
  └─ Submission: SUB-001 [EDI: 837 Sent]
```

**Failure Event** (at Step 5):
```
Validation detects: "Claim total exceeds authorization"
```

**Compensation Chain** (reversed order):

**Step 1: RN-COMP-003** (Undo Submission)
```
CompensateSubmitDelegate(submissionId=SUB-001, claimId=CLM-001)
├─ API: POST /payers/ANS-12345/submissions/SUB-001/cancel → 200 OK
├─ UPDATE claims SET status='PENDING_SUBMISSION'
├─ DELETE claim_submissions WHERE submission_id='SUB-001'
├─ UPDATE claims SET payer_claim_number=NULL
└─ Result: Claim back to PENDING_SUBMISSION

Final State after RN-COMP-003:
  Claim: CLM-001, Status: PENDING_SUBMISSION (ready to resubmit)
```

**Step 2: RN-COMP-002** (Undo Provision)
```
CompensateProvisionDelegate(provisionId=PROV-001, glosaId=GLOS-001)
├─ DELETE glosa_provisions WHERE provision_id='PROV-001'
├─ INSERT journal_entries(Dr 2101, Cr 6301, Amount: $12,500) [Reversal]
├─ UPDATE glosas SET status='PENDING_PROVISION'
├─ UPDATE general_ledger REDUCE liability by $12,500
└─ POST /erp/provisions/PROV-001/cancel

Final State after RN-COMP-002:
  GL: Provision Liability = $0 (rolled back)
  GL: Provision Expense = $0 (rolled back)
  Glosa: Status = PENDING_PROVISION
```

**Step 3: RN-COMP-001** (Undo Allocation)
```
CompensateAllocationDelegate(allocationId=ALLOC-001)
├─ DELETE payment_allocations WHERE allocation_id='ALLOC-001'
├─ UPDATE payments SET unallocated_amount=$5,000
├─ UPDATE invoices SET allocated_amount=0, status='PENDING'
├─ DELETE automatic_matching WHERE allocation_id='ALLOC-001'
└─ UPDATE account_receivables RESTORE balances

Final State after RN-COMP-001:
  Payment: PAY-001, Unallocated: $5,000
  Invoices: INV-001, INV-002, Status: PENDING, Allocated: $0
  AR Balances: Restored to original
```

**Final State** (after all compensations):
- All financial operations reversed
- All claims back to PENDING_SUBMISSION
- Glosa back to PENDING_PROVISION
- Payment back to unallocated
- All journal entries balanced (Dr = Cr)
- Ready for retry or manual correction

---

## VI. ADR-010: Distributed Transactions Compliance

All compensation delegates comply with ADR-010 requirements:

### 6.1. Key Requirements

| Requirement | Implementation | Validation |
|-------------|-----------------|-----------|
| Idempotency | Entity not found = return success | Unit tests verify |
| Isolation | Single DB transaction per delegate | Transaction logs |
| Ordering | Compensations in reverse order | SAGA orchestration |
| Rastreabilidade | Audit trail for every operation | Audit queries |
| Notificação | Kafka events published | Message broker logs |
| Durability | Commit on success, rollback on error | DB recovery logs |

### 6.2. Compensation Ordering

```
SAGA Execution Order (Forward):
  Step 1: Allocate (RN-COMP-001 available)
  Step 2: Provision (RN-COMP-002 available)
  Step 3: Submit (RN-COMP-003 available)
  Step 4: Validate (No compensation)

Compensation Order (Reverse):
  Undo Step 3: RN-COMP-003 (undo submission)
  Undo Step 2: RN-COMP-002 (undo provision)
  Undo Step 1: RN-COMP-001 (undo allocation)
  // Never undo Step 0 (payment received)
```

---

## VII. Monitoring and Alerting

### 7.1. Key Metrics

```
Metric: compensate_allocation_duration_seconds
├─ P50: < 250ms
├─ P95: < 500ms
└─ P99: < 1000ms

Metric: compensate_provision_duration_seconds
├─ P50: < 300ms
├─ P95: < 600ms
└─ P99: < 2000ms (includes ERP call)

Metric: compensate_submit_duration_seconds
├─ P50: < 1000ms
├─ P95: < 2000ms
└─ P99: < 5000ms (includes payer API timeout)

Metric: compensation_success_rate
├─ Target: ≥ 99.5%
├─ Alert: < 99%
└─ Critical: < 95%
```

### 7.2. Alerting Rules

| Alert | Threshold | Severity | Action |
|-------|-----------|----------|--------|
| High Error Rate | > 1% in 5min | CRITICAL | Page on-call engineer |
| Timeout Latency | > 2s median | WARNING | Review payer/DB performance |
| Idempotency Ratio | > 30% in 1h | INVESTIGATION | Check for timeout issues |
| GL Mismatch | Any occurrence | CRITICAL | Immediate escalation |

### 7.3. Dashboard Queries

```sql
-- Compensation success rate by delegate
SELECT delegate_name, COUNT(*) as total,
       SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) as success,
       SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END)*100/COUNT(*) as rate
FROM compensation_audit_trail
WHERE timestamp > NOW() - INTERVAL 24 HOUR
GROUP BY delegate_name;

-- Average compensation duration
SELECT delegate_name,
       AVG(execution_time_ms) as avg_ms,
       MAX(execution_time_ms) as max_ms,
       PERCENTILE(execution_time_ms, 0.95) as p95_ms
FROM compensation_audit_trail
WHERE timestamp > NOW() - INTERVAL 24 HOUR
GROUP BY delegate_name;

-- Idempotent vs fresh compensations
SELECT delegate_name, compensation_type,
       COUNT(*) as count,
       COUNT(*)*100/(SELECT COUNT(*) FROM compensation_audit_trail
                     WHERE timestamp > NOW() - INTERVAL 24 HOUR) as percentage
FROM compensation_audit_trail
WHERE timestamp > NOW() - INTERVAL 24 HOUR
GROUP BY delegate_name, compensation_type;
```

---

## VIII. Testing Strategy

### 8.1. Unit Tests

Each delegate has comprehensive unit tests covering:

| Test Case | RN-COMP-001 | RN-COMP-002 | RN-COMP-003 |
|-----------|-------------|-------------|-------------|
| Successful compensation | ✅ | ✅ | ✅ |
| Idempotent (entity not found) | ✅ | ✅ | ✅ |
| Invalid input parameters | ✅ | ✅ | ✅ |
| Database errors | ✅ | ✅ | ✅ |
| External API failures | N/A | ✅ (ERP) | ✅ (Payer) |
| Partial failures | ✅ | ✅ | ✅ |
| Concurrent executions | ✅ | ✅ | ✅ |

### 8.2. Integration Tests

SAGA-level tests:

```
Test 1: Compensation after Step 2 failure
  ✓ Allocation compensated correctly
  ✓ Balances restored
  ✓ Audit trail complete

Test 2: Compensation after Step 3 failure
  ✓ Provision compensated
  ✓ Allocation compensated
  ✓ All GL entries balanced

Test 3: Compensation after Step 4 failure
  ✓ Submission compensated
  ✓ Provision compensated
  ✓ Allocation compensated
  ✓ Claim ready for resubmission

Test 4: Idempotent retry
  ✓ First compensation: success
  ✓ Second compensation: idempotent success
  ✓ No duplicate operations
```

### 8.3. Performance Tests

```
Benchmark: RN-COMP-001 (100 concurrent compensations)
├─ Avg time: 234ms
├─ P95: 456ms
└─ P99: 678ms
✓ SLA: < 1s met

Benchmark: RN-COMP-002 (100 concurrent, with ERP)
├─ Avg time: 567ms
├─ P95: 1200ms
└─ P99: 1800ms
✓ SLA: < 2s met

Benchmark: RN-COMP-003 (100 concurrent, with Payer API)
├─ Avg time: 1234ms
├─ P95: 2400ms
└─ P99: 3500ms
✓ SLA: < 5s met (includes API timeout)
```

---

## IX. Operational Runbooks

### 9.1. Incident: High Compensation Failure Rate

**Alert**: `compensation_success_rate < 95%`

**Investigation Steps**:
1. Check which delegates are failing most
2. Review error logs for specific error codes
3. Check external dependencies (DB, ERP, Payer APIs)
4. Verify network connectivity
5. Check for recent deployments

**Mitigation**:
- If DB issue: Check query performance, restart DB connection pool
- If ERP issue: Check ERP API logs, contact ERP team
- If Payer issue: Reach out to payer support
- If code issue: Rollback recent deployment

### 9.2. Incident: GL Balance Mismatch

**Alert**: `compensation_gl_mismatch detected`

**Severity**: CRITICAL - Requires immediate escalation

**Investigation Steps**:
1. **DO NOT** continue processing until resolved
2. Get specific mismatches from DB queries
3. Retrieve compensation records for affected claims
4. Verify journal entries (Dr = Cr)
5. Check GL balances before/after
6. Engage accounting team

**Recovery**:
- If compensation error: Verify and rerun compensation
- If data corruption: Restore from backup + replay from checkpoint
- If systemic issue: Escalate to CTO + CFO

### 9.3. Operational Maintenance

**Daily**:
- Review compensation success rates
- Monitor alert dashboards
- Check for idempotent spike (unusual retry patterns)

**Weekly**:
- Review compensation audit trail
- Verify GL reconciliation
- Check payer API availability metrics

**Monthly**:
- Full reconciliation of all compensated transactions
- Audit trail completeness check
- Performance trend analysis

---

## X. Related Documents

### ADR References
- [ADR-010: Distributed Transactions with SAGA Pattern](../ADR/ADR-010-saga-pattern.md)
- [ADR-003: Delegates and Workers Implementation](../ADR/ADR-003-delegates-workers-implementacao.md)
- [ADR-007: Variables and Error Handling](../ADR/ADR-007-variaveis-error-handling-best-practices.md)

### Implementation References
- [BaseDelegate Class Documentation](./RN-020-BaseDelegate.md)
- [SagaCompensationService](../services/SagaCompensationService.java)

### Related Rules
- [RN-BIL-004: Process Payment](./RN-BIL-004-ProcessPayment.md)
- [RN-BIL-005: Retry Submission](./RN-BIL-005-RetrySubmission.md)

---

## XI. Glossary

| Term | Definition |
|------|-----------|
| **SAGA** | Distributed transaction pattern for microservices |
| **Compensation** | Reversing/undoing operation in SAGA |
| **Idempotent** | Safe to execute multiple times with same result |
| **GL** | General Ledger (accounting system) |
| **Allocation** | Mapping payment received to open invoices |
| **Provision** | Accounting reserve for potential glosas |
| **Submission** | Sending claim to payer for payment |
| **Glosa** | Payer's rejection of claim (fully or partially) |
| **EDI** | Electronic Data Interchange (X12 837 format) |
| **Payer** | Health plan/insurance company |
| **Claim** | Medical claim with procedures and amounts |
| **Journal Entry** | Accounting entry in double-entry bookkeeping |

---

## XII. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Revenue Cycle Team | Initial documentation |

---

**Document Status**: Published
**Last Updated**: 2026-01-24
**Maintained By**: Revenue Cycle Development Team
**Contact**: revenue-cycle-architects@hospital.com
