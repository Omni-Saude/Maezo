# ADR-003: Python External Task Workers over Embedded Java Delegates

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, CTO

## Context

Business logic includes FHIR lookups, TISS XML generation (ANS 4.01), denial analysis with ML models, WhatsApp Business API integration, sepsis score calculations (qSOFA/SOFA), and ERP data transformations.

Two patterns exist in CIB Seven:

1. **Embedded Java Delegates** — business logic runs inside the engine JVM as Java classes
2. **External Task pattern** — engine creates tasks that external workers fetch via REST long-polling, execute independently, and report back

The MAEZO team has 4 Python developers and 1 Java developer. Python is the primary language for data science, ML, and existing integrations. The Java developer is allocated to engine configuration, not business logic.

## Decision

All business logic will be implemented as **Python External Task workers** using `camunda-external-task-client-python3` version 4.5.0. No Java delegates will be written for business logic.

- Java developer maintains engine Spring Boot application (configuration, upgrades, plugins) only.
- **Exception:** WhatsApp worker may use Node.js 18+ if the WhatsApp Business API SDK is significantly better in Node.js. Requires Tech Lead approval and addendum to this ADR.
- Workers are stateless, horizontally scaled via Kubernetes HPA, and communicate with the engine **exclusively** through the REST API (`fetchAndLock`, `complete`, `handleFailure`, `handleBpmnError`).
- Workers do not consume Kafka directly (see ADR-006).

## Consequences

**Positive:**

- Entire business logic layer in Python — the team's strongest language. Hiring, onboarding, and code review velocity maximized.
- Workers independently deployable and scalable. A spike in TISS generation does not affect eligibility verification.
- Engine remains a clean runtime with no custom code, reducing upgrade risk.

**Negative:**

- External Task pattern introduces latency (REST long-poll cycle, typically 5–10s). *Mitigation:* acceptable for billing cycles and clinical alerts; interval is configurable.
- End-to-end debugging requires correlation between engine and worker logs. *Mitigation:* all workers emit structured logs with `processInstanceId` and `activityId`, indexed in Elasticsearch.
