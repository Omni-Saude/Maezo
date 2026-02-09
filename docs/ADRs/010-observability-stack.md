# ADR-010: Observability — Prometheus + Grafana + ELK + CIB ins7ght

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, DevOps Lead

## Context

The platform runs 10+ services (engine, 6+ workers, bridge, FHIR server, Mirth Connect) across 5 Kubernetes namespaces. Without unified observability, diagnosing stuck processes, slow workers, or CDC lag requires container SSH — unacceptable for production.

The three pillars (metrics, logs, traces) must be covered, plus BPM-specific analytics (process heatmaps, bottleneck detection, SLA monitoring). CIB Seven exposes Prometheus-compatible metrics natively.

## Decision

The observability stack has four layers:

| Layer | Tool | Purpose |
|---|---|---|
| **Metrics** | Prometheus 2.51 + Alertmanager | Scrapes all services; routes alerts to Slack/PagerDuty |
| **Dashboards** | Grafana 11 | Engine health, worker throughput, Kafka lag, PostgreSQL, Redis |
| **Logs** | Elasticsearch 8.13 + Kibana + Fluentd | Centralized structured logging (JSON with `processInstanceId`, `tenantId`, `correlationId`) |
| **Process Analytics** | CIB ins7ght (Enterprise, R$60K/year) | BPMN heatmaps, duration analysis, bottleneck detection, SLA compliance |

**Critical alerting rules** (Prometheus, stored in `/infra`):

| Alert | Severity |
|---|---|
| Engine job executor backlog > 1,000 | P1 |
| Worker External Task fetch failures > 5/min | P1 |
| Process SLA breach (timer event fired) | P1 |
| Kafka consumer lag > 10,000 | P2 |
| PostgreSQL connection pool > 80% | P2 |

All workers expose `/health` and `/metrics` endpoints via the `AustaWorker` base framework (Prometheus Python client).

## Consequences

**Positive:**

- Full three-pillar coverage plus BPM-native process analytics. Operations diagnoses any issue from dashboard to individual log line without container access.
- ins7ght provides BPMN-native visualization — execution counts and durations overlaid on diagrams. Essential for process optimization conversations with business stakeholders.

**Negative:**

- Four observability tools is a significant operational surface. *Mitigation:* all deployed via Helm charts. ELK is heaviest; can be replaced with Loki (Grafana stack) later if cost is a concern.
- ins7ght R$60K/year is the only paid software component besides AWS. *Mitigation:* identifying a 1-day billing cycle reduction is worth significantly more than R$60K.
