# ADR-016: External Task Topic Naming Convention

**Status:** Accepted
**Date:** 2026-02-16
**Deciders:** Tech Lead, Platform Architect
**Amends:** ADR-003, ADR-009

## Context

The platform has 283 workers subscribing to External Task topics. Without a naming convention, topic names varied: some used camelCase, some snake_case, some included domain prefixes, others did not. This made it difficult to:
1. Map a BPMN serviceTask to its implementing worker
2. Search for all workers in a domain
3. Validate that every topic has exactly one subscriber

## Decision

All External Task topics must follow this pattern:

```
{domain}.{subprocess}.{action}
```

**Examples:**
- `revenue_cycle.billing.validate_claim`
- `revenue_cycle.coding.suggest_cid10`
- `revenue_cycle.collection.parse_payment_file`
- `patient_access.registration.check_existing_patient`
- `clinical_operations.surgical.coordinate_team`

**Rules:**

1. **domain**: Top-level bounded context (`revenue_cycle`, `patient_access`, `clinical_operations`, `platform_services`)
2. **subprocess**: The BPMN subprocess name in snake_case (`billing`, `coding`, `glosa`, `collection`, `production`)
3. **action**: The worker's core action in snake_case, matching the worker filename without `_worker.py` suffix
4. **Worker filename**: Must be `{action}_worker.py` or `{action}_worker_v2.py`
5. **1:1 mapping**: Each topic must have exactly one worker subscriber. If multiple workers need the same input, create a dispatcher worker.

**BPMN serviceTask attribute:**
```xml
<bpmn:serviceTask id="task_validate_claim" name="Validate Claim"
  camunda:type="external"
  camunda:topic="revenue_cycle.billing.validate_claim" />
```

**Enforcement:** A CI lint rule should validate that:
- Every `camunda:topic` in BPMN files has a corresponding worker file
- Every worker file has a corresponding `camunda:topic` in a BPMN file
- Topic names follow the `{domain}.{subprocess}.{action}` pattern

(CI rule implementation deferred to a separate PR.)

## Consequences

**Positive:**
- Instant traceability: topic name → worker file → BPMN task.
- Domain-scoped search: `grep "revenue_cycle.billing"` finds all billing topics.
- Prevents orphaned workers and orphaned topics.

**Negative:**
- Requires renaming existing topics that don't follow the convention. Mitigation: rename incrementally per subprocess during regular maintenance.
- Longer topic names. Mitigation: still well within Camunda's topic name limits.
