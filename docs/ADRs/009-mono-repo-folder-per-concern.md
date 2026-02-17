# ADR-009: Mono-repo with Folder-per-Concern Structure

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, DevOps Lead

## Context

The platform consists of multiple artifact types with interdependencies: BPMN process models reference External Task topic names that workers implement; DMN tables define input/output schemas that workers consume.

Two strategies evaluated:

| Criterion | Mono-repo | Poly-repo |
|---|---|---|
| Cross-artifact consistency | Atomic commits | Cross-repo PRs |
| Search/refactor | Single find-replace | Multi-repo grep |
| CI/CD | Path-filtered pipelines | Per-repo pipelines |
| Onboarding | Clone one repo | Clone N repos |
| Permission granularity | CODEOWNERS (review gates) | Repo-level access |

With poly-repo, ensuring consistency between a BPMN topic name change and the corresponding worker's subscription requires cross-repo coordination. For ~8 FTEs, this overhead is significant.

## Decision

Single **mono-repo** (`austa-orchestration-platform`) with this top-level structure:

```text
/
├── bpmn/                  # BPMN process models (.bpmn)
├── dmn/
│   ├── global/            # Default decision tables
│   └── tenants/           # Tenant-specific overrides
│       ├── hospital-a/
│       ├── amh-sp-morumbi/
│       └── ...
├── workers/
│   ├── worker-eligibility/
│   ├── worker-tiss/
│   ├── worker-denial/
│   ├── worker-whatsapp/
│   ├── worker-clinical/
│   └── worker-base/       # Shared MaezoWorker framework
├── adapters/
│   ├── tasy-adapter/
│   ├── mvsoul-adapter/
│   └── fhir-bridge/
├── bridge/                # CDC-to-BPM bridge service
├── engine/                # CIB Seven Spring Boot config
├── infra/
│   ├── terraform/
│   ├── helm/
│   └── k8s/
├── tests/
│   ├── e2e/
│   └── load/
├── docs/
│   ├── adr/               # This folder
│   ├── specs/
│   └── runbooks/
├── CODEOWNERS
└── README.md
```

**CODEOWNERS enforcement:**

- `/bpmn`, `/dmn` → Business Analyst + Tech Lead
- `/workers` → Python Dev + Tech Lead
- `/engine` → Java Dev + Tech Lead
- `/infra` → DevOps Lead

**CI/CD:** path-filtered — changes to `/workers/worker-eligibility` only trigger that worker's build/test/deploy. Changes to `/bpmn` trigger BPMN validation + DMN test suite + engine deployment.

## Consequences

**Positive:**

- Atomic commits across BPMN + worker + DMN. Topic name changes in the same PR, reviewed together, merged atomically. Eliminates cross-repo drift.
- Unified search and refactoring — single find-and-replace for topic renames.
- Simplified onboarding — new developer clones one repo, full context available.

**Negative:**

- Repository size will grow. *Mitigation:* path-filtered CI ensures only affected components build. Git LFS for binary assets if needed.
- All developers can read all code (review gates via CODEOWNERS, not access control). Acceptable for current team size.

**Trade-off:** If team scales beyond 20 devs or independent product teams emerge, revisit in favor of multi-repo with shared library strategy.

---

## Amendment 1: Domain-Driven Structure Evolution (2026-02-09)

**Status:** Accepted  
**Deciders:** Tech Lead, Architecture Review

### Context for Amendment

During Phase 7-8 implementation, the original centralized structure (`/dmn/`, `/workers/` at root) created several friction points:

1. **Cognitive Load:** 600+ workers in flat `/workers/` folder made navigation difficult
2. **Domain Coupling:** DMN tables semantically belong with their consuming workers
3. **ADR-007 Alignment:** DMN Federation requires domain-aware path resolution
4. **Team Scaling:** Domain teams need clear ownership boundaries

### Revised Decision

Evolve to **domain-driven structure** within mono-repo:

```text
platform/
├── patient_access/           # Domain: Scheduling, Registration, Authorization
│   ├── bpmn/                 # Domain-specific process models
│   ├── dmn/                  # Domain decision tables
│   │   └── authorization/    # 68 DMN (authorization rules)
│   └── workers/              # Domain workers
│       ├── check_authorization_requirements_worker.py
│       ├── validate_eligibility_worker.py
│       └── ...
├── clinical_operations/      # Domain: Clinical Production, Safety, Documentation
│   ├── bpmn/
│   ├── dmn/
│   │   └── clinical_safety/  # 268 DMN (DDI, EWS, LAB, MED, RSK, etc.)
│   └── workers/
├── revenue_cycle/            # Domain: Billing, Coding, Collections, Denial Management
│   ├── bpmn/
│   ├── dmn/
│   │   ├── billing/          # Billing rules
│   │   ├── coding_audit/     # Coding validation
│   │   ├── glosa_prevention/ # Denial prevention
│   │   ├── revenue_recovery/ # Appeal/collection rules
│   │   ├── pricing/          # Pricing tables
│   │   └── cash_operations/  # Cash management
│   └── workers/
├── platform_services/        # Domain: Cross-cutting services
│   ├── bpmn/
│   ├── dmn/
│   │   ├── compliance/       # LGPD, regulatory compliance
│   │   ├── credentialing/    # Provider credentialing
│   │   ├── access_control/   # Permission rules
│   │   └── infrastructure/   # System configuration
│   └── workers/
└── shared/                   # Shared across all domains
    ├── dmn/
    │   ├── federation_service.py  # ADR-007 tenant-aware resolution
    │   └── tenant_overrides/      # Tenant-specific DMN overrides
    │       ├── {tenant}/
    │       │   ├── patient_access/
    │       │   ├── clinical_operations/
    │       │   ├── revenue_cycle/
    │       │   └── platform_services/
    ├── protocols/            # Shared interfaces
    ├── models/               # Shared data models
    └── utils/                # Shared utilities
```

### Domain Mapping Reference

| Category | Domain | Rationale |
|----------|--------|-----------|
| authorization | patient_access | Pre-service eligibility/auth |
| clinical_safety (DDI, EWS, LAB, MED, RSK, SYN, VIT, DDX, DLI) | clinical_operations | Clinical decision support |
| billing, coding_audit, glosa_prevention, revenue_recovery, pricing, cash_operations | revenue_cycle | Financial operations |
| compliance, credentialing, access_control, infrastructure | platform_services | Cross-cutting concerns |

### Federation Service Integration

Per ADR-007, the `FederatedDMNService` resolves DMN tables in priority order:

1. **Tenant Override:** `platform/shared/dmn/tenant_overrides/{tenant}/{domain}/{category}/{table}.dmn`
2. **Domain Base:** `platform/{domain}/dmn/{category}/{table}.dmn`
3. **Fallback Error:** If not found, raise `DMNNotFoundException`

### CODEOWNERS Update

```text
# Domain ownership
/platform/patient_access/     → @patient-access-team + Tech Lead
/platform/clinical_operations/ → @clinical-team + Medical Informatics Lead
/platform/revenue_cycle/       → @revenue-team + Tech Lead
/platform/platform_services/   → @platform-team + Tech Lead
/platform/shared/              → Tech Lead (approval required)
```

### Consequences of Amendment

**Positive:**

- Domain teams have clear ownership boundaries
- Reduced cognitive load (workers with their DMN)
- Aligns with ADR-007 DMN Federation tenant override structure
- Supports independent domain deployments in future

**Negative:**

- Deeper directory nesting
- Federation service must resolve domain paths (implemented)
- Cross-domain imports require explicit shared module usage

**Migration Note:** Phase 7.5.2 migrated 633 legacy DMN files to domain structure. Legacy centralized DMN archived in `Legacy processes/dmn-phase6-inferior/`.

---

## Amendment 2: Revenue Cycle Subdomain Structure (2026-02-09)

**Status:** Accepted  
**Deciders:** Tech Lead, Architecture Review

### Context for Amendment 2

The `revenue_cycle` domain contains 89 workers — significantly larger than other domains (patient_access: 23, clinical_operations: 20, platform_services: 29). A flat `workers/` folder would create navigation challenges.

### Revised Decision for Large Domains

Allow **subdomain folders** within `revenue_cycle` as an exception for large domains (50+ workers):

```text
platform/revenue_cycle/
├── billing/                  # Subdomain: TISS generation, submission
│   ├── bpmn/
│   └── workers/              # 13 workers
├── coding/                   # Subdomain: Coding, audit, validation
│   ├── bpmn/
│   └── workers/              # 10 workers
├── collection/               # Subdomain: Payment, reconciliation
│   └── workers/              # 48 workers (largest)
├── glosa/                    # Subdomain: Denial management, appeals
│   ├── bpmn/
│   └── workers/              # 10 workers
├── production/               # Subdomain: Charge capture, pricing
│   ├── bpmn/
│   └── workers/              # 8 workers
├── bpmn/                     # Domain-level BPMN (SP-RC-001 to SP-RC-010)
├── dmn/                      # Domain DMN (follows standard structure)
│   ├── billing/
│   ├── coding_audit/
│   ├── glosa_prevention/
│   ├── revenue_recovery/
│   ├── pricing/
│   └── cash_operations/
└── services/                 # Domain services (DMN aggregation)
    ├── billing_rules_service.py
    ├── glosa_prevention_service.py
    ├── appeal_strategy_service.py
    └── pricing_service.py
```

### Rationale

1. **Scale**: 89 workers require subdomain organization
2. **Team Structure**: Billing, coding, collection teams work independently
3. **Import Clarity**: `platform.revenue_cycle.billing.workers.X` is explicit
4. **No Breaking Changes**: Structure was established in Phase 2

### Applicability

This variant is **only acceptable** for domains with 50+ workers. Other domains must follow flat `workers/` structure.

| Domain | Workers | Structure |
|--------|---------|-----------|
| patient_access | 23 | Flat `workers/` |
| clinical_operations | 20 | Flat `workers/` |
| platform_services | 29 | Flat `workers/` |
| **revenue_cycle** | **89** | **Subdomain folders** (exception) |

---

## Atomic Unit Definition (Amendment — 2026-02-16)

### The Atomic Unit: BPMN ↔ Workers ↔ DMN Triad

The **atomic unit** of the platform is the triad:

```text
1 BPMN subprocess ↔ N workers ↔ M DMN tables
```

Each subprocess folder must contain:

```text
{domain}/{subprocess}/
├── bpmn/          # BPMN subprocess definition(s)
├── workers/       # Python external task workers
│   ├── __init__.py
│   ├── base.py    # Optional subprocess-specific base
│   └── {action}_worker_v2.py
├── dmn/           # DMN tables consumed by these workers
│   ├── {category}/
│   │   └── {prefix}_{category}_{NNN}.dmn
│   └── federated/
│       └── fed_{prefix}_{NNN}.dmn
└── tests/         # Unit tests mirroring workers
```

### Current Domains Following This Structure

- `revenue_cycle/billing/` (13 workers, 80+ DMN)
- `revenue_cycle/coding/` (10 workers, 30+ DMN)
- `revenue_cycle/glosa/` (10 workers, 70+ DMN)
- `revenue_cycle/collection/` (50 workers, 60+ DMN)
- `revenue_cycle/production/` (8 workers, 20+ DMN)

### Colocation Rule

**Workers and DMN tables must be colocated within their subprocess folder.** Cross-subprocess DMN references must go through `FederatedDMNService`.

### Rationale

1. **Semantic Cohesion**: A BPMN subprocess, its workers, and its decision tables form a logical unit. Separating them breaks this cohesion.

2. **Change Atomicity**: Changes to a subprocess — new decision rules, worker logic updates, process flow modifications — can be committed atomically. Splitting across folders increases the risk of missed synchronization.

3. **Tenant Override Alignment**: ADR-007 specifies that tenant overrides follow domain/subprocess structure. Colocation ensures the override path mirrors the base structure exactly.

4. **Developer Workflow**: A developer implementing a new business rule navigates to one folder (`revenue_cycle/glosa/`), not scattered across `dmn/glosa_prevention/` and `workers/` at different levels.

5. **Federation Service Predictability**: `FederatedDMNService` resolves paths deterministically. Consistent colocation eliminates ambiguity.

### Structural Violation Detection

Flag these patterns as structural violations:

| Pattern | Violation | Fix |
|---------|-----------|-----|
| Worker in `revenue_cycle/workers/` but DMN in `revenue_cycle/dmn/glosa/` | Scattered structure | Move worker to `revenue_cycle/glosa/workers/` |
| DMN in `dmn/global/` referenced by single subprocess only | Over-generalization | Move DMN to subprocess folder |
| Worker directly imports another domain's DMN | Cross-domain coupling | Use `FederatedDMNService` + tenant overrides |
| Subprocess has no `dmn/` folder | Incomplete atom | Create `dmn/` and define decision tables |

### Migration Path for Existing Violations

Existing violations pre-Amendment should be refactored during the next maintenance cycle:

1. Audit all workers for direct DMN imports (should only use `FederatedDMNService`)
2. Move misplaced DMN tables to their subprocess homes
3. Update import paths and federation service calls
4. Verify tests pass after movement
