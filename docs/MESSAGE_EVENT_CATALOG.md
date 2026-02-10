# Message Event Catalog - Inter-Domain Choreography

## Overview

This catalog defines all BPMN 2.0 message and signal events used for inter-domain communication
in the CIB7 Healthcare Platform. Messages are used for point-to-point cross-process communication;
signals are reserved for broadcast within the same tenant.

## Design Principles

1. **Messages for cross-process**: All inter-domain communication uses BPMN message events
2. **Signals for broadcast**: Signals only for intra-tenant broadcast (e.g., Code Blue)
3. **Tenant isolation**: All correlation keys include `tenantId`
4. **No PII in payloads**: Only FHIR resource IDs, never patient names/SSN/DOB
5. **Single throw, multiple catch**: Each message has exactly 1 throw point and 1+ catch points

---

## Cross-Domain Messages

### MSG-001: PatientAdmitted

| Field | Value |
|-------|-------|
| **Message Name** | `msg_patient_admitted` |
| **Direction** | Patient Access → Revenue Cycle |
| **Trigger** | SP-PA-006 (Check-in Flow) completes successfully |
| **Source** | `patient-access-main` orchestrator (throw after `call_SP_PA_006`) |
| **Target** | `revenue-cycle-main` orchestrator (message start event) |
| **Correlation Keys** | `tenantId` + `patientFhirId` + `encounterFhirId` |
| **Payload** | `{ tenantId, patientFhirId, encounterFhirId, appointmentFhirId, serviceType, payerId }` |
| **Event Type** | Intermediate Throw → Message Start |
| **Notes** | Replaces/augments existing `msg_encounter_created`. Triggers full revenue cycle. |

### MSG-002: ProceduresCompleted

| Field | Value |
|-------|-------|
| **Message Name** | `msg_procedures_completed` |
| **Direction** | Clinical Operations → Revenue Cycle |
| **Trigger** | SP-CO-007 (Surgical Services) completes successfully |
| **Source** | `clinical-ops-main` orchestrator (throw after `call_SP_CO_007` merge) |
| **Target** | `revenue-cycle-main` orchestrator (non-interrupting boundary on `call_SP_RC_004`) |
| **Correlation Keys** | `tenantId` + `encounterFhirId` + `procedureFhirId` |
| **Payload** | `{ tenantId, encounterFhirId, procedureFhirId, surgicalOutcome, carePlanFhirId }` |
| **Event Type** | Intermediate Throw → Non-Interrupting Boundary Catch |
| **Notes** | Notifies Revenue Cycle of completed procedures for clinical production capture. |

### MSG-003: SepsisAlert

| Field | Value |
|-------|-------|
| **Message Name** | `msg_sepsis_alert` |
| **Direction** | Clinical Alerts → Clinical Operations |
| **Trigger** | SP-CA-001 (Sepsis Detection) confirms sepsis with escalation |
| **Source** | `clinical-alerts-main` orchestrator (throw when escalation required) |
| **Target** | `clinical-ops-main` orchestrator (interrupting boundary on `call_SP_CO_003`) |
| **Correlation Keys** | `tenantId` + `patientFhirId` + `alertId` |
| **Payload** | `{ tenantId, patientFhirId, encounterFhirId, alertId, qsofaScore, alertScore }` |
| **Event Type** | Intermediate Throw → Interrupting Boundary Catch |
| **Notes** | CRITICAL alert. Uses interrupting boundary to immediately activate sepsis protocol. |

### MSG-004: AuthorizationDenied

| Field | Value |
|-------|-------|
| **Message Name** | `msg_authorization_denied` |
| **Direction** | Revenue Cycle → Patient Access |
| **Trigger** | SP-RC-002 (Pre-Service) authorization denied |
| **Source** | `revenue-cycle-main` orchestrator (throw on denial path from `gateway_billing_approved`) |
| **Target** | `patient-access-main` orchestrator (non-interrupting boundary on `call_SP_PA_002`) |
| **Correlation Keys** | `tenantId` + `authorizationId` + `encounterFhirId` |
| **Payload** | `{ tenantId, authorizationId, encounterFhirId, patientFhirId, denialReason, payerId }` |
| **Event Type** | Intermediate Throw → Non-Interrupting Boundary Catch |
| **Notes** | Triggers rescheduling workflow in Patient Access. Non-interrupting so scheduling can continue for other patients. |

### MSG-005: GlosaDetected

| Field | Value |
|-------|-------|
| **Message Name** | `msg_glosa_detected` |
| **Direction** | Revenue Cycle → Revenue Cycle (intra-domain) |
| **Trigger** | SP-RC-008 (Revenue Collection) detects payment variance |
| **Source** | `revenue-cycle-main` orchestrator (throw from collection payment variance path) |
| **Target** | `revenue-cycle-main` orchestrator (starts SP-RC-007 via event sub-process) |
| **Correlation Keys** | `tenantId` + `claimFhirId` + `payerId` |
| **Payload** | `{ tenantId, claimFhirId, payerId, encounterFhirId, varianceAmount, varianceType }` |
| **Event Type** | Intermediate Throw → Event Sub-Process Message Start |
| **Notes** | Intra-domain message for payment variance detection. Triggers denial management. |

---

## Existing Messages (Phase 1.1)

### MSG-100: PatientContact

| Field | Value |
|-------|-------|
| **Message Name** | `msg_patient_contact` |
| **Direction** | External → Patient Access |
| **Source** | External systems (CDC bridge, portal, call center) |
| **Target** | `patient-access-main` (message start event) |
| **Correlation Keys** | `tenantId` + `demandChannel` |

### MSG-101: PatientReadyForCare

| Field | Value |
|-------|-------|
| **Message Name** | `msg_patient_ready_for_care` |
| **Direction** | Patient Access → Clinical Operations |
| **Source** | `patient-access-main` (intermediate throw after SP-PA-006) |
| **Target** | `clinical-ops-main` (message start event) |
| **Correlation Keys** | `tenantId` + `encounterFhirId` |

### MSG-102: EncounterCreated

| Field | Value |
|-------|-------|
| **Message Name** | `msg_encounter_created` |
| **Direction** | Patient Access → Revenue Cycle |
| **Source** | `patient-access-main` (intermediate throw after SP-PA-006) |
| **Target** | `revenue-cycle-main` (message start event) |
| **Correlation Keys** | `tenantId` + `encounterFhirId` |

### MSG-103: ClinicalDocumentationReady

| Field | Value |
|-------|-------|
| **Message Name** | `msg_clinical_documentation_ready` |
| **Direction** | Clinical Operations → Revenue Cycle |
| **Source** | `clinical-ops-main` (intermediate throw after surgical merge) |
| **Target** | `revenue-cycle-main` (intermediate catch before SP-RC-003) |
| **Correlation Keys** | `tenantId` + `encounterFhirId` |

### MSG-104: DischargeCompleted

| Field | Value |
|-------|-------|
| **Message Name** | `msg_discharge_completed` |
| **Direction** | Clinical Operations → Revenue Cycle |
| **Source** | `clinical-ops-main` (intermediate throw after documentation) |
| **Target** | `revenue-cycle-main` (intermediate catch before SP-RC-004) |
| **Correlation Keys** | `tenantId` + `encounterFhirId` |

### MSG-105: ClearanceApproved

| Field | Value |
|-------|-------|
| **Message Name** | `msg_clearance_approved` |
| **Direction** | Internal Patient Access |
| **Source** | Financial clearance completion |
| **Target** | `patient-access-main` (intermediate catch before SP-PA-006) |
| **Correlation Keys** | `tenantId` + `patientFhirId` |

### MSG-106: PaymentReconciled

| Field | Value |
|-------|-------|
| **Message Name** | `msg_payment_reconciled` |
| **Direction** | Revenue Cycle → Analytics |
| **Source** | `revenue-cycle-main` (intermediate throw after SP-RC-008) |
| **Target** | External analytics systems |
| **Correlation Keys** | `tenantId` + `encounterFhirId` |

### MSG-107: VitalSignsReceived

| Field | Value |
|-------|-------|
| **Message Name** | `msg_vital_signs_received` |
| **Direction** | External → Clinical Alerts |
| **Source** | IoT/monitoring devices, EMR integration |
| **Target** | `clinical-alerts-main` (message start event) |
| **Correlation Keys** | `tenantId` + `patientFhirId` |

### MSG-108: ClinicalEscalation

| Field | Value |
|-------|-------|
| **Message Name** | `msg_clinical_escalation` |
| **Direction** | Clinical Alerts → Care Team |
| **Source** | `clinical-alerts-main` (intermediate throw on escalation) |
| **Target** | Care team notification systems |
| **Correlation Keys** | `tenantId` + `patientFhirId` + `encounterFhirId` |

### MSG-109: LabResultsReady

| Field | Value |
|-------|-------|
| **Message Name** | `msg_lab_results_ready` |
| **Direction** | External → Clinical Operations |
| **Source** | LIS integration |
| **Target** | `clinical-ops-main` (intermediate catch before SP-CO-005) |
| **Correlation Keys** | `tenantId` + `encounterFhirId` |

---

## Signals (Broadcast Within Tenant)

### SIG-001: CodeBlue

| Field | Value |
|-------|-------|
| **Signal Name** | `signal_code_blue` |
| **Scope** | Broadcast within same tenant |
| **Source** | `clinical-alerts-main` (signal throw when critical alert) |
| **Targets** | All active clinical processes for the tenant |
| **Notes** | Uses signal (not message) because it's a broadcast to all listeners. |

---

## Message Flow Summary

```
Patient Access          Clinical Operations       Clinical Alerts         Revenue Cycle
      |                        |                        |                      |
      |---PatientReadyForCare->|                        |                      |
      |---EncounterCreated-----|------------------------|--------------------->|
      |---PatientAdmitted------|------------------------|--------------------->|
      |                        |                        |                      |
      |                        |<------SepsisAlert------|                      |
      |                        |                        |                      |
      |                        |---ClinDocReady---------|--------------------->|
      |                        |---DischargeCompleted---|--------------------->|
      |                        |---ProceduresCompleted--|--------------------->|
      |                        |                        |                      |
      |<---AuthorizationDenied-|------------------------|----------------------|
      |                        |                        |                      |
      |                        |                        |      GlosaDetected-->|
      |                        |                        |      (RC internal)   |
```

---

## Validation Checklist

- [x] All messages have unique names (prefixed with `msg_`)
- [x] All correlation keys include `tenantId`
- [x] No PII in message payloads (only FHIR IDs)
- [x] Each message has exactly 1 throw and 1+ catch events
- [x] Cross-process communication uses messages (not signals)
- [x] Signals only for broadcast within same tenant
- [x] Interrupting boundary for critical alerts (SepsisAlert)
- [x] Non-interrupting boundary for notifications (AuthorizationDenied, ProceduresCompleted)
