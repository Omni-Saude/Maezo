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

```
/
├── bpmn/                  # BPMN process models (.bpmn)
├── dmn/
│   ├── global/            # Default decision tables
│   └── tenants/           # Tenant-specific overrides
│       ├── austa-hospital/
│       ├── amh-sp-morumbi/
│       └── ...
├── workers/
│   ├── worker-eligibility/
│   ├── worker-tiss/
│   ├── worker-denial/
│   ├── worker-whatsapp/
│   ├── worker-clinical/
│   └── worker-base/       # Shared AustaWorker framework
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
