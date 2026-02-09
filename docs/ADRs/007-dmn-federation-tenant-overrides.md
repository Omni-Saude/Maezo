# ADR-007: DMN Federation with Tenant-Specific Overrides

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, Business Analysts, Process Architect

## Context

Business rules vary across hospital units and across the external payers they bill. For example: eligibility rules differ by payer contract (Bradesco vs. Unimed vs. SulAmérica vs. AUSTA Saúde), TISS validation rules differ by ANS version adopted, clinical alert thresholds may differ by hospital protocol, and revenue capture rules differ by unit-specific fee schedules.

> **Clarification on payers vs. tenants:** Payers (Bradesco, Unimed, SulAmérica, Amil, AUSTA Saúde, etc.) are **external entities** the hospital bills. They are not tenants. Payer-specific rules (eligibility carência, contract terms, fee schedules) are modeled as **input parameters** to DMN tables, not as separate tenant deployments. Tenant overrides are reserved for differences between **hospital units** (e.g., austa-hospital uses different coding rules than amh-sp-morumbi because they run different ERPs or follow different local protocols).

The platform uses DMN 1.3 decision tables for all rule-based logic. Three strategies were considered:

1. Single global DMN with tenant-specific input columns
2. Separate DMN per tenant (full duplication)
3. **Federated model** — global defaults + tenant-specific overrides using CIB Seven's deployment tenant resolution

## Decision

We adopt a **federated DMN model**:

- **Global DMN tables** deployed without `tenantId` — available to all hospital units as defaults
- **Tenant-specific DMN tables** deployed with corresponding `tenantId` — override global version for that hospital unit only
- **Payer-specific logic** handled via input parameters within global/tenant DMN tables (e.g., column `payerId` → different rules per payer), not via separate deployments
- **Resolution logic** (CIB Seven native): engine checks for tenant-specific deployment first; if none exists, falls back to global (no-tenant) deployment

**Governance:**

- DMN tables versioned in Git alongside BPMN processes
- CI/CD deploys global DMN without tenant, then iterates tenant-specific DMN folders deploying each with appropriate `tenantId`
- Tenant-specific overrides must include a comment explaining divergence from global
- Business Analyst reviews all overrides quarterly to identify rules promotable to global

## Consequences

**Positive:**

- Minimizes rule duplication. Most rules are global (ANS TISS schema, qSOFA thresholds, payer contract logic). Only genuinely different hospital-unit-level rules are overridden per tenant.
- Global rule updates (e.g., new ANS TISS version) deployed once, immediately effective across all non-overriding hospital units.
- Business analysts work on tenant rules independently without affecting other units.
- Payer-specific logic is centralized in global DMN tables, making it easy to onboard a new payer across all hospital units simultaneously.

**Negative:**

- Override mechanism is implicit — no dashboard showing which units override which rules. *Mitigation:* CI/CD generates a DMN inventory matrix (tenant × DMN table) showing global vs. overridden status.
- Testing complexity increases: same process can execute different rules depending on tenant. *Mitigation:* DMN test suite runs each table with test cases for both global and every tenant override.
