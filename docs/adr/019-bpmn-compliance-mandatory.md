# ADR-019: BPMN Compliance Rules — Mandatory Governance

**Status:** Accepted
**Date:** 2026-02-17
**Deciders:** Tech Lead, Platform Architect
**Supersedes:** None
**Related:** ADR-001 (CIB7 Engine), ADR-003 (External Task Workers), ADR-016 (Topic Naming)

## Context

The BPMN Audit Swarm (2026-02-17) discovered 91 compliance issues across 56 BPMN files: 17 CRITICAL, 21 HIGH, 51 MEDIUM, 2 LOW. Root causes identified:

1. **Test coverage illusion** — 508 tests pass but mock the BPM engine; BPMN XML never validated
2. **Manual review fatigue** — 56 files × 200+ tasks = 11,200 inspection points exceed human capacity
3. **No enforcement mechanism** — ADR-003/015/016 govern workers, but NO ADR governed BPMN files
4. **Namespace evolution** — 13 files retained Zeebe namespace after migration to CIB7 (Camunda 7 fork)
5. **Topic convention drift** — Workers use `domain.action` (ADR-016) but 123 BPMN topics use kebab-case

This ADR closes the governance gap by defining mandatory BPMN compliance rules with automated enforcement.

## Decision

### R1: Namespace — CRITICAL

All BPMN definitions MUST declare:
```xml
xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
```

MUST NOT use:
- `http://camunda.org/schema/zeebe/1.0` (Zeebe namespace)
- Custom namespaces (e.g., `xmlns:cib7`)

**Rationale:** CIB7 engine rejects Zeebe namespace at deployment. 13 files blocked from deployment.
**Enforcement:** CI/CD blocker (`.github/workflows/bpmn-validation.yml`), pre-commit hook.

### R2: Topic Format — CRITICAL

All `camunda:topic` values MUST follow ADR-016 convention:
```
{domain}.{subprocess}.{action}
```

MUST NOT use:
- kebab-case (`surgical-scheduling`)
- camelCase (`surgicalScheduling`)
- Flat names without domain prefix

**Rationale:** 123 kebab-case topics in BPMN never match worker TOPIC constants → process instances stall.
**Enforcement:** CI/CD blocker — regex check for hyphens in topic attributes.

### R3: File Naming — HIGH

BPMN files MUST follow:
```
SP-{DOMAIN}-{NNN}_{Description}.bpmn
```

Where DOMAIN is one of:
- `PA` — patient_access
- `CO` — clinical_operations
- `RC` — revenue_cycle
- `PS` — platform_services

**Rationale:** Consistent naming enables automated discovery and prevents duplicate confusion.
**Enforcement:** CI/CD warning (non-blocking).

### R4: BPMNDI Diagram Section — HIGH

Every BPMN file MUST include a `<bpmndi:BPMNDiagram>` section.

**Rationale:** 12 files missing BPMNDI cannot be opened in Camunda Modeler → forces error-prone manual XML editing.
**Enforcement:** CI/CD warning (non-blocking).

### R5: Unique Process IDs — CRITICAL

The `<bpmn:process id="...">` value MUST be unique across the entire repository.

**Rationale:** 9 duplicate ID scenarios found. Duplicate IDs cause non-deterministic deployment — last-deployed wins, potentially executing the wrong process version.
**Enforcement:** CI/CD blocker — extract all process IDs and fail on duplicates.

### R6: Error Boundary Events — MEDIUM

Service tasks SHOULD have `<bpmn:boundaryEvent>` with error event definition attached.

**Rationale:** 200+ service tasks without error boundaries → process hangs indefinitely on worker failure.
**Enforcement:** Quarterly audit report (not CI/CD blocker).

### R7: Topic–Worker Connectivity — CRITICAL

- Every `camunda:topic` in BPMN MUST have at least one active worker with a matching `TOPIC` constant
- Every worker `TOPIC` constant SHOULD appear in at least one BPMN file

**Rationale:** 59 orphan BPMN topics (no worker) + 47 orphan workers (no BPMN reference) = 106 disconnects. Orphan BPMN topics create process instances that never complete.
**Enforcement:** `scripts/validate/validate_bpmn_worker_connectivity.py` in CI/CD (exit code 1 on orphan BPMN topics).

### R8: Single Canonical Location — HIGH

Each process MUST exist in exactly one BPMN file. Superseded files MUST be moved to a `.archive/` subdirectory within the same domain folder.

**Rationale:** 4+ duplicate files found (e.g., `glosa_management.bpmn` vs `SP-RC-007_Denial_Management.bpmn`). Team edits wrong version → changes lost.
**Enforcement:** Quarterly deduplication audit.

## Implementation

### Phase 1: CI/CD Automation (Week 1)
- `.github/workflows/bpmn-validation.yml` — R1, R2, R5 as blockers; R3, R4 as warnings
- `scripts/validate/validate_bpmn_worker_connectivity.py` — R7 enforcement

### Phase 2: Pre-commit Hooks (Week 2)
- `scripts/validate/bpmn_pre_commit_hook.sh` — Local validation before push

### Phase 3: Integration Tests (Week 3)
- `tests/integration/test_bpmn_deployment.py` — Actual CIB7 engine deployment validation
- `tests/integration/test_bpmn_connectivity.py` — Topic ↔ worker cross-reference

### Phase 4: Continuous Monitoring (Month 2)
- Quarterly BPMN Audit Swarm (next: May 2026)
- BPMN health dashboard metrics

## Consequences

**Positive:**
- CI/CD blocks PRs introducing namespace, topic format, or duplicate ID violations
- Automated detection eliminates manual review fatigue (11,200 inspection points → automated)
- Integration tests catch deployment failures before production
- Clear governance closes the ADR gap between worker standards (ADR-003/016) and BPMN standards
- Quarterly audits track compliance drift with trend analysis

**Negative:**
- Existing non-compliant files must be remediated (addressed by BPMN-FIX-P0 and P1 swarms)
- CI/CD may block PRs during remediation period. Mitigation: phase enforcement gradually (warnings → blockers)
- Additional pipeline execution time (~30s for BPMN validation). Mitigation: run only on `*.bpmn` file changes

## References

- `.swarm/bpmn-audit-reflection.md` — Root cause analysis and prevention framework
- `scripts/validate/validate_bpmn_worker_connectivity.py` — Connectivity validation script
- ADR-001: CIB7 as BPM Engine
- ADR-003: Python External Task Workers
- ADR-016: Topic Naming Convention
- ADR-017: Anti-Pattern Enforcement
