# ADR-015: Worker Archetypes and DMN Delegation Patterns

**Status:** Accepted
**Date:** 2026-02-16
**Deciders:** Tech Lead, Platform Architect
**Amends:** ADR-003

## Context

With 283 workers across 4 domains, the team observed that workers fall into repeating structural patterns. Without formal archetypes, developers created ad-hoc implementations leading to inconsistent error handling, metrics, and DMN contracts. The V2 migration standardized the base class (`BaseExternalTaskWorker`) but did not prescribe which archetype a worker should follow.

## Decision

All workers must conform to one of four archetypes. Each archetype defines: DMN input contract, expected output, error handling strategy, and observability requirements.

### Archetype 1: CLINICAL_ALERT

**Purpose:** Evaluate clinical conditions and trigger alerts/escalations.
**DMN Input:** `{ patient_id, encounter_id, vital_signs{}, lab_results{} }`
**DMN Output:** `{ alert_level: "critical"|"warning"|"info", action: "PROSSEGUIR"|"BLOQUEAR"|"REVISAR" }`
**Error Handling:** On DMN failure → default to REVISAR (fail-safe, never suppress clinical alerts).
**Metrics:** `clinical_alert_evaluated_total`, `clinical_alert_triggered_total`
**Examples:** Sepsis scoring (qSOFA/SOFA), drug interaction checks, allergy alerts.

### Archetype 2: CLINICAL_SCORE

**Purpose:** Calculate clinical complexity or risk scores.
**DMN Input:** `{ encounter_id, diagnoses[], procedures[], patient_demographics{} }`
**DMN Output:** `{ score: float, level: str, factors: list[str] }`
**Error Handling:** On DMN failure → return score=0, level="unknown", log error.
**Metrics:** `clinical_score_calculated_total`, `clinical_score_distribution`
**Examples:** Charlson comorbidity, complexity calculation, fraud risk scoring.

### Archetype 3: ADMIN_ADJUDICATION

**Purpose:** Administrative decision-making (billing, coding, eligibility, denials).
**DMN Input:** `{ claim{}, payer_id, contract_id, codes[], amounts[] }`
**DMN Output:** `{ decision: "PROSSEGUIR"|"BLOQUEAR"|"REVISAR", reason_code: str, adjustments[] }`
**Error Handling:** On DMN failure → BLOQUEAR with reason "DMN_EVALUATION_FAILED".
**Metrics:** `admin_decision_total{decision}`, `admin_adjustment_amount`
**Examples:** Claim validation, contract rule application, glosa classification, pricing.
**Note:** This is the most common archetype (95 workers / 41% of total).

### Archetype 4: OPERATIONAL_ROUTING

**Purpose:** Route work items, assign resources, manage workflow transitions.
**DMN Input:** `{ item_type, priority, current_state, metadata{} }`
**DMN Output:** `{ next_state: str, assigned_to: str|null, action: "PROSSEGUIR"|"BLOQUEAR"|"REVISAR" }`
**Error Handling:** On DMN failure → maintain current state, escalate to supervisor.
**Metrics:** `routing_decision_total{next_state}`, `routing_latency_seconds`
**Examples:** Triage routing, appointment assignment, collection prioritization.

### Base Class Reference

All archetypes inherit from `BaseExternalTaskWorker` (healthcare_platform/shared/workers/base.py, 540 lines) which provides:
- Tenant resolution and multi-tenant context
- DMN evaluation via `FederatedDMNService`
- LGPD-compliant PII hashing
- Structured logging with process correlation IDs
- Prometheus metrics emission
- Error handling with BPMN error propagation

### DMN Evaluation Reference

All DMN calls go through `FederatedDMNService` (healthcare_platform/shared/dmn/federation_service.py, 610 lines) which provides:
- 11 domain DMN path mappings
- Tenant-specific override resolution
- Result caching
- Federation across DMN domains

## Consequences

**Positive:**
- New workers follow a known pattern — reduces design decisions and review time.
- Consistent error handling — clinical workers fail-safe, admin workers fail-closed.
- Uniform metrics — dashboards can be templated per archetype.

**Negative:**
- Some workers may not fit neatly into one archetype. Requires Tech Lead review for edge cases.
- Archetype constraints may feel restrictive for experimental features. Mitigation: prototype workers can deviate with explicit Tech Lead approval and a migration plan.
