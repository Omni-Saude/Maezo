# ADR-017: Anti-Pattern Detection and Enforcement

**Status:** Accepted
**Date:** 2026-02-16
**Deciders:** Tech Lead, Platform Architect
**References:** ADR-003 (Amendment 2026-02-16), ADR-015

## Context

During the V1→V2 migration, 47 workers were archived (Swarm M) because they exhibited anti-patterns that made them unmaintainable, untestable, and inconsistent across tenants. These anti-patterns emerged because ADR-003 prescribed Python external tasks but did not define what workers should NOT do. Without enforcement, the same anti-patterns will reappear as the team grows.

## Decision

### Anti-Pattern Registry

| ID | Name | Severity | Description | Detection |
|----|------|----------|-------------|-----------|
| AP1 | Hardcoded Business Rules | CRITICAL | if/elif chains encoding business logic that should be DMN tables | >5 if/elif branches in a single method evaluating business conditions |
| AP2 | Embedded Workflow Logic | CRITICAL | Worker orchestrates other workers or manages state machines | Worker imports or instantiates other worker classes |
| AP3 | Complex Conditionals | MAJOR | Deeply nested conditionals replacing decision tables | Cyclomatic complexity >10 per method |
| AP4 | Embedded Decision Tables | MAJOR | Python dicts/lists acting as business rule lookup tables | Dict literal with >10 entries used in conditional flow |
| AP5 | Direct DB Access | MAJOR | Worker queries database directly instead of using service layer | Import of sqlalchemy, psycopg2, or raw SQL strings |
| AP6 | Missing Tenant Context | MINOR | Worker does not propagate tenant_id through the call chain | Worker method lacks tenant_id parameter or BaseExternalTaskWorker tenant resolution |

### Enforcement Mechanisms

1. **PR Review Checklist** — Every PR modifying files in `*/workers/` must verify:
   - [ ] Worker inherits from `BaseExternalTaskWorker`
   - [ ] All business decisions delegated to DMN via `FederatedDMNService`
   - [ ] No if/elif chains with >3 branches encoding business rules
   - [ ] Worker LOC < 200 (excluding imports/models)
   - [ ] Worker conforms to one of the 4 archetypes (ADR-015)
   - [ ] Topic name follows convention (ADR-016)

2. **Automated Detection (Future)** — CI pipeline rules:
   - Cyclomatic complexity check via `radon` (threshold: 10)
   - Import analysis: flag workers importing other workers
   - LOC count: flag workers exceeding 200 lines

3. **Precedent Documentation** — The `.archive/workers/` directory (47 archived V1 workers) serves as a reference for what these anti-patterns look like in practice.

## Consequences

**Positive:**
- Prevents regression to V1 patterns as team scales.
- PR checklist catches issues before merge.
- Archived V1 workers serve as teaching material for new developers.

**Negative:**
- Additional PR review overhead. Mitigation: checklist is short (6 items) and becomes habitual.
- Automated rules may produce false positives. Mitigation: severity-based — only CRITICAL blocks merge, MAJOR generates warnings.

## Related Decisions

- **ADR-003:** Defines external task workers as Python Camunda workers
- **ADR-015:** Defines 4 worker archetypes (CLINICAL_ALERT, CLINICAL_SCORE, ADMIN_ADJUDICATION, OPERATIONAL_ROUTING)
- **ADR-016:** Defines topic naming conventions
