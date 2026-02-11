# TASY API ↔ Worker Mapping Matrix

> Generated: 2026-02-10 | TASY TIE Engine v1.0 | 770 endpoints, 16 domains, 469 data models

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total TASY Endpoints** | 770 |
| **Endpoints Currently Used** | ~18 (via `tasy_api_client.py` + `TasyScoringAdapter`) |
| **Coverage** | **2.3%** |
| **Workers with TASY Integration** | 7 / ~100+ |
| **Scoring APIs Used** | 9 / 9 (100%) |
| **Scheduling Endpoints Used** | 0 / 122 |
| **Surgical Endpoints Used** | 0 / 122 |
| **Supply Chain Endpoints Used** | 0 / 212 |
| **Regulatory Endpoints Used** | 0 / 16 |

---

## 1. Current `tasy_api_client.py` Endpoints (9 methods)

| Method | TASY Endpoint | Used By |
|--------|---------------|---------|
| `get_patient` | `GET /api/v1/patients/{id}` | `update_patient_registry_worker` |
| `search_patients` | `GET /api/v1/patients` | `check_existing_patient_worker` |
| `get_encounter` | `GET /api/v1/encounters/{id}` | `sync_erp_data_worker` |
| `search_encounters` | `GET /api/v1/encounters` | `sync_erp_data_worker` |
| `get_billing_account` | `GET /api/v1/billing/accounts/{id}` | `capture_procedure_worker` |
| `get_billing_items` | `GET /api/v1/billing/accounts/{id}/items` | `capture_procedure_worker` |
| `get_prescription` | `GET /api/v1/prescriptions/{id}` | (via CDC, not direct) |
| `get_vital_signs` | `GET /api/v1/encounters/{id}/vitals` | (via CDC, not direct) |
| `get_coverage` | `GET /api/v1/patients/{id}/coverages` | `verify_insurance_coverage_worker` |

## 2. TASY Adapters (7 adapters, Tasy→FHIR)

| Adapter | TASY Table | FHIR Resource | Status |
|---------|-----------|---------------|--------|
| `patient_adapter.py` | PACIENTE | Patient R4 | Active |
| `encounter_adapter.py` | ATENDIMENTO | Encounter R4 | Active |
| `billing_adapter.py` | CONTA_MEDICA / ITEM_CONTA | Claim R4 | Active |
| `coverage_adapter.py` | CONVENIO_PACIENTE | Coverage R4 | Active |
| `prescription_adapter.py` | PRESCRICAO | MedicationRequest R4 | Active |
| `vital_signs_adapter.py` | SINAL_VITAL | Observation R4 | Active |
| `base_adapter.py` | — | Base class | — |

## 3. CDC Fallback Poller (`cdc_fallback_poller.py`)

Polls 5 TASY tables when Debezium is unavailable:

| Table | Priority | Poll Interval | Workers Fed |
|-------|----------|---------------|-------------|
| ATENDIMENTO | HIGH | 60-120s | `sync_erp_data_worker` |
| CONTA_MEDICA | HIGH | 60-120s | Revenue cycle workers |
| ITEM_CONTA | MEDIUM | 300s | Revenue cycle workers |
| PRESCRICAO | MEDIUM | 300s | Clinical workers |
| SINAL_VITAL | HIGH | 60-120s | `vital_signs_monitoring_worker` |

**Missing from CDC**: Regulatory tables, Supply chain tables, Scheduling tables.

---

## 4. Scheduling Domain (122 endpoints → 0 used)

### patient_access Workers

| Worker | TASY Integration | TASY Endpoints NEEDED |
|--------|-----------------|----------------------|
| `update_scheduling_system_worker` | **STUB** (StubSchedulingSystemUpdater) | `POST/PUT/DELETE /api/schedules`, confirm, cancel |
| `check_availability_worker` | **STUB** (StubAvailabilityChecker) | `GET /api/schedules/availability`, `GET /api/time-suggestions` |
| `create_appointment_worker` | **STUB** (StubAppointmentCreator) | `POST /api/schedules`, status transitions, participant linking |
| `handle_cancellation_worker` | **STUB** (StubCancellationHandler) | `PUT /api/schedules/{id}/cancel`, `POST /api/waiting-list` |
| `validate_appointment_rules_worker` | **STUB** (StubAppointmentRulesValidator) | `GET /api/schedules/rules`, conflict checking, working hours |
| `send_appointment_confirmation_worker` | **STUB** (StubConfirmationSender) | `POST /api/schedules/{id}/notifications` |
| `send_reminder_notification_worker` | **STUB** (StubReminderSender) | `POST /api/schedules/{id}/reminders` |
| `assign_resources_worker` | **STUB** (StubResourceAssigner) | `GET /api/schedules/resources/availability`, conflict detection |
| `calculate_estimated_duration_worker` | **STUB** (StubDurationCalculator) | `GET /api/schedules/duration-estimate` |
| `verify_insurance_coverage_worker` | Has TasyApiClient (coverage only) | `GET /api/insurance-authorization/eligibility` |
| `check_pre_authorization_worker` | **STUB** (StubPreAuthChecker) | `POST /api/insurance-authorization`, status check |
| `check_authorization_requirements_worker` | **STUB** (StubAuthRequirementChecker) | `GET /api/insurance-authorization/ans-rules` |
| `validate_patient_data_worker` | No TASY | `GET /api/v1/patients` (validation) |
| `check_existing_patient_worker` | No TASY | `GET /api/v1/patients?cpf=` |
| `update_patient_registry_worker` | Has TasyApiClient ref | `PUT /api/v1/patients/{id}` |

### Scheduling State Machine Coverage

**We handle**: 2 states (`booked`=SCHEDULED, `cancelled`=CANCELLED) — **4% coverage**

**53 TASY states NOT handled** (critical ones):
- PRESCHEDULE, PRESCHEDULE_CONFIRMED, CONFIRMED, WAITING
- IN_ANAMNESIS, AWAITING_CONSULTATION, IN_CONSULTATION, SERVICED, FINISHED
- RESCHEDULED, JUSTIFIED_ABSENCE, NOT_JUSTIFIED_ABSENCE, ADMIT_AS_PRIORITY
- PENDING_AUTHORIZATION, AUTHORIZATION_APPROVED/DENIED
- CHECK_IN_COMPLETE, NO_SHOW, LATE_ARRIVAL, EARLY_ARRIVAL

---

## 5. Revenue Cycle Domain (181 endpoints → 2 used)

### revenue_cycle Workers

| Worker | TASY Integration | TASY Endpoints NEEDED |
|--------|-----------------|----------------------|
| `capture_procedure_worker` | CDC-based (`tasy_client.get_procedures`) | REST billing/procedure endpoints |
| `export_to_erp_worker` | **MOCK** (returns fake `TASY-{uuid}`) | `POST /api/v1/billing/sync`, payment posting |
| `calculate_charges_worker` | **None** (in-memory only) | Contract pricing, Brasindice/SIMPRO |
| `submit_to_payer_worker` | TISS client only | TASY submission tracking |
| `generate_tiss_xml_worker` | TISS client only | TASY authorization validation |
| `validate_claim_worker` | **None** | TASY business rule validation |
| `apply_contract_rules_worker` | **None** | Contract terms, procedure authorization |
| `identify_glosa_worker` | ClaimResponse only | `POST /api/v1/billing/denials` |
| `submit_appeal_worker` | TISS client only | `POST /api/v1/billing/appeals` |
| `suggest_tuss_worker` | ANS client only | TASY procedure master data |
| `reconcile_daily_worker` | **MOCK** (hardcoded amounts) | Payment data, PIX, receivables |
| `assign_prices_worker` | FHIR only | Brasindice, SIMPRO, material pricing (36 combinations) |

---

## 6. Clinical/Telehealth Domain (66 endpoints → 2 used)

### clinical_operations Workers

| Worker | TASY Integration | TASY Endpoints NEEDED |
|--------|-----------------|----------------------|
| `vital_signs_monitoring_worker` | TasyScoringAdapter | `early-warning-score`, `sentry-score` |
| `clinical_alerts_worker` | TasyScoringAdapter | `sepsis-alert`, `sentry-smart-alert` |
| `clinical_decision_support_worker` | TasyScoringAdapter | `risk-of-death-score`, Micromedex interaction checking |
| `adverse_event_detection_worker` | TasyScoringAdapter | `sepsis-score` |
| `clinical_assessment_worker` | TasyScoringAdapter | `automated-acuity` |
| `medication_management_worker` | **None** (8 hardcoded interactions) | Micromedex via TASY (comprehensive DB) |
| `discharge_planning_worker` | TasyScoringAdapter | `risk-of-readmission-score` |
| `clinical_protocols_worker` | TasyScoringAdapter | `vent-management` |
| `care_planning_worker` | TasyScoringAdapter | Clinical scoring APIs |
| `clinical_quality_indicators_worker` | TasyScoringAdapter | Scoring APIs for quality metrics |

### Scoring API Coverage: 9/9 (100%)

| Scoring Endpoint | Status | Worker That Uses It |
|-----------------|--------|--------------------------|
| `early-warning-score` (NEWS/MEWS) | **USED** | `vital_signs_monitoring_worker` |
| `sepsis-score` | **USED** | `adverse_event_detection_worker` |
| `sentry-score` | **USED** | `vital_signs_monitoring_worker` |
| `sentry-smart-alert` | **USED** | `clinical_alerts_worker` |
| `risk-of-death-score` (APACHE/SAPS) | **USED** | `clinical_decision_support_worker` |
| `risk-of-readmission-score` | **USED** | `discharge_planning_worker` |
| `automated-acuity` | **USED** | `clinical_assessment_worker` |
| `vent-management` | **USED** | `clinical_protocols_worker` |
| `sepsis-alert` | **USED** | `clinical_alerts_worker` |

---

## 7. Regulatory Domain (16 endpoints → 0 used)

| Worker | TASY Integration | TASY Endpoints NEEDED |
|--------|-----------------|----------------------|
| `generate_regulatory_reports_worker` | **STUB** (ANS client stub) | APAC, CNES, CNS, SUS/GERPAC |

### Async Callback Pattern (not implemented)

| Operation | Success Callback | Error Callback |
|-----------|-----------------|----------------|
| APAC Report | `POST /api/apacReport/success` | `POST /api/apacReport/error` |
| APAC Parameters | `POST /api/performAPACParam/success` | `POST /api/performAPACParam/error` |
| SUS GERPAC | `POST /api/sus/gerpac/.../success` | `POST /api/sus/gerpac/.../error` |
| Patient Reports | `POST /api/reportspatient/success` | `POST /api/reportspatient/error` |
| PIX Transmission | — | `POST /api/pix/transmission/{id}/error` |

---

## 8. Supply Chain Domain (212 endpoints → 0 used)

| Sub-domain | Endpoints | Used | Workers That Should Use Them |
|-----------|-----------|------|------------------------------|
| Materials & Stock | 93 | 0 | `optimize_resource_utilization_worker`, `sync_erp_data_worker` |
| Purchases | 56 | 0 | (no purchase workers exist) |
| CME (Sterilization) | 63 | 0 | (no CME workers exist) |
| Material Pricing | 18 | 0 | `assign_prices_worker`, `calculate_charges_worker` |

---

## 9. platform_services Workers

| Worker | TASY Integration | TASY Endpoints NEEDED |
|--------|-----------------|----------------------|
| `sync_erp_data_worker` | CDC-based (`TasyClientProtocol`) | Extended REST endpoints for all domains |
| `detect_data_quality_issues_worker` | References "tasy" as data source | Validation endpoints across domains |
| `reconcile_data_sources_worker` | References "tasy" as source | Cross-domain reconciliation |
| `optimize_resource_utilization_worker` | **STUB** | Materials, CME, equipment endpoints |
| `generate_regulatory_reports_worker` | **STUB** | APAC, CNES, CNS, SUS |
| `integrate_laboratory_worker` | No TASY | ICCA lab integration (29 endpoints) |
| `integrate_imaging_worker` | No TASY | ICCA imaging endpoints |
| `monitor_system_health_worker` | No TASY | TASY health/status endpoints |

---

## 10. Surgical Services Domain (122 endpoints → 0 used)

### surgical_services Workers (14 workers need TASY)

| Worker | TASY Integration | TASY Endpoints NEEDED |
|--------|-----------------|----------------------|
| `manage_operating_rooms_worker` | **STUB** | `GET/POST /api/v1/surgical/rooms/*` — room CRUD, availability, status |
| `schedule_surgery_worker` | **STUB** | `POST /api/v1/surgical/records`, `GET/PUT /api/v1/surgical/rooms/{id}/schedule` |
| `assign_surgical_team_worker` | **STUB** | `GET /api/v1/surgical/centers/{id}/staff`, `POST /api/v1/surgical/records/{id}/team` |
| `prepare_surgical_materials_worker` | **STUB** | `GET /api/v1/surgical/materials/preference-cards/{id}`, `POST /api/v1/surgical/materials/requests` |
| `surgical_safety_checklist_worker` | **STUB** | `GET/POST /api/v1/surgical/centers/{id}/checklist` |
| `monitor_room_turnover_worker` | **STUB** | `GET/POST /api/v1/surgical/rooms/{id}/turnover`, cleaning endpoints |
| `track_surgery_timeline_worker` | **STUB** | `GET/POST /api/v1/surgical/records/{id}/timeline` |
| `record_surgical_notes_worker` | **STUB** | `GET/POST /api/v1/surgical/records/{id}/notes` |
| `record_anesthesia_worker` | **STUB** | `GET/POST/PUT /api/v1/surgical/records/{id}/anesthesia` |
| `manage_surgical_consent_worker` | **STUB** | `GET/POST /api/v1/surgical/records/{id}/consent` |
| `detect_surgical_complications_worker` | **STUB** | `POST /api/v1/surgical/records/{id}/complications` |
| `track_surgical_outcomes_worker` | **STUB** | `GET/POST /api/v1/surgical/records/{id}/outcomes` |
| `manage_surgical_queue_worker` | **STUB** | `GET /api/v1/surgical/centers/{id}/queue`, priority endpoints |
| `surgical_analytics_worker` | **STUB** | `GET /api/v1/surgical/centers/{id}/metrics/*`, procedure statistics |

### Worker → TASY Endpoint Mapping

| Worker | Primary Endpoints | Secondary Endpoints |
|--------|------------------|-------------------|
| `manage_operating_rooms_worker` | rooms (27) | centers/rooms (1) |
| `schedule_surgery_worker` | rooms/schedule (3), records (4) | procedures/duration (2) |
| `assign_surgical_team_worker` | records/team (3) | centers/staff (3) |
| `prepare_surgical_materials_worker` | materials/* (19) | procedures/materials (3) |
| `surgical_safety_checklist_worker` | centers/checklist (2) | records/counts (2) |
| `monitor_room_turnover_worker` | rooms/turnover (2), rooms/cleaning (3) | rooms/status (2) |
| `track_surgery_timeline_worker` | records/timeline (2) | records/vitals (2) |
| `record_surgical_notes_worker` | records/notes (3) | records/images (2) |
| `record_anesthesia_worker` | records/anesthesia (3) | records/vitals (2) |
| `manage_surgical_consent_worker` | records/consent (2) | procedures/consent-template (1) |
| `detect_surgical_complications_worker` | records/complications (3) | records/outcomes (2) |
| `track_surgical_outcomes_worker` | records/outcomes (2), procedures/statistics (1) | records/summary (1) |
| `manage_surgical_queue_worker` | centers/queue (2) | centers/metrics/delays (1) |
| `surgical_analytics_worker` | centers/metrics (4) | rooms/utilization (1), procedures/statistics (1) |

### Surgical State Machine

**States**: REQUESTED → SCHEDULED → CONFIRMED → PRE_OP → IN_ROOM → ANESTHESIA → IN_PROGRESS → CLOSING → POST_OP → RECOVERY → COMPLETED

**Cancellation paths**: Any state before IN_PROGRESS → CANCELLED (with reason)

**Emergency override**: Any state → EMERGENCY_OVERRIDE (bypasses queue)

---

## 11. Cross-Cutting Gaps

| Gap | Affected Workers | Impact |
|-----|-----------------|--------|
| **Multi-establishment (`establishment_id`)** | ALL workers | Cannot support hospital groups (AUSTA+AMH) |
| **Scheduling channels (11 types)** | All patient_access workers | No channel analytics |
| **Async callbacks for regulatory** | `generate_regulatory_reports_worker` | No submission status tracking |
| **Soft delete (ACTIVE/INACTIVE flags)** | All workers reading TASY data | May return inactive records |
| **Idempotent PUT transitions (21 endpoints)** | All workers writing to TASY | Not using retry-safe operations |
