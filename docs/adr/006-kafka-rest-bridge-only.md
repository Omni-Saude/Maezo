# ADR-006: Kafka as Event Bus — Workers Consume via REST Bridge Only

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, Architecture Team

## Context

Apache Kafka 3.7 (KRaft mode) serves as the event streaming backbone for CDC events, inter-process messages, and audit streams. The question: should individual workers consume Kafka topics directly, or should consumption be centralized in a dedicated bridge service?

The DOCX architecture document allowed workers to consume Kafka directly (e.g., clinical alert worker consuming observation events). The MD technical document restricted workers to REST-only communication, with a dedicated CDC-to-BPM bridge consuming Kafka.

If workers consume Kafka directly, they become coupled to two systems (BPM engine via REST **and** Kafka via consumer groups), creating dual coordination complexity for scaling.

## Decision

**Workers will not consume Kafka topics directly.** All Kafka consumption is handled by a single dedicated service: the `cdc-to-bpm-bridge`.

The bridge service is responsible for:

1. Consuming CDC events from Debezium topics
2. Consuming HL7/FHIR events from Mirth Connect topics
3. Transforming events into process variables
4. Starting or correlating process instances via CIB Seven REST API

Workers interact **exclusively** with the CIB Seven engine via the External Task REST API. If a worker needs data that originated from a Kafka event, that data is available as a process variable (set by the bridge) or queryable from the FHIR server.

The bridge service is stateless, horizontally scalable, deployed in the `integration` Kubernetes namespace.

## Consequences

**Positive:**

- Workers remain simple and single-responsibility — fetch tasks, execute logic, report results. No Kafka client libraries, no consumer group management, no offset tracking.
- Scaling decisions straightforward: workers scale on External Task queue depth only (one dimension).
- Testing simpler: worker unit tests mock only REST API. No Kafka in worker test fixtures.

**Negative:**

- Bridge becomes a critical single point of translation. *Mitigation:* 2+ replicas, at-least-once delivery via Kafka consumer offsets, dead-letter topic for failed transformations.
- Additional hop (Kafka → bridge → REST API) adds 100–500ms per event. *Mitigation:* acceptable for billing/admission events.

**Trade-off:** Prioritizes architectural simplicity and team cognitive load over minimal latency. Revisit if future use case (e.g., real-time streaming analytics) requires direct Kafka consumption by a specialized service.
