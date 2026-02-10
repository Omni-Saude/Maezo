# TASY Integration Gap Analysis

> Generated: 2026-02-10 | Cross-reference of 770 TASY endpoints vs codebase

## Overall Integration Maturity

```
Total TASY Endpoints:    770
Endpoints Mapped:         18  (2.3%)
Endpoints NOT Mapped:    752  (97.7%)
Workers with TASY:         7  / ~100+
Scoring APIs Used:       9/9  (100%)
```

---

## CRITICAL Gaps (Must Fix)

### GAP-01: Clinical Scoring Integration
- **Status**: RESOLVED (Wave 4 - 2026-02-10)
- **Solution**: All 9 scoring APIs integrated into 7 clinical workers via `TasyScoringAdapter` + `TasyApiClientProtocol` extension
- **TASY Endpoints**: 9 scoring APIs fully integrated
- **Workers Now Using**:
  - `vital_signs_monitoring_worker` → `early-warning-score`, `sentry-score`
  - `clinical_alerts_worker` → `sepsis-alert`, `sentry-smart-alert`
  - `adverse_event_detection_worker` → `sepsis-score`
  - `clinical_decision_support_worker` → `risk-of-death-score`
  - `clinical_assessment_worker` → `automated-acuity`
  - `discharge_planning_worker` → `risk-of-readmission-score`
  - `clinical_protocols_worker` → `vent-management`
- **Impact**: Patient safety enhanced with real-time clinical scoring for sepsis detection, deterioration alerting, and clinical decision support
- **Testing**: All adapters covered by unit and integration tests

### GAP-02: All 15 Scheduling Workers Are Stubbed
- **Severity**: CRITICAL (operational)
- **TASY Endpoints**: 122 scheduling endpoints, 0 used
- **Impact**: No real appointment management, fake availability, no state tracking
- **Key Issues**:
  - Only 2 of 53 scheduling states handled (4%)
  - Time-suggestions API (AI slot optimization) not used
  - Waiting-list management not implemented
  - 11 scheduling channels not tracked
  - Multi-establishment scheduling not supported
- **Action**: Create `TasySchedulingAdapter`, implement 53-state machine
- **Effort**: 3-4 weeks

### GAP-03: Revenue Cycle Workers Mocked/Disconnected
- **Severity**: CRITICAL (financial)
- **TASY Endpoints**: 181 billing/revenue endpoints, only 2 used (`get_billing_account`, `get_billing_items`)
- **Impact**: No real ERP sync, fake reconciliation data, billing errors
- **Key Missing**:
  - `export_to_erp_worker` returns mock `TASY-{uuid}` — no real sync
  - `reconcile_daily_worker` uses hardcoded amounts — no real payment data
  - Insurance authorization workflow (9 endpoints) not connected
  - Denial/appeal tracking not in TASY
  - Material pricing (Brasindice/SIMPRO, 36 combinations) not used
  - PIX payment integration (9 endpoints) missing
- **Action**: Extend `tasy_api_client.py` with billing/pricing/PIX methods
- **Effort**: 2-3 weeks

### GAP-04: Drug Interaction Checking Hardcoded
- **Severity**: CRITICAL (patient safety)
- **Current**: `medication_management_worker` has 8 hardcoded drug interactions
- **Available**: Micromedex integration via TASY (comprehensive pharmaceutical DB)
- **Impact**: Missed drug-drug interactions, adverse drug events
- **Action**: Integrate Micromedex endpoints via TASY telehealth APIs
- **Effort**: 1 week

---

## HIGH Gaps

### GAP-05: Multi-Establishment Parameter Missing Everywhere
- **Severity**: HIGH
- **TASY**: `establishment_id` appears in 35+ endpoints as required parameter
- **Codebase**: No worker passes establishment context
- **Impact**: Cannot support AUSTA+AMH hospital group (multi-facility)
- **Action**: Add establishment_id to TenantContext, propagate through all workers
- **Effort**: 1 week (cross-cutting)

### GAP-06: Regulatory Async Callbacks Not Implemented
- **Severity**: HIGH
- **TASY**: 16 write-only regulatory endpoints use Push+Callback pattern
- **Codebase**: `generate_regulatory_reports_worker` uses ANS client stub
- **Impact**: No APAC/CNES/CNS/SUS submission, no callback handling
- **Key Pattern**:
  ```
  Submit → POST /api/apacReport
  Success → POST /api/apacReport/success (TASY calls us back)
  Error   → POST /api/apacReport/error   (TASY calls us back)
  ```
- **Action**: Implement callback receiver endpoints, submission tracking
- **Effort**: 2 weeks

### GAP-07: ICCA Integration (Tele-ICU) Absent
- **Severity**: HIGH
- **TASY**: 29 ICCA endpoints (infusion pumps, clinical orders, lab/micro)
- **Codebase**: Zero ICCA integration
- **Impact**: No infusion pump data, manual medication admin tracking
- **Action**: Create `TasyICCAAdapter` for critical care integration
- **Effort**: 2 weeks

### GAP-08: Supply Chain Completely Missing
- **Severity**: HIGH
- **TASY**: 212 endpoints (93 materials + 56 purchases + 63 CME)
- **Codebase**: Zero supply chain integration, no workers for procurement/CME
- **Impact**: No automated procurement, no sterilization tracking
- **Action**: Phase 3+ deliverable (new bounded context)
- **Effort**: 4-6 weeks (new domain)

---

## MEDIUM Gaps

### GAP-09: CDC Fallback Poller Limited to 5 Tables
- **Severity**: MEDIUM
- **Current**: Polls ATENDIMENTO, CONTA_MEDICA, ITEM_CONTA, PRESCRICAO, SINAL_VITAL
- **Missing**: Regulatory tables, supply chain tables, scheduling tables
- **Action**: Extend poller with additional table configs

### GAP-10: No PIX Payment Reconciliation
- **Severity**: MEDIUM
- **TASY**: 9 PIX payment endpoints including async callbacks
- **Impact**: Cannot reconcile PIX payments (increasingly common in Brazil)
- **Action**: Add PIX endpoints to revenue cycle integration

### GAP-11: Convênios/Insurance Domain Underused
- **Severity**: MEDIUM
- **TASY**: 50 convênios/insurance endpoints (read-heavy)
- **Codebase**: Only `get_coverage` used
- **Impact**: Limited insurance validation capability

---

## Workers Needing TASY Integration (Currently Without)

### patient_access (12 workers need TASY)
| Worker | Priority | TASY Domain |
|--------|----------|-------------|
| `update_scheduling_system_worker` | P0 | Scheduling |
| `check_availability_worker` | P0 | Scheduling |
| `create_appointment_worker` | P0 | Scheduling |
| `handle_cancellation_worker` | P0 | Scheduling |
| `validate_appointment_rules_worker` | P1 | Scheduling |
| `assign_resources_worker` | P1 | Scheduling |
| `send_appointment_confirmation_worker` | P1 | Scheduling |
| `send_reminder_notification_worker` | P2 | Scheduling |
| `calculate_estimated_duration_worker` | P2 | Scheduling |
| `check_pre_authorization_worker` | P1 | Insurance Auth |
| `check_authorization_requirements_worker` | P1 | Insurance Auth |
| `validate_patient_data_worker` | P2 | Patient Master |

### clinical_operations (7 workers need TASY)
| Worker | Priority | TASY Domain |
|--------|----------|-------------|
| `vital_signs_monitoring_worker` | P0 | Clinical Scoring |
| `clinical_alerts_worker` | P0 | Clinical Scoring |
| `adverse_event_detection_worker` | P0 | Clinical Scoring |
| `clinical_decision_support_worker` | P0 | Clinical Scoring + Micromedex |
| `medication_management_worker` | P0 | Micromedex |
| `clinical_assessment_worker` | P1 | Clinical Scoring |
| `discharge_planning_worker` | P1 | Clinical Scoring |

### revenue_cycle (12 workers need TASY)
| Worker | Priority | TASY Domain |
|--------|----------|-------------|
| `export_to_erp_worker` | P0 | Billing Sync |
| `reconcile_daily_worker` | P0 | Payments/PIX |
| `calculate_charges_worker` | P0 | Pricing |
| `assign_prices_worker` | P0 | Brasindice/SIMPRO |
| `validate_claim_worker` | P1 | Billing Validation |
| `apply_contract_rules_worker` | P1 | Contracts |
| `generate_tiss_xml_worker` | P1 | Authorization |
| `submit_to_payer_worker` | P1 | Submission Tracking |
| `identify_glosa_worker` | P1 | Denial Tracking |
| `submit_appeal_worker` | P1 | Appeal Tracking |
| `suggest_tuss_worker` | P2 | Procedure Master |
| `capture_procedure_worker` | P2 | Billing Procedures |

### platform_services (4 workers need TASY)
| Worker | Priority | TASY Domain |
|--------|----------|-------------|
| `generate_regulatory_reports_worker` | P0 | Regulatory (APAC/CNES/CNS) |
| `optimize_resource_utilization_worker` | P1 | Materials/CME |
| `integrate_laboratory_worker` | P1 | ICCA Lab |
| `integrate_imaging_worker` | P2 | ICCA Imaging |

**Total: 35 workers need TASY integration**

---

## Key Questions Answered

| Question | Answer |
|----------|--------|
| Which of the 122 scheduling endpoints do we use? | **0** — all 15 scheduling workers are stubbed |
| Do we use sepsis-score, early-warning-score APIs? | **No** — 0/9 scoring APIs used |
| Are we handling the 53 scheduling states? | **No** — only 2 states (booked, cancelled) = 4% |
| Do we support multi-establishment param? | **No** — not passed in any worker |
| Are we implementing async callbacks for regulatory? | **No** — no callback handlers exist |

---

## Recommended Implementation Roadmap

### Phase 1: Patient Safety (Weeks 1-2)
- GAP-01: Clinical scoring integration (9 endpoints)
- GAP-04: Micromedex drug interaction integration
- New adapters: `TasyScoringAdapter`, `TasyMicromedexAdapter`

### Phase 2: Scheduling (Weeks 3-6)
- GAP-02: Full scheduling integration (122 endpoints)
- 53-state machine implementation
- Time-suggestions and waiting-list APIs
- New adapter: `TasySchedulingAdapter`

### Phase 3: Revenue Cycle (Weeks 5-8)
- GAP-03: Billing/pricing/payment integration
- GAP-10: PIX payment reconciliation
- Insurance authorization workflow
- Material pricing (Brasindice/SIMPRO)
- New adapters: `TasyBillingAdapter`, `TasyPricingAdapter`

### Phase 4: Cross-Cutting (Weeks 7-9)
- GAP-05: Multi-establishment parameter propagation
- GAP-06: Regulatory async callback handlers
- GAP-07: ICCA integration
- GAP-09: CDC poller extension

### Phase 5: Supply Chain (Weeks 10-15)
- GAP-08: New supply chain bounded context
- Materials, purchases, CME domains
- New workers and adapters

---

## Appendix: Endpoints per Domain

| # | Domain | Total Endpoints | Used | Gap | Coverage |
|---|--------|----------------|------|-----|----------|
| 1 | Scheduling | 122 | 0 | 122 | 0% |
| 2 | Materials & Stock | 93 | 0 | 93 | 0% |
| 3 | Billing & Invoicing | 77 | 2 | 75 | 2.6% |
| 4 | Telehealth & ICCA | 66 | 2 | 64 | 3.0% |
| 5 | Patient Management | 63 | 3 | 60 | 4.8% |
| 6 | CME (Sterilization) | 63 | 0 | 63 | 0% |
| 7 | Purchases | 56 | 0 | 56 | 0% |
| 8 | Convênios & Insurance | 50 | 1 | 49 | 2.0% |
| 9 | Legal Entity | 40 | 0 | 40 | 0% |
| 10 | Clinical/EMR | 31 | 1 | 30 | 3.2% |
| 11 | Financial | 29 | 0 | 29 | 0% |
| 12 | Material Pricing | 18 | 0 | 18 | 0% |
| 13 | Regulatory/SUS | 16 | 0 | 16 | 0% |
| 14 | Medical Management | 16 | 0 | 16 | 0% |
| 15 | Ophthalmology | 15 | 0 | 15 | 0% |
| 16 | Pharmacy | 11 | 0 | 11 | 0% |
| | **TOTAL** | **770** | **9** | **761** | **1.2%** |
