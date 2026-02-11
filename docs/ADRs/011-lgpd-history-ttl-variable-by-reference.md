# ADR-011: LGPD Compliance — History TTL + Variable-by-Reference

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, DPO, Legal

## Context

The Lei Geral de Proteção de Dados (LGPD) requires personal data be retained only as long as necessary, and that data subjects can request deletion. The CIB Seven History Service stores complete process execution history including all process variables, which may contain patient names, CPF numbers, clinical data, and insurance information.

If process variables contain personal data directly (e.g., `patientName = 'João Silva'`), LGPD deletion requests require purging from History Service, destroying audit trail integrity.

Additionally, ANS requires billing audit trails for 5+ years — tension between LGPD minimization and regulatory retention.

## Decision

Dual strategy: **Variable-by-Reference** and **History TTL**.

**Variable-by-Reference:**

Process variables **never** store personal data directly. They store references (IDs) to the FHIR server.

```
# ❌ WRONG
patientName = "João Silva"
patientCPF = "123.456.789-00"

# ✅ CORRECT
patientFhirId = "Patient/12345"
coverageFhirId = "Coverage/67890"
```

When a LGPD deletion request arrives, the FHIR Patient resource is anonymized/deleted. Process history retains only the opaque reference ID, which is no longer personally identifiable.

**History TTL:**

- **Default:** `historyTimeToLive = 180 days` for completed process instances
- **Revenue cycle processes:** custom `historyTimeToLive = 2190 days` (6 years) in BPMN definition — satisfies ANS requirements
- **Clinical alert processes:** `historyTimeToLive = 365 days`

**Additional controls:**

- Encryption at rest via PostgreSQL TDE
- All data in transit uses TLS 1.3
- `pgaudit` extension logs all data access queries

## Consequences

**Positive:**

- LGPD compliance without sacrificing audit trail integrity. History remains intact and auditable; personal data lives exclusively in FHIR server where data subject rights are managed.
- History database stays compact — IDs instead of full patient records reduces storage and improves query performance.

**Negative:**

- Workers must never store PII in process variables. Developer mistakes create compliance violations. *Mitigation:* `MaezoWorker` base framework includes variable validator rejecting known PII patterns (CPF regex, email regex) before completing a task. CI includes static analysis check.
- Resolving variables to actual data requires FHIR lookup, adding latency to Cockpit/Tasklist views. *Mitigation:* Redis caches frequent FHIR resources; Cockpit views show process status rather than patient details.
