# ADR-018: Platform Atomization Blueprint

**Status:** Accepted
**Date:** 2026-02-16
**Deciders:** Tech Lead, Platform Architect
**References:** ADR-009 (Amendment 2026-02-16), ADR-015, ADR-016

## Context

The platform has grown to 283 workers, 54 BPMN processes, and 982 DMN tables across 4 domains. To maintain coherence, each subprocess must be a self-contained atomic unit with clear boundaries. This ADR maps the current state and defines the migration checklist for any remaining non-conforming workers.

## Decision

### Domain Map

| Domain | Subprocesses | Workers | DMN Tables | BPMN Processes |
|--------|-------------|---------|------------|----------------|
| revenue_cycle | billing, coding, glosa, collection, production | 91+ | 400+ | 10 (SP-RC-001 to SP-RC-010) |
| patient_access | registration, scheduling, insurance | 35+ | 50+ | 1 main + subprocesses |
| clinical_operations | surgical, nursing, pharmacy | 30+ | 100+ | 7 (SP-CO-001 to SP-CO-007) |
| platform_services | analytics, integration, optimization | 20+ | 30+ | 3 |

### Atomic Unit Structure

Each subprocess follows the structure defined in ADR-009 Amendment:

```
{domain}/{subprocess}/
├── bpmn/SP-{XX}-{NNN}_{Name}.bpmn
├── workers/
│   ├── __init__.py          # Exports all workers + register functions
│   ├── base.py              # Optional subprocess-specific base
│   └── {action}_worker_v2.py
├── dmn/{category}/{prefix}_{cat}_{NNN}.dmn
└── tests/test_{action}_worker.py
```

### Worker Migration Checklist

For any worker not yet conforming to V2 standards:

1. **Identify archetype** (ADR-015): CLINICAL_ALERT, CLINICAL_SCORE, ADMIN_ADJUDICATION, or OPERATIONAL_ROUTING
2. **Extract business rules to DMN**: Convert if/elif chains (AP1) and embedded tables (AP4) to DMN decision tables
3. **Inherit BaseExternalTaskWorker**: Replace raw camunda client usage with base class
4. **Implement 3-output routing**: Map DMN result to PROSSEGUIR/BLOQUEAR/REVISAR
5. **Apply topic naming** (ADR-016): Rename topic to `{domain}.{subprocess}.{action}`
6. **Add metrics**: Implement archetype-specific Prometheus counters
7. **Verify LOC < 200**: Split if necessary
8. **Update __init__.py**: Export worker class and register function
9. **Write/update tests**: Minimum 3 test cases (happy path, error path, edge case)
10. **Archive V1 worker**: Move to `.archive/workers/{domain}/{subprocess}/`

### Current Migration Status

| Subprocess | V2 Complete | V1.5 Remaining | Notes |
|-----------|-------------|----------------|-------|
| billing | 13/13 | 0 | Fully migrated (Swarm M) |
| coding | 10/10 | 0 | Fully migrated (Swarm M) |
| glosa | 10/10 | 0 | Fully migrated (Swarm M) |
| collection | 50/50 | 0 | All V2 |
| production | 8/8 | 0 | Fully migrated (Swarm M) |
| patient_access | 35/35 | 0 | All V2 |
| clinical_operations | 1/56 | 55 | **AUDITED:** 56 workers (1.8% V2-ready), 241 DMN tables needed, 65% LOC reduction target |
| platform_services | 0/29 | 29 | **AUDITED:** 29 workers (0% V2-ready), 85 DMN tables needed, 65% LOC reduction target |

**Audit Complete (Swarm Q, 2026-02-16):**
- **Total workers audited:** 85 (56 clinical_operations + 29 platform_services)
- **V2-ready:** 1 (adverse_event_detection_worker_v2.py only)
- **Need migration:** 84 (98.8%)
- **Total DMN tables to create:** ~326 (241 clinical + 85 platform)
- **Current total LOC:** ~36,500 → **Target LOC:** ~12,750 (65% reduction)
- **Anti-pattern distribution:**
  - AP1 (if/elif chains): 39 occurrences
  - AP3 (complex logic): 24 occurrences
  - AP4 (embedded tables): 38 occurrences
  - AP6 (no inheritance): 28 occurrences (all doctor_*/patient_* workers)
- **Migration effort:**
  - LOW: 29 workers (34.1%)
  - MEDIUM: 42 workers (49.4%)
  - HIGH: 14 workers (16.5%)
- **Topic naming violations:** 29 platform_services workers use kebab-case instead of ADR-016 format
- **Orphaned topics:** 39 topics without workers (31 platform_services, 8 clinical_operations)

**Next Steps:** Execute Swarm R migration plan (20-27 days, 12 agents, 5 phases).

## Consequences

**Positive:**
- Complete visibility into platform composition and migration status.
- Clear, repeatable checklist for migrating any remaining non-conforming workers.
- Atomic unit structure ensures new subprocesses are created correctly from the start.

**Negative:**
- Blueprint requires periodic updates as workers are added/removed. Mitigation: update as part of PR process.
- Audit of clinical_operations and platform_services still pending. Mitigation: schedule as Swarm Q.

## Related Decisions

- **ADR-003:** Defines external task workers as Python Camunda workers
- **ADR-009:** Defines atomic unit structure for subprocesses
- **ADR-015:** Defines 4 worker archetypes and routing patterns
- **ADR-016:** Defines topic naming conventions and DMN integration
