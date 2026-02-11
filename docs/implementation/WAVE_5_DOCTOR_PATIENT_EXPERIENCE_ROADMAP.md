# Wave 5: Doctor & Patient Experience Enhancement Roadmap

**Status:** 📋 Prepared  
**Created:** 2026-02-10  
**Estimated Duration:** 5-7 days (swarm-accelerated)  
**Dependencies:** Wave 3.6 (Surgical) patterns, WhatsApp infrastructure

---

## Executive Summary

Wave 5 extends the **proactive communication** and **self-service** principles successfully implemented for surgeons (Wave 3.6) to **ALL doctors and patients** across the platform's 5 patient journeys.

### Key Metrics

| Metric | Value |
|--------|-------|
| **New Workers** | 31 (16 patient + 15 doctor) |
| **New BPMN Processes** | 4 subprocesses |
| **New DMN Tables** | 4 decision tables |
| **Patient Journeys Covered** | 5/5 (100%) |
| **Communication Channels** | WhatsApp, SMS fallback |
| **Memory Entries Indexed** | 12 (scope + patterns + references) |

---

## Memory System Preparation ✅

Following ADR-013 (Claude-flow Swarm Intelligence), we've prepared the memory system for optimal swarm agent performance:

### Indexed Memory Keys (healthcare-platform namespace)

| Key | Purpose | Size |
|-----|---------|------|
| `wave-5-scope` | Overall wave objectives | 476 bytes |
| `wave-5.1-scope` | Emergency Journey phase | 762 bytes |
| `wave-5.2-scope` | Inpatient Experience phase | 920 bytes |
| `wave-5.3-scope` | Post-Discharge Continuity phase | 1000 bytes |
| `wave-5.4-scope` | Financial Self-Service phase | 837 bytes |
| `wave-5.5-scope` | Relationship/Fidelity phase | 862 bytes |
| `wave-5-bpmn-scope` | BPMN processes to create | 898 bytes |
| `wave-5-dmn-scope` | DMN tables to create | 920 bytes |
| `domain-5-journeys` | 5 patient journeys context | 673 bytes |
| `domain-doctor-touchpoints` | Doctor communication touchpoints | 635 bytes |
| `domain-patient-touchpoints` | Patient communication touchpoints | 690 bytes |
| `reference-notification-workers` | Existing worker templates | 601 bytes |
| `reference-whatsapp-client` | WhatsApp client documentation | 588 bytes |

### Indexed Pattern Keys (patterns namespace)

| Key | Purpose |
|-----|---------|
| `pattern-whatsapp-notification-worker` | WhatsApp notification worker template |
| `pattern-interactive-selfservice` | Self-service interactive buttons pattern |

### Vector Search Verification

```bash
# Test semantic search (verified working)
npx @claude-flow/cli@latest memory search \
  --query "doctor patient notification whatsapp" \
  --namespace healthcare-platform --top-k 5
# Results: 0.84, 0.80, 0.80 relevance scores ✅
```

---

## Phase Breakdown

### Phase 5.0: BPMN & DMN Foundation (Pre-requisite)
**Duration:** 1 day  
**Swarm Workers:** 4

Create the foundational BPMN and DMN before workers.

#### Deliverables

| Artifact | Path | Description |
|----------|------|-------------|
| SP-PA-010 BPMN | `patient_access/bpmn/SP-PA-010_Doctor_Daily_Engagement.bpmn` | Doctor daily engagement orchestration |
| SP-PA-011 BPMN | `clinical_operations/bpmn/SP-PA-011_Patient_Inpatient_Experience.bpmn` | Inpatient patient experience |
| SP-PA-012 BPMN | `clinical_operations/bpmn/SP-PA-012_Post_Discharge_Followup.bpmn` | Post-discharge continuity |
| SP-RF-003 BPMN | `revenue_cycle/bpmn/SP-RF-003_Patient_Financial_SelfService.bpmn` | Financial self-service |

| DMN Table | Path | Description |
|-----------|------|-------------|
| notification_timing_rules.dmn | `platform_services/dmn/communication/` | When to send notifications |
| channel_preference_rules.dmn | `platform_services/dmn/communication/` | Channel selection (WhatsApp/SMS/Email) |
| selfservice_eligibility_rules.dmn | `platform_services/dmn/communication/` | Self-service vs staff actions |
| notification_frequency_rules.dmn | `platform_services/dmn/communication/` | Prevent over-communication |

---

### Phase 5.1: Emergency Journey Notifications
**Duration:** 0.5 day  
**Workers:** 5 (3 doctor + 2 patient)

#### Doctor Workers

| Worker | CIB7 Topic | Description |
|--------|------------|-------------|
| `doctor_triage_escalation_worker.py` | `emergency.triage_escalation` | Notify physician of escalated triage |
| `doctor_specialist_consult_worker.py` | `emergency.specialist_consult` | Request specialist via WhatsApp |
| `doctor_patient_arrival_worker.py` | `scheduling.patient_arrival` | Patient arrived for appointment |

#### Patient Workers

| Worker | CIB7 Topic | Description |
|--------|------------|-------------|
| `patient_emergency_wait_update_worker.py` | `emergency.wait_update` | Emergency wait time updates |
| `patient_triage_status_worker.py` | `emergency.triage_status` | Triage classification notification |

#### Output Paths
- Doctor: `healthcare_platform/clinical_operations/workers/`
- Patient: `healthcare_platform/patient_access/workers/`

---

### Phase 5.2: Inpatient Experience
**Duration:** 1 day  
**Workers:** 8 (4 doctor + 4 patient)

#### Doctor Workers

| Worker | CIB7 Topic | Description |
|--------|------------|-------------|
| `doctor_rounds_summary_worker.py` | `inpatient.rounds_summary` | Daily rounds summary at 6AM |
| `doctor_critical_value_worker.py` | `clinical.critical_value` | **URGENT** critical lab values |
| `doctor_discharge_readiness_worker.py` | `inpatient.discharge_ready` | Patient ready for discharge review |
| `doctor_bed_availability_worker.py` | `inpatient.bed_available` | Bed available for pending admission |

#### Patient Workers

| Worker | CIB7 Topic | Description | Interactive |
|--------|------------|-------------|-------------|
| `patient_daily_care_plan_worker.py` | `inpatient.daily_plan` | Morning care plan update | ❌ |
| `patient_medication_reminder_worker.py` | `inpatient.medication_reminder` | Medication reminder | ✅ Confirm taken |
| `patient_meal_preference_worker.py` | `inpatient.meal_choice` | Meal selection | ✅ Option A/B/C |
| `patient_care_team_intro_worker.py` | `inpatient.care_team_intro` | Care team introduction | ❌ |

---

### Phase 5.3: Post-Discharge Continuity
**Duration:** 1 day  
**Workers:** 8 (4 doctor + 4 patient)

#### Doctor Workers

| Worker | CIB7 Topic | Description |
|--------|------------|-------------|
| `doctor_patient_recovery_alert_worker.py` | `continuity.recovery_alert` | Patient reports worsening |
| `doctor_followup_completion_worker.py` | `continuity.followup_pending` | Pending follow-up scheduling |
| `doctor_referral_status_worker.py` | `continuity.referral_status` | Referral approval/denial |
| `doctor_readmission_risk_worker.py` | `continuity.readmission_risk` | High readmission risk alert |

#### Patient Workers

| Worker | CIB7 Topic | Description | Interactive |
|--------|------------|-------------|-------------|
| `patient_followup_reminder_worker.py` | `continuity.followup_reminder` | Follow-up scheduling | ✅ Confirm/Reschedule |
| `patient_recovery_checkin_worker.py` | `continuity.recovery_checkin` | Recovery status check | ✅ Better/Same/Worse |
| `patient_medication_adherence_worker.py` | `continuity.medication_adherence` | Medication adherence | ✅ Yes/No/Need help |
| `patient_test_results_worker.py` | `continuity.results_available` | Test results available | ✅ View now |

---

### Phase 5.4: Financial Self-Service
**Duration:** 0.5 day  
**Workers:** 6 (4 patient + 2 doctor)

#### Patient Workers

| Worker | CIB7 Topic | Description | Interactive |
|--------|------------|-------------|-------------|
| `patient_copay_estimate_worker.py` | `financial.copay_estimate` | Pre-visit copay estimate | ✅ Pay Now/Pay Later |
| `patient_bill_notification_worker.py` | `financial.bill_ready` | Bill ready notification | ✅ View/Pay/Question |
| `patient_payment_confirmation_worker.py` | `financial.payment_confirmed` | Payment confirmation + PDF | ❌ (sends receipt) |
| `patient_authorization_update_worker.py` | `financial.auth_update` | Authorization status | ❌ |

#### Doctor Workers

| Worker | CIB7 Topic | Description |
|--------|------------|-------------|
| `doctor_procedure_auth_status_worker.py` | `financial.auth_pending` | Pending authorizations summary |
| `doctor_reimbursement_summary_worker.py` | `financial.reimbursement_summary` | Monthly billing summary |

---

### Phase 5.5: Relationship & Fidelity
**Duration:** 0.5 day  
**Workers:** 7 (4 patient + 3 doctor)

#### Patient Workers (Fidelization)

| Worker | CIB7 Topic | Description | Interactive |
|--------|------------|-------------|-------------|
| `patient_birthday_worker.py` | `relationship.birthday` | Birthday wishes + wellness tip | ❌ |
| `patient_health_anniversary_worker.py` | `relationship.anniversary` | Health milestone celebration | ✅ Share feedback |
| `patient_preventive_reminder_worker.py` | `relationship.preventive` | Annual checkup reminder | ✅ Schedule now |
| `patient_satisfaction_survey_worker.py` | `relationship.survey` | Post-visit NPS survey | ✅ 1-5 stars |

#### Doctor Workers (Engagement)

| Worker | CIB7 Topic | Description |
|--------|------------|-------------|
| `doctor_performance_summary_worker.py` | `relationship.doctor_performance` | Weekly performance metrics |
| `doctor_patient_feedback_worker.py` | `relationship.patient_feedback` | Patient compliments/feedback |
| `doctor_cme_reminder_worker.py` | `relationship.cme_reminder` | CME credits expiration |

---

## Swarm Commands

### Phase 5.0: BPMN & DMN Foundation

```bash
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 4 \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --namespace healthcare-platform \
  --use-memory \
  --use-patterns \
  --objective "
**PHASE 5.0: BPMN & DMN FOUNDATION**

MEMORY CONTEXT:
Retrieve keys: wave-5-bpmn-scope, wave-5-dmn-scope, domain-5-journeys, pattern-surgical-bpmn

WORKER ASSIGNMENTS:
- Worker 1: Create SP-PA-010_Doctor_Daily_Engagement.bpmn
- Worker 2: Create SP-PA-011_Patient_Inpatient_Experience.bpmn + SP-PA-012_Post_Discharge_Followup.bpmn
- Worker 3: Create SP-RF-003_Patient_Financial_SelfService.bpmn
- Worker 4: Create 4 DMN tables in platform_services/dmn/communication/

ARCHITECTURE REQUIREMENTS:
- CIB Seven 2.1.3 external task pattern
- Multi-tenant with tenant markers (ADR-002)
- Error boundary events for BPMN errors
- Timer events for scheduled notifications

DMN REQUIREMENTS:
- Hit policy: FIRST for timing rules, COLLECT for frequency
- Input/output variables as per wave-5-dmn-scope memory
- Tenant override support (ADR-007)

OUTPUT PATHS:
- BPMN: healthcare_platform/{domain}/bpmn/
- DMN: healthcare_platform/platform_services/dmn/communication/

VALIDATION:
xmllint --noout *.bpmn
Test DMN with sample inputs

ESTIMATED TIME: 2-3 hours
"
```

### Phase 5.1: Emergency Journey

```bash
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 5 \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --namespace healthcare-platform \
  --use-memory \
  --use-patterns \
  --objective "
**PHASE 5.1: EMERGENCY JOURNEY NOTIFICATIONS**

MEMORY CONTEXT:
Retrieve keys: wave-5.1-scope, pattern-whatsapp-notification-worker, pattern-interactive-selfservice, reference-whatsapp-client

WORKER ASSIGNMENTS:
- Worker 1: doctor_triage_escalation_worker.py
- Worker 2: doctor_specialist_consult_worker.py
- Worker 3: doctor_patient_arrival_worker.py
- Worker 4: patient_emergency_wait_update_worker.py
- Worker 5: patient_triage_status_worker.py

TEMPLATE: Use send_reminder_notification_worker.py as pattern

ARCHITECTURE REQUIREMENTS:
- WhatsAppClientProtocol for messaging
- LGPD: NEVER log phone numbers or message content
- Multi-tenant (ADR-002)
- CIB7 external task pattern (ADR-003)
- I18n with pt_BR translations
- Prometheus metrics (@track_task_execution)

WORKER STRUCTURE:
1. Input/Output Pydantic models
2. WhatsAppClientProtocol protocol
3. Worker class with execute() method
4. StubClient for testing

OUTPUT PATHS:
- Doctor workers: healthcare_platform/clinical_operations/workers/
- Patient workers: healthcare_platform/patient_access/workers/
- Tests: tests/unit/{domain}/workers/

VALIDATION:
python -m py_compile *.py
pytest tests/unit/ -k 'emergency or triage'

ESTIMATED TIME: 1-2 hours
"
```

### Phase 5.2: Inpatient Experience

```bash
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 8 \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --namespace healthcare-platform \
  --use-memory \
  --use-patterns \
  --objective "
**PHASE 5.2: INPATIENT EXPERIENCE**

MEMORY CONTEXT:
Retrieve keys: wave-5.2-scope, pattern-whatsapp-notification-worker, pattern-interactive-selfservice, reference-notification-workers

WORKER ASSIGNMENTS:
- Worker 1: doctor_rounds_summary_worker.py
- Worker 2: doctor_critical_value_worker.py (URGENT priority)
- Worker 3: doctor_discharge_readiness_worker.py
- Worker 4: doctor_bed_availability_worker.py
- Worker 5: patient_daily_care_plan_worker.py
- Worker 6: patient_medication_reminder_worker.py (interactive: confirm taken)
- Worker 7: patient_meal_preference_worker.py (interactive: option A/B/C)
- Worker 8: patient_care_team_intro_worker.py

CRITICAL VALUE WORKER SPECIAL:
- HIGHEST urgency, bypass frequency limits
- Include lab value in message
- Require acknowledgment

INTERACTIVE PATTERNS:
- Medication: [Taken ✓] [Remind in 30min] [Need help]
- Meals: [Option A] [Option B] [Option C]
- Use button payload: action_entityId format

OUTPUT PATHS:
- Doctor workers: healthcare_platform/clinical_operations/workers/
- Patient workers: healthcare_platform/clinical_operations/workers/ (inpatient)
- Tests: tests/unit/clinical_operations/workers/

ESTIMATED TIME: 2-3 hours
"
```

### Phase 5.3: Post-Discharge Continuity

```bash
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 8 \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --namespace healthcare-platform \
  --use-memory \
  --use-patterns \
  --objective "
**PHASE 5.3: POST-DISCHARGE CONTINUITY**

MEMORY CONTEXT:
Retrieve keys: wave-5.3-scope, pattern-whatsapp-notification-worker, pattern-interactive-selfservice, domain-patient-touchpoints

WORKER ASSIGNMENTS:
- Worker 1: doctor_patient_recovery_alert_worker.py
- Worker 2: doctor_followup_completion_worker.py
- Worker 3: doctor_referral_status_worker.py
- Worker 4: doctor_readmission_risk_worker.py
- Worker 5: patient_followup_reminder_worker.py (interactive)
- Worker 6: patient_recovery_checkin_worker.py (interactive: Better/Same/Worse)
- Worker 7: patient_medication_adherence_worker.py (interactive)
- Worker 8: patient_test_results_worker.py (interactive: View now)

RECOVERY CHECKIN FLOW:
- If 'Worse' selected → trigger doctor_patient_recovery_alert_worker
- Store response in process variable recoveryStatus
- Schedule follow-up call if needed

READMISSION RISK INTEGRATION:
- Use clinical_decision_support for risk scoring
- Alert if score > threshold (tenant-configurable via DMN)

OUTPUT PATHS:
- Workers: healthcare_platform/clinical_operations/workers/
- Tests: tests/unit/clinical_operations/workers/

ESTIMATED TIME: 2-3 hours
"
```

### Phase 5.4: Financial Self-Service

```bash
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 6 \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --namespace healthcare-platform \
  --use-memory \
  --use-patterns \
  --objective "
**PHASE 5.4: FINANCIAL SELF-SERVICE**

MEMORY CONTEXT:
Retrieve keys: wave-5.4-scope, pattern-whatsapp-notification-worker, reference-whatsapp-client, pattern-interactive-selfservice

WORKER ASSIGNMENTS:
- Worker 1: patient_copay_estimate_worker.py (interactive: Pay Now/Pay Later)
- Worker 2: patient_bill_notification_worker.py (interactive: View/Pay/Question)
- Worker 3: patient_payment_confirmation_worker.py (sends receipt PDF)
- Worker 4: patient_authorization_update_worker.py
- Worker 5: doctor_procedure_auth_status_worker.py
- Worker 6: doctor_reimbursement_summary_worker.py

PAYMENT CONFIRMATION SPECIAL:
- Use send_document() for PDF receipt
- Include payment_id, amount, date in caption
- LGPD: receipt PDF should be encrypted/password protected

BILL NOTIFICATION BUTTONS:
- [View Bill] → deep link to patient portal
- [Pay Now] → deep link to payment page
- [Question] → trigger support workflow

OUTPUT PATHS:
- Patient workers: healthcare_platform/revenue_cycle/workers/
- Doctor workers: healthcare_platform/revenue_cycle/workers/
- Tests: tests/unit/revenue_cycle/workers/

ESTIMATED TIME: 1-2 hours
"
```

### Phase 5.5: Relationship & Fidelity

```bash
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 7 \
  --topology hierarchical-mesh \
  --consensus byzantine \
  --claude \
  --model-routing intelligent \
  --namespace healthcare-platform \
  --use-memory \
  --use-patterns \
  --objective "
**PHASE 5.5: RELATIONSHIP & FIDELITY**

MEMORY CONTEXT:
Retrieve keys: wave-5.5-scope, surgeon-fidelity-analysis, pattern-whatsapp-notification-worker, domain-patient-touchpoints

WORKER ASSIGNMENTS:
- Worker 1: patient_birthday_worker.py
- Worker 2: patient_health_anniversary_worker.py (interactive: Share feedback)
- Worker 3: patient_preventive_reminder_worker.py (interactive: Schedule now)
- Worker 4: patient_satisfaction_survey_worker.py (NPS 1-5 stars)
- Worker 5: doctor_performance_summary_worker.py
- Worker 6: doctor_patient_feedback_worker.py
- Worker 7: doctor_cme_reminder_worker.py

BIRTHDAY WORKER:
- Personalized message with wellness tip
- Consider age and health conditions for tip selection
- Use template: birthday_greeting_v1

SATISFACTION SURVEY:
- NPS format: 1-5 stars
- If score ≤ 2 → trigger follow-up call
- If score ≥ 4 → trigger thank you + referral request

DOCTOR PERFORMANCE:
- Weekly aggregation: patients seen, satisfaction avg, outcomes
- Comparison to peer average (anonymized)
- Gamification: badges for achievements

OUTPUT PATHS:
- Patient workers: healthcare_platform/patient_access/workers/
- Doctor workers: healthcare_platform/clinical_operations/workers/
- Tests: tests/unit/{domain}/workers/

ESTIMATED TIME: 1-2 hours
"
```

---

## Post-Wave Validation

After all phases complete:

```bash
# 1. Count all new workers
find healthcare_platform -name "*worker.py" -newer docs/implementation/WAVE_5_* | wc -l
# Expected: 31+ new workers

# 2. Validate Python syntax
find healthcare_platform -name "*worker.py" -newer docs/implementation/WAVE_5_* -exec python -m py_compile {} \;

# 3. Run unit tests
pytest tests/unit/ -k "notification or reminder or patient_ or doctor_" -v

# 4. Validate BPMN
find healthcare_platform -name "SP-PA-01*.bpmn" -o -name "SP-RF-003*.bpmn" | xargs xmllint --noout

# 5. Store completion in memory
npx @claude-flow/cli@latest memory store \
  --key "wave-5-complete" \
  --namespace healthcare-platform \
  --value "Wave 5 Doctor/Patient Experience complete: 31 workers, 4 BPMN, 4 DMN. All phases validated."

# 6. Neural training on generated patterns
npx @claude-flow/cli@latest neural train \
  --modelType moe \
  --data-source "healthcare_platform/*/workers/*notification*" \
  --epochs 10 \
  --namespace healthcare-platform
```

---

## Success Criteria

| Criterion | Metric | Target |
|-----------|--------|--------|
| Workers Created | Count | 31 |
| BPMN Processes | Count | 4 |
| DMN Tables | Count | 4 |
| Python Syntax | py_compile | 100% pass |
| Unit Test Coverage | pytest | ≥ 80% |
| Interactive Workers | With buttons | 12 |
| LGPD Compliance | No PII in logs | 100% |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| WhatsApp template approval delay | Pre-register templates; use text fallback |
| Over-notification fatigue | notification_frequency_rules.dmn prevents flooding |
| Timezone issues | Store user timezone; use UTC internally |
| Language support | I18n with pt_BR; expandable to other locales |

---

## Related Documentation

- [ADR-013: Claude-flow Swarm Intelligence](../ADRs/013-claude-flow-swarm-intelligence.md)
- [ADR-003: Python External Task Workers](../ADRs/003-python-external-task-workers.md)
- [Technical Specification](../Technical%20specification/technical-specification.md)
- [WhatsApp Client](../../healthcare_platform/shared/integrations/whatsapp_client.py)
- [Wave 3.6 Surgical (reference)](./RC-GAP-3-implementation-summary.md)

---

**Next Steps:**
1. User reviews this roadmap
2. Execute Phase 5.0 swarm command (BPMN/DMN)
3. Sequential execution of Phases 5.1-5.5
4. Post-wave validation and memory update
