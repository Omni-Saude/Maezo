# Clinical Delegates Documentation Suite

**Created:** 2026-01-24
**Status:** COMPLETE
**Analyst:** Research & Analysis Agent

## Overview

This directory contains comprehensive documentation for all clinical workflow delegates in the Revenue Cycle Management BPMN process. The documentation covers business rules, TASY ERP integration, LGPD compliance, and data handling requirements.

## Documents Included

### 1. Index and Integration Guide
**File:** `00-CLINICAL-DELEGATES-INDEX.md`
**Purpose:** Comprehensive index of all clinical delegates with cross-references and integration points
**Key Sections:**
- Summary of all three clinical delegates
- Clinical workflow sequence
- TASY ERP integration architecture
- HL7 message standards
- Data flow between delegates
- LGPD compliance framework overview
- Error handling and resilience
- Performance characteristics
- Testing strategy
- Monitoring and observability
- Troubleshooting guide

**Read This First:** For overview of clinical delegates and how they work together

### 2. LGPD Compliance Guide
**File:** `00-CLINICAL-LGPD-GUIDE.md`
**Purpose:** Detailed LGPD compliance framework for clinical data handling
**Key Sections:**
- Legal framework (LGPD, CFM, ANS, ANVISA)
- Patient rights (access, correction, deletion, portability, opposition)
- Data classification and sensitivity levels
- Legal bases for processing
- Data security requirements
- Patient rights implementation
- Data breach notification procedures
- Third-party data processor agreements
- International data transfer restrictions
- Compliance checklists
- DPO responsibilities
- Practical implementation examples
- Regulatory inspection preparation
- Compliance metrics and reporting

**Read This For:** Understanding LGPD obligations and implementing data protection measures

### 3. Clinical Delegates (Existing Documentation)

#### RN-CLIN-001: CloseEncounterDelegate
**File:** `RN-CLIN-001-CloseEncounter.md`
**Handles:** Encounter closure with comprehensive validation
**Business Rules:**
- Validation of complete documentation
- Discharge summary verification
- Prescription and follow-up confirmation
- TASY status update
- Document archival
- Billing workflow trigger
- Discharge notifications

**Key Output:** `ready_for_billing = true` (Critical trigger for billing process)

#### RN-CLIN-002: CollectTASYDataDelegate
**File:** `RN-CLIN-002-CollectTASYData.md`
**Handles:** Clinical data extraction from TASY EHR
**Business Rules:**
- Data scope handling (FULL, BASIC, BILLING_ONLY)
- Patient demographics collection
- Procedure collection (TUSS codes)
- Diagnosis collection (ICD-10 codes)
- Medication collection (conditional)
- Lab result collection (conditional)
- Data source tracking

**Key Output:** Complete clinical data set for downstream processes

#### RN-CLINICAL-007: RegisterEncounterDelegate
**File:** `RN-RegisterEncounterDelegate.md`
**Handles:** Encounter registration in TASY
**Business Rules:**
- Patient ID validation
- Service type validation
- Encounter creation in TASY ADT module
- Status initialization
- Optional demographic data capture
- TASY confirmation receipt
- Idempotency enforcement

**Key Output:** `encounterId` (Unique identifier for entire encounter lifecycle)

## Clinical Workflow Sequence

```
Patient Arrival
    ↓
1. RegisterEncounterDelegate
   └─> Create encounter, generate encounterId
    ↓
2. Clinical Evaluation (Medical Staff)
   └─> Procedures, diagnoses, medications, tests
    ↓
3. CollectTASYDataDelegate
   └─> Extract all clinical data from TASY
    ↓
4. Coding & Validation (Downstream)
   └─> Validate codes, verify documentation
    ↓
5. CloseEncounterDelegate
   └─> Validate completeness, update status, trigger billing
    ↓
Billing Process (SUB_04_Faturamento)
```

## Data Flow Between Delegates

```
RegisterEncounterDelegate
├─ Input: patientId, serviceType
├─ Output: encounterId (CRITICAL)
│
├─> CollectTASYDataDelegate
│   ├─ Input: encounterId, patientId
│   ├─ Output: clinicalData, procedures, diagnoses, medications, labResults
│   │
│   └─> CloseEncounterDelegate
│       ├─ Input: encounter_id (uses encounterId)
│       ├─ Output: ready_for_billing (CRITICAL TRIGGER)
│       │
│       └─> Billing Process
│
└─> All share: patientId (common identifier across process)
```

## TASY ERP Integration Points

**All three delegates integrate with TASY:**

- **RegisterEncounter:** `POST /tasy/encounters` - ADT module
- **CollectTASY:** `GET /tasy/patients/{id}`, `GET /tasy/encounters/{id}/procedures`, etc.
- **CloseEncounter:** `PUT /tasy/encounters/{id}/status` - ADT module

**HL7 Standards:**
- ADT-A01 (Admit Patient) - on register
- ADR messages (real-time updates) - during clinical phase

## LGPD Compliance Quick Reference

**Data Sensitivity:** CRITICAL (Healthcare data is most sensitive)

**Legal Bases:**
- Contractual execution (healthcare delivery)
- Legal obligations (CFM 7-year retention)
- Legitimate interest (billing, compliance)

**Patient Rights:**
- Access: Retrieve all data referenced in delegates
- Correction: Physician-authorized only
- Deletion: After 7-year retention period
- Portability: Export in HL7/FHIR formats

**Security Requirements:**
- HTTPS/TLS 1.2+ encryption
- Role-based access control
- Comprehensive audit logging
- Breach notification procedures

**Key Metric:** All delegates must track audit trail of data access

## Error Handling

### RegisterEncounter
- `INVALID_PATIENT_ID`: Patient ID missing/invalid
- `INVALID_SERVICE_TYPE`: Service type not supported
- `ENCOUNTER_REGISTRATION_FAILED`: TASY unavailable

### CollectTASY
- `INVALID_PATIENT_ID`: Patient ID missing/invalid
- `INVALID_ENCOUNTER_ID`: Encounter ID missing/invalid
- `TASY_DATA_COLLECTION_FAILED`: Data retrieval failure

### CloseEncounter
- `INCOMPLETE_DOCUMENTATION`: Required docs missing
- `INCOMPLETE_DISCHARGE_SUMMARY`: Discharge summary incomplete

**Retry Strategy:** Exponential backoff with 5 max attempts

## Performance Expectations

| Delegate | Avg Time | P95 | Timeout |
|----------|----------|-----|---------|
| RegisterEncounter | 1-2s | 4s | 15s |
| CollectTASY (FULL) | 2-3s | 7s | 20s |
| CloseEncounter | 2-4s | 7s | 30s |

## Testing Considerations

**Critical Test Scenarios:**
1. Complete successful workflow (happy path)
2. Missing patient ID
3. Invalid service type
4. TASY unavailable (error handling)
5. Incomplete documentation (blocking error)
6. Idempotency (duplicate registrations)
7. Data scope variations (FULL vs BASIC)

## Monitoring and Alerts

**Key Metrics to Monitor:**
- Execution time (% > P95)
- Error rate per delegate
- Timeout rate
- Retry rate
- TASY availability

**Critical Alerts:**
- Any `ready_for_billing` not set (blocks downstream)
- Data collection failures
- Documentation validation failures
- Encounter closure failures

## Compliance and Audit

**Documents to Maintain:**
- Audit logs (minimum 5 years)
- DPAs with TASY and processors
- Staff LGPD training records
- Incident response logs
- Patient rights request logs

**Inspection Readiness:**
- Data flow diagram showing all three delegates
- Security controls documentation
- Retention period tracking
- Patient rights procedures

## Related Processes

- **SUB_03_Atendimento_Clinico.bpmn:** Parent subprocess
- **SUB_04_Faturamento.bpmn:** Triggered by CloseEncounter
- **Coding Process:** Consumes CollectTASY output
- **Eligibility Verification:** Uses patient data from RegisterEncounter

## Troubleshooting Quick Links

1. **Issue:** Encounter not registering
   → See RN-RegisterEncounterDelegate.md section 5 (Error Handling)

2. **Issue:** Missing clinical data
   → See RN-CLIN-002-CollectTASYData.md section 8 (Scenarios)

3. **Issue:** Cannot close encounter
   → See RN-CLIN-001-CloseEncounter.md section 5 (Error Handling)

4. **Issue:** LGPD compliance question
   → See 00-CLINICAL-LGPD-GUIDE.md sections 3-8

5. **Issue:** Data breach detected
   → See 00-CLINICAL-LGPD-GUIDE.md section 6 (Breach Notification)

## Key Contacts

- **Data Protection Officer:** [DPO Contact]
- **Medical Director:** [Director Contact]
- **IT/Security Lead:** [IT Lead Contact]
- **Compliance Officer:** [Compliance Contact]

## Document Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-24 | Initial comprehensive clinical delegates documentation suite |

## File Organization

```
01_Delegates/
├─ 00-README-CLINICAL.md (this file)
├─ 00-CLINICAL-DELEGATES-INDEX.md (integration & overview)
├─ 00-CLINICAL-LGPD-GUIDE.md (LGPD & data protection)
├─ RN-CLIN-001-CloseEncounter.md (existing)
├─ RN-CLIN-002-CollectTASYData.md (existing)
├─ RN-RegisterEncounterDelegate.md (existing)
├─ RN-CloseEncounterDelegate.md (legacy - superseded by RN-CLIN-001)
└─ [other delegates...]
```

## Next Steps

1. **Review:** Team reviews all clinical delegate documentation
2. **Training:** Staff trained on LGPD requirements
3. **Audit:** Compliance audit of current implementation
4. **Updates:** Update clinical delegate code if gaps found
5. **Monitor:** Implement monitoring per section 13 of LGPD guide

---

**Last Updated:** 2026-01-24
**Status:** READY FOR USE
**Approved By:** Research & Analysis Agent
