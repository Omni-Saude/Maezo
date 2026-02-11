# ADR-001: Use CIB Seven 2.1.3 as BPM Engine

**Status:** Accepted  
**Date:** 2026-02-08  
**Deciders:** Tech Lead, CTO, Architecture Team

## Context

The Healthcare Group hospital network requires a central BPM engine to orchestrate revenue cycle, clinical alerts, and patient experience processes across multiple units (Hospital AUSTA, AMH SP, AMH RJ, AMH MG). The engine must support BPMN 2.0, DMN 1.3, External Task pattern, multi-tenancy, and a complete REST API.

Four candidates were evaluated:

| Criterion | CIB Seven 2.1.x | Camunda 8 SaaS | Kogito/Drools | Flowable 7 |
|---|---|---|---|---|
| License | Apache 2.0 | Proprietary SaaS | Apache 2.0 | Apache 2.0 |
| Cost/year | R$ 0 | R$ 2.7M–4.6M | R$ 0 | R$ 0 |
| BPMN 2.0 complete | ✅ | ✅ | Partial | ✅ |
| DMN 1.3 native | ✅ (FEEL, hot-deploy) | ✅ | ✅ (Drools) | ✅ |
| External Task pattern | ✅ REST + long-polling | ✅ (gRPC/Zeebe) | ❌ (embedded) | Partial |
| Multi-tenancy native | ✅ Tenant Markers | ❌ (multi-region = cost) | ❌ | Partial |
| REST API | ✅ (OpenAPI 3.0, 200+ endpoints) | Partial (Operate API) | ❌ | ✅ |
| Camunda 7 compatibility | ✅ 100% drop-in | ❌ (rewrite required) | ❌ | ❌ |
| Python workers | ✅ (mature community client) | ✅ (pyzeebe) | ❌ | Partial |
| Data sovereignty | ✅ (self-hosted) | ❌ (Camunda Cloud) | ✅ | ✅ |

CIB Seven is a permanent, community-backed fork of Camunda 7.24 maintained by CIB group (Germany), with 1,000+ enterprise users including Atruvia AG (banking). It is a drop-in replacement for Camunda 7, reuses existing BPMN/DMN models, and provides an automated Java package migration tool (`org.camunda` → `org.cibseven`).

## Decision

We will use **CIB Seven 2.1.3** as the sole BPM orchestration engine for the platform.

- Deployed as a Spring Boot application in Docker on Kubernetes (EKS).
- Treated as a **configured black box**: no custom Java delegates, no embedded business logic. All business logic executes in external Python workers via REST API.
- CIB ins7ght (Enterprise) licensed at R$60,000/year for process analytics and BPMN heatmap capabilities.
- Engine version pinned to 2.1.3 in production; upgrades evaluated quarterly against CIB public roadmap (next milestone: Web Modeler OSS, AI Agents, October 2026).

## Consequences

**Positive:**

- Zero licensing cost saves R$2.7M–4.6M/year compared to Camunda 8.
- Full compatibility with Camunda 7 ecosystem — largest BPM knowledge base, community connectors, proven patterns.
- External Task pattern decouples engine from worker technology, leveraging the existing Python team (4 devs) without Java expertise for business logic.
- Data sovereignty maintained — all process data stays in our PostgreSQL on AWS within Brazil (LGPD).

**Negative:**

- CIB Seven is maintained by a single company. If CIB discontinues, we must self-maintain the fork. *Mitigation:* Apache 2.0 code, 1,000+ enterprise community, well-understood Camunda 7 codebase.
- Minimum one Java-capable engineer required for engine upgrades and Spring Boot configuration.
- Future divergence from Camunda 7 ecosystem possible. *Mitigation:* workers communicate via REST API only, which CIB commits to backward-compatible.
