# ADR-002: Single Engine with Tenant Markers

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, Architecture Team

## Context

The platform must serve multiple hospital units (`hospital-a`, `amh-sp-morumbi`, `amh-rj-barra`, `amh-mg-bh`), each with locally adapted processes and rules, but sharing the same infrastructure. The platform scope is the **entire hospital digital operation** — from patient access through clinical delivery, revenue cycle, and platform services — as defined in the Hospital Digital Manifesto (4 domains, 29 subprocesses, 5 patient journeys).

> **Scope boundary:** The AUSTA Saúde healthcare plan (operadora) will operate a **separate** orchestration platform. Payers (Bradesco, Unimed, SulAmérica, Amil, AUSTA Saúde, etc.) are external entities referenced in DMN decision tables and operator portal integrations — they are not tenants of this platform.

CIB Seven offers three multi-tenancy strategies:

1. **Tenant Markers** — single engine, shared database, tenant ID on each process instance
2. **Multi-Engine** — one engine per tenant, separate databases
3. **Hybrid** — shared engine with tenant-specific databases

The hospital units run structurally identical processes (revenue cycle, clinical operations, patient access) with local variations in DMN rules (e.g., different payer contract terms per unit, different clinical protocol thresholds). Expected tenant count: 4–8 in Year 1, potentially 15+ as AMH expands to new hospital units.

## Decision

We will use the **Tenant Markers** strategy: a single CIB Seven engine instance with a shared PostgreSQL database, where every process instance, deployment, and task carries a `tenantId` marker.

- **Federation model:** global defaults (deployed without tenant) plus tenant-specific overrides (deployed with `tenantId`). Resolution: engine checks tenant-specific first, falls back to global.
- **Tenant identifiers:** `hospital-a`, `amh-sp-morumbi`, `amh-rj-barra`, `amh-mg-bh`. Each identifier represents a **hospital unit**, not a payer or business line.
- **Provisioning:** bootstrap script creates tenant marker, seeds default user groups, deploys global process package.

## Consequences

**Positive:**

- Minimal operational overhead — one engine to monitor, one database to backup, one deployment pipeline. Critical for ~8 FTE team.
- Global process updates propagate to all tenants with a single deployment.
- All hospital units share the same orchestration model with local rule overrides only where genuinely needed.

**Negative:**

- Noisy-neighbor risk — high-volume tenant could saturate job executor. *Mitigation:* tenant-aware priority queues, per-tenant throughput monitoring in Grafana.
- Logical isolation only, not physical. *Mitigation:* engine enforces tenant filters on all queries; integration tests verify cross-tenant isolation.

**Trade-off:** If a tenant requires physical isolation (regulatory), we can migrate that specific tenant to a dedicated engine without changing worker code.
