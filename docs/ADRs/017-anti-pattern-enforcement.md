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
| **AP7** | **Throwaway Validation Scripts** | **CRITICAL** | Creating one-time bash/Python scripts in `.swarm/` for manual validation instead of permanent pytest modules with CI/CD integration | Scripts in `.swarm/` for testing/validation not converted to `tests/integration/` within same sprint |

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
   - **Throwaway script detection:** Fail PR if `.swarm/*.{sh,py}` contains test/validation logic not mirrored in `tests/`

3. **Precedent Documentation** — The `.archive/workers/` directory (47 archived V1 workers) serves as a reference for what these anti-patterns look like in practice.

### AP7 Detailed Guidance

**Anti-Pattern:** Creating validation/test scripts in `.swarm/` directory for one-time manual execution.

**Why It's Wrong:**
- Scripts are hidden, not discoverable by team
- No CI/CD integration — tests don't run automatically
- Not reusable — throwaway after single use
- Not maintainable — no version control tracking
- Violates automation-first principle

**Correct Pattern:**
```
tests/
  integration/
    bpmn/
      test_deployment.py          # pytest module
      test_namespace_compliance.py
      test_topic_connectivity.py
      test_process_instantiation.py
    conftest.py                    # fixtures
  
.github/workflows/
  bpmn-validation.yml              # CI/CD job with service containers

docker-compose.test.yml            # Local test environment

tests/integration/README.md        # Team documentation
```

**Exception:** Prototyping/exploration scripts are acceptable ONLY if:
1. Clearly marked as prototype in filename: `.swarm/PROTOTYPE_*.sh`
2. Accompanied by immediate follow-up task to convert to pytest
3. Deleted within same sprint after conversion

**Detection:** PR fails if `.swarm/` contains `test_*.py`, `validate_*.py`, `*_test.sh`, or similar patterns not marked as PROTOTYPE.

## Consequences

**Positive:**

- Prevents regression to V1 patterns as team scales.
- PR checklist catches issues before merge.
- Archived V1 workers serve as teaching material for new developers.
- **AP7 enforcement ensures permanent, automated, discoverable test infrastructure.**

**Negative:**

- Additional PR review overhead. Mitigation: checklist is short (7 items) and becomes habitual.
- Automated rules may produce false positives. Mitigation: severity-based — only CRITICAL blocks merge, MAJOR generates warnings.

## Related Decisions

- **ADR-003:** Defines external task workers as Python Camunda workers
- **ADR-015:** Defines 4 worker archetypes (CLINICAL_ALERT, CLINICAL_SCORE, ADMIN_ADJUDICATION, OPERATIONAL_ROUTING)
- **ADR-016:** Defines topic naming conventions
