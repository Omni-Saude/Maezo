# ADR-012: Engine Replicas — 1 in Phase 1, 2 in Phase 2

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, DevOps Lead, Architecture Team

## Context

The CIB Seven engine is the single point of orchestration — if it goes down, no process instances progress, no external tasks dispatch, no timers fire. High availability is critical for production.

However, multiple replicas introduce complexity: job executor must coordinate to avoid duplicate task execution, database connection load increases.

| Posture | Pros | Cons |
|---|---|---|
| 2 replicas from day 1 (MD doc) | HA immediately | Coordination complexity during ramp-up |
| 1 replica initially (DOCX doc) | Simple, lower cost | 30–60s downtime on pod crash |

During Phase 1 (shadow mode), an engine outage means delayed BPM processing but no business impact — manual process continues. In Phase 2, BPM becomes primary system and outages directly impact operations.

## Decision

**Phase 1 (Weeks 1–16):** single CIB Seven engine replica.

- Job executor runs without coordination overhead
- Database connection pool sized for one engine (20 connections)
- Failover: Kubernetes pod restart (30–60 second recovery)

**Phase 2 (Week 17+):** scale to 2 engine replicas.

- Job executor configured for cluster coordination (database-based locking)
- Database connection pool doubles (40 connections)
- Kubernetes readiness probe ensures traffic routes only to healthy replicas

**Transition:** configuration change only (`replicas: 2` + `clusterMode: true` in Helm values). No code changes, no data migration, no process redeployment.

**Phase 3+ (if needed):** additional replicas added linearly. Database-based job locking supports ~5 replicas before contention concern. Beyond that, evaluate tenant partitioning across engine instances (new ADR required).

## Consequences

**Positive:**

- Phase 1 simplicity: no coordination bugs, simplified debugging (all state in one JVM), reduced infrastructure cost during non-critical period.
- Non-disruptive transition: Helm values change, no downtime.
- Phase 2 HA: automatic failover. Surviving replica continues processing; Kubernetes restarts failed pod. Expected recovery: 30s with zero process instance loss (state in PostgreSQL, not JVM).

**Negative:**

- During Phase 1, pod crash = 30–60s no task dispatching. In-flight External Tasks are not lost (timeout + retry), but timer events may fire late. *Mitigation:* acceptable during shadow mode with manual processes running in parallel.
- 2-replica job executor uses `SELECT FOR UPDATE` locking, adding ~5ms per job acquisition cycle. *Mitigation:* negligible at expected volumes (< 1,000 process instances/day).
