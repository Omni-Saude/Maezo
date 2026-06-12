# Consolidated Technical Specification

**Version:** 1.1  
**Date:** February 2026  
**Status:** Approved  
**Classification:** Confidential — Internal Use  
**Supersedes:** `AUSTA-CIBSeven-Platform-Technical-Document.md` (v1.0) and `Plataforma de Orquestração de Processos Hospitalares – Arquitetura CIB Seven.docx` (v1.0)

> This document is the **single source of truth** for the AUSTA Hospital Orchestration Platform architecture. It was created by reconciling two prior architecture documents, resolving all divergences, and aligning with the Hospital Digital Manifesto and Hospital do Futuro revenue cycle vision.

---

## 1. Problem Statement

The Grupo AUSTA hospital network operates critical processes — billing, authorization, clinical alerts, patient access, supply chain, clinical operations — in a fragmented manner across multiple units and ERPs. Each unit (Hospital AUSTA on Tasy, AMH units on MV Soul) runs its own workflows with ad-hoc integrations, manual handoffs, and department-siloed processes.

**Consequences of fragmentation:**

- Glosa (denial) rates of 8–12% due to coding errors and missed authorization windows
- Billing cycles of 45+ days (target: <24 hours account closure per Hospital do Futuro vision)
- Sepsis detection relying on manual observation (>60 min to alert)
- No SLA visibility for authorization or clinical response times
- LGPD and ANS compliance difficult without centralized audit trail
- Patient experience fragmented across disconnected departmental touchpoints
- Only 30% task automation (target: 90%)
- Coding precision at 85% (target: 99.5%)

### Scope Boundary

This platform orchestrates **hospital operations only**. The AUSTA Saúde healthcare plan (operadora) will operate a **separate** orchestration platform — similar in architecture but independent in deployment, data, and processes. Payers (Bradesco, Unimed, SulAmérica, Amil, AUSTA Saúde, etc.) are external entities the hospitals bill; they are referenced in DMN decision tables and operator portal integrations but are not tenants of this platform.

## 2. Solution Overview

Deploy CIB Seven 2.1.3 as the central orchestration engine — the **"sistema nervoso operacional"** — coordinating the entire hospital digital operation across four operational domains, five patient journeys, and 29 subprocesses, spanning all hospital units via multi-tenant federation.

### 2.1 The Hospital Digital Model

The platform implements the Hospital Digital Manifesto's vision of replacing departmental silos with **orchestrated patient journeys** that cross all operational boundaries.

**5 Patient Journeys (cross-cutting):**

| Journey | Description | From → To |
|---|---|---|
| **Jornada de Acesso** | First contact to patient prepared for care | Demand capture → Check-in complete |
| **Jornada de Cuidado** | Admission to discharge with documented outcomes | Triage → Discharge + documentation |
| **Jornada de Continuidade** | Post-discharge to stabilization | Home care handoff → Ambulatory follow-up |
| **Jornada de Relacionamento** | First interaction to loyalty | First contact → Retention (patient + physician) |
| **Jornada Financeira** | Eligibility to payment reconciliation | Clearance → Payment posting |

**4 Operational Domains (29 subprocesses):**

| # | Domain | Subprocess | Phase |
|---|---|---|---|
| | **Acesso Digital e Experiência** | | |
| 1 | | Capturar Demanda e Qualificar Acesso | 2 |
| 2 | | Orquestrar Agendamento e Capacidade | 2 |
| 3 | | Verificar Identidade e Registrar Paciente | 2 |
| 4 | | Executar Clearance Financeiro e Estimativas | 1 |
| 5 | | Executar Intake Digital Pré-Atendimento | 2 |
| 6 | | Executar Check-in e Gerenciar Fluxo | 2 |
| | **Operações Clínicas e Cuidado** | | |
| 7 | | Executar Triagem e Roteamento Clínico | 3 |
| 8 | | Gerenciar Admissão e Alocação de Leitos | 3 |
| 9 | | Orquestrar Equipe de Cuidado e Tarefas | 3 |
| 10 | | Processar Prescrições e Suporte à Decisão | 3 |
| 11 | | Gerenciar Diagnósticos e Resultados | 3 |
| 12 | | Executar Gestão de Medicamentos | 3 |
| 13 | | Coordenar Serviços Cirúrgicos | 3 |
| 14 | | Executar Alta e Transição do Cuidado | 2 |
| | **Ciclo de Receita e Contratação** | | |
| 15 | | Capturar Consumo e Produção Assistencial | **1** |
| 16 | | Garantir Integridade Documentação Clínica | **1** |
| 17 | | Executar Codificação e Faturamento | **1** |
| 18 | | Prevenir e Gerenciar Glosas | **1** |
| 19 | | Executar Cobrança ao Paciente | 2 |
| 20 | | Gerenciar Contratos e Performance Pagadores | 2 |
| 21 | | Analisar Receita e Otimizar Margem | 2 |
| 22 | | Gerenciar Desfechos e Performance VBHC | 3 |
| | **Plataforma, Supply Chain e Risco** | | |
| 23 | | Gerenciar Força de Trabalho e Escalas | 3 |
| 24 | | Automatizar Supply Chain e Inventário | 3 |
| 25 | | Manter Equipamentos e Instalações | 4 |
| 26 | | Gerenciar Risco Clínico e Segurança | 3 |
| 27 | | Operar Plataforma de Dados | 4 |
| 28 | | Proteger Dados e Cibersegurança | 4 |
| 29 | | Orquestrar Automação e Operações de IA | 4 |

### 2.2 Design Principles

| Principle | Implementation |
|---|---|
| Engine as black box | No Java business logic. All logic in Python External Task workers. (ADR-001, ADR-003) |
| Multi-tenant federation | Single engine, shared DB, tenant markers per hospital unit. Global BPMN/DMN with local overrides. (ADR-002, ADR-007) |
| ERP decoupling | CDC captures events; FHIR normalizes data. Workers never query ERPs directly. (ADR-004, ADR-005) |
| Workers single-responsibility | Each worker handles one topic. No Kafka consumption. REST-only. (ADR-003, ADR-006) |
| Data minimization | Process variables store FHIR references, not PII. History TTL enforced. (ADR-011) |
| Anticipation over reaction | System identifies needs before patient articulates them. Predictive models trigger proactive actions. (Manifesto Principle 1) |
| Persistent context | Every interaction inherits complete context from all prior interactions. Patient never repeats information. (Manifesto Principle 2) |

### 2.3 10-Stage Revenue Cycle (Hospital do Futuro)

The revenue cycle domain follows the Hospital do Futuro 10-stage model, each stage becoming an orchestrated BPMN process:

1. **Primeiro Contato e Agendamento** — WhatsApp/Portal capture, CRM integration, auto-scheduling
2. **Pré-Atendimento** — Eligibility verification, pre-authorization, intake digital, clearance financeiro
3. **Atendimento Clínico** — Triage, clinical documentation feeding billing in real-time
4. **Produção Clínica** — IoT/RFID charge capture, prescription tracking, automatic procedure logging
5. **Codificação e Auditoria** — AI-assisted coding (CID-10, CBHPM, TUSS), documentation audit
6. **Faturamento e Submissão** — TISS 4.01 XML generation, batch submission, protocol tracking
7. **Gestão de Glosas** — AI denial analysis, auto-contestation, priority scoring, recovery tracking
8. **Arrecadação** — Payment matching, automatic posting, variance analysis, aging management
9. **Analytics e Inteligência** — OmniCash dashboards, denial prediction, revenue forecasting
10. **Maximização** — VBHC contract optimization, process mining, continuous improvement

---

## 3. Component Architecture

### 3.1 Technology Stack (Canonical Versions)

| Layer | Component | Technology | Version | ADR |
|---|---|---|---|---|
| Orchestration | BPM Engine | CIB Seven | 2.1.3 | ADR-001 |
| Orchestration | Process Analytics | CIB ins7ght | Enterprise | ADR-010 |
| Workers | Runtime | Python | 3.12 | ADR-003 |
| Workers | External Task Client | camunda-external-task-client-python3 | 4.5.0 | ADR-003 |
| Decisions | DMN Engine | CIB Seven native | FEEL 1.3 | ADR-007 |
| Integration | FHIR Server | HAPI FHIR R4 (JPA) | **7.4.0** | ADR-005 |
| Integration | HL7 Engine | Mirth Connect | **4.5.2** | — |
| Integration | CDC | Debezium | 2.7 | ADR-004 |
| Events | Streaming | Apache Kafka (KRaft) | 3.7 | ADR-006 |
| Data | Process DB | PostgreSQL | 16 | — |
| Data | Cache | Redis (Sentinel) | 7.2 | — |
| Data | Search | Elasticsearch | 8.13 | ADR-010 |
| Security | Auth | Basic Auth (CIB Seven) | — | ADR-020 |
| Monitoring | Metrics | Prometheus | 2.51 | ADR-010 |
| Monitoring | Dashboards | Grafana | 11 | ADR-010 |
| Infrastructure | Container Orchestration | AWS EKS | Latest | ADR-012 |
| Infrastructure | IaC | Terraform/OpenTofu | 1.7+ | ADR-009 |

### 3.2 Multi-Tenant Model

**Strategy:** Tenant Markers — single engine, shared database (ADR-002)

**Tenants (hospital units only):**

| Tenant ID | Unit | ERP | Location |
|---|---|---|---|
| `austa-hospital` | Hospital AUSTA | Philips Tasy (Oracle) | São José do Rio Preto, SP |
| `amh-sp-morumbi` | AMH São Paulo | MV Soul (PostgreSQL) | São Paulo, SP |
| `amh-rj-barra` | AMH Rio de Janeiro | MV Soul (PostgreSQL) | Rio de Janeiro, RJ |
| `amh-mg-bh` | AMH Belo Horizonte | MV Soul (Oracle) | Belo Horizonte, MG |

**External payers (not tenants — referenced in DMN tables and integrations):**

Bradesco Saúde, Unimed (regional federations), SulAmérica, Amil, AUSTA Saúde, Porto Seguro, NotreDame Intermédica, and others per hospital unit contracts.

**DMN Federation** (ADR-007):

```
Resolution order:
1. Check deployment with tenantId = {current hospital unit}
2. If not found → fall back to deployment without tenantId (global)

Payer-specific logic:
→ Handled via input parameter 'payerId' within DMN tables, NOT via tenant deployments
```

### 3.3 Engine Configuration

**Replicas:** 1 in Phase 1, 2 in Phase 2 (ADR-012)

Key engine settings:

```yaml
cibseven:
  bpm:
    database:
      type: postgres
      schema-update: true
    job-execution:
      enabled: true
      core-pool-size: 6
      max-pool-size: 12
      queue-capacity: 100
    history-cleanup:
      enabled: true
      batch-size: 100
      removal-time-strategy: end
    multi-tenancy:
      enabled: true
      default-tenant: austa-hospital
    external-task:
      lock-duration: 300000  # 5 minutes
      retry-timeout: 30000   # 30 seconds
```

### 3.4 Security Model (ADR-008)


---

## 4. Process Architecture

### 4.1 BPMN Process Inventory

**Phase 1 — Revenue Cycle (MVP):**

| Process ID | Name | Type | Scope |
|---|---|---|---|
| `revenue-cycle-main` | Revenue Cycle Orchestrator | Main (Call Activities) | All hospital units |
| `SP-RC-001` | Scheduling & Registration | Sub-process | All hospital units |
| `SP-RC-002` | Pre-Service (Eligibility + Authorization) | Sub-process | All hospital units |
| `SP-RC-003` | Clinical Service (documentation triggers) | Sub-process | All hospital units |
| `SP-RC-004` | Clinical Production (charge capture) | Sub-process | All hospital units |
| `SP-RC-005` | Coding & Audit | Sub-process | All hospital units |
| `SP-RC-006` | Billing & Submission (TISS) | Sub-process | All hospital units |
| `SP-RC-007` | Denial Management | Sub-process | All hospital units |
| `SP-RC-008` | Revenue Collection (payment reconciliation) | Sub-process | All hospital units |
| `SP-RC-009` | Analytics & Intelligence | Sub-process | All hospital units |
| `SP-RC-010` | Maximization (VBHC, optimization) | Sub-process | All hospital units |

**Phase 2 — Access + Discharge:**

| Process ID | Name | Type | Scope |
|---|---|---|---|
| `patient-access-main` | Patient Access Orchestrator | Main | All hospital units |
| `SP-PA-001` | Demand Capture & Qualification | Sub-process | All hospital units |
| `SP-PA-002` | Scheduling & Capacity | Sub-process | All hospital units |
| `SP-PA-003` | Identity Verification & Registration | Sub-process | All hospital units |
| `SP-PA-004` | Financial Clearance & Estimates | Sub-process | All hospital units |
| `SP-PA-005` | Digital Intake | Sub-process | All hospital units |
| `SP-PA-006` | Check-in & Flow Management | Sub-process | All hospital units |
| `SP-DI-001` | Discharge & Care Transition | Sub-process | Hospital tenants |
| `SP-PX-001` | Post-Discharge Follow-up | Sub-process | Hospital tenants |
| `SP-PX-002` | NPS Collection | Sub-process | All hospital units |

**Phase 3 — Clinical Operations + Alerts:**

| Process ID | Name | Type | Scope |
|---|---|---|---|
| `clinical-ops-main` | Clinical Operations Orchestrator | Main | Hospital tenants |
| `SP-CO-001` | Triage & Clinical Routing | Sub-process | Hospital tenants |
| `SP-CO-002` | Admission & Bed Management | Sub-process | Hospital tenants |
| `SP-CO-003` | Care Team Orchestration | Sub-process | Hospital tenants |
| `SP-CO-004` | Prescriptions & Clinical Decision Support | Sub-process | Hospital tenants |
| `SP-CO-005` | Diagnostics & Results | Sub-process | Hospital tenants |
| `SP-CO-006` | Medication Management | Sub-process | Hospital tenants |
| `SP-CO-007` | Surgical Services Coordination | Sub-process | Hospital tenants |
| `clinical-alerts-main` | Clinical Alert Orchestrator | Main | Hospital tenants |
| `SP-CA-001` | Sepsis Detection (qSOFA/SOFA) | Sub-process | Hospital tenants |
| `SP-CA-002` | NEWS2 Early Warning | Sub-process | Hospital tenants |

### 4.2 External Task Topic Registry (Phase 1)

| Topic | Worker | Input Variables | Output Variables | SLA |
|---|---|---|---|---|
| `verify-eligibility` | worker-eligibility | `coverageFhirId`, `procedureCodes`, `payerId` | `eligibilityResult`, `eligibilityDetails` | 10s |
| `request-authorization` | worker-eligibility | `encounterFhirId`, `procedureCodes`, `payerId` | `authorizationNumber`, `authorizationStatus` | 30s |
| `capture-charges` | worker-production | `encounterFhirId`, `iotEventIds` | `billingItems`, `captureCompleteness` | 15s |
| `generate-tiss` | worker-tiss | `encounterFhirId`, `billingItems`, `payerId` | `tissXml`, `tissHash`, `tissValidationErrors` | 15s |
| `submit-tiss` | worker-tiss | `tissXml`, `operatorPortalId` | `submissionProtocol`, `submissionTimestamp` | 60s |
| `analyze-denial` | worker-denial | `denialCode`, `denialReason`, `claimFhirId` | `contestationText`, `contestationPriority`, `recoveryProbability` | 30s |
| `reconcile-payment` | worker-payment | `paymentBatchId`, `expectedAmount` | `reconciliationStatus`, `varianceAmount` | 30s |
| `evaluate-qsofa` | worker-clinical | `patientFhirId`, `vitalSigns` | `qsofaScore`, `sepsisAlert` | 5s |
| `send-whatsapp` | worker-whatsapp | `patientPhone`, `templateId`, `templateParams` | `messageId`, `deliveryStatus` | 10s |

### 4.3 DMN Decision Tables

| DMN ID | Name | Scope | Hit Policy | Key Inputs |
|---|---|---|---|---|
| `DMN-RC-001` | Eligibility Rules | Global + tenant overrides | FIRST | payerId, carência, network status, contract status |
| `DMN-RC-002` | Authorization Flow Routing | Global + tenant overrides | FIRST | procedure type, cost threshold, payerId |
| `DMN-RC-003` | Denial Analysis & Contestation | Global + tenant overrides | COLLECT | denial code, payerId, historical recovery rate |
| `DMN-RC-004` | TISS Validation Rules | Global | FIRST | ANS version, procedure code, material code |
| `DMN-RC-005` | Coding Optimization (AI-assisted) | Global | FIRST | diagnosis, procedures, documentation completeness |
| `DMN-CA-001` | Sepsis Protocol Thresholds | Global | FIRST | qSOFA components, patient age, comorbidities |
| `DMN-CA-002` | NEWS2 Escalation Matrix | Global | FIRST | NEWS2 total, individual parameter scores |

### 4.4 Timer Events (SLA Enforcement)

| Process | Timer | Duration | Action on Expiry |
|---|---|---|---|
| SP-RC-002 (Authorization) | Boundary Interrupting | 48 hours | Escalate to supervisor; send WhatsApp update |
| SP-RC-006 (TISS Generation) | Boundary Non-Interrupting | 24 hours | Alert billing team via Cockpit incident |
| SP-RC-007 (Denial Contestation) | Boundary Interrupting | 5 business days | Auto-submit contestation with generated text |
| SP-CA-001 (Sepsis) | Boundary Interrupting | 5 minutes | Escalate to chief intensivist + administrator |
| SP-RC-004 (Account Closure) | Boundary Non-Interrupting | 24 hours post-discharge | Alert: account must close within 24h target |

---

## 5. Integration Architecture

### 5.1 CDC Pipeline (ADR-004, ADR-006)

```
ERP Database (Hospital)
    │
    ▼ (Transaction Log)
Debezium Connector
    │
    ▼ (CDC Events)
Apache Kafka
    │
    ▼ (Consumer)
cdc-to-bpm-bridge (Python)
    │
    ▼ (REST API)
CIB Seven Engine → starts/correlates process instances
```

**Kafka Topic Design:**

| Topic | Source | Partitions | Retention |
|---|---|---|---|
| `tasy.AUSTA.ATENDIMENTO` | Debezium Oracle | 3 | 7 days |
| `tasy.AUSTA.CONTA_MEDICA` | Debezium Oracle | 3 | 7 days |
| `tasy.AUSTA.ITEM_CONTA` | Debezium Oracle | 6 | 7 days |
| `tasy.AUSTA.SINAL_VITAL` | Debezium Oracle | 3 | 3 days |
| `tasy.AUSTA.PRESCRICAO` | Debezium Oracle | 3 | 7 days |
| `mv.{tenant}.ATENDIME` | Debezium PostgreSQL | 3 | 7 days |
| `mv.{tenant}.ITREG_FAT` | Debezium PostgreSQL | 6 | 7 days |
| `mv.{tenant}.REGISTRO_ALTA` | Debezium PostgreSQL | 3 | 7 days |
| `mirth.fhir.observations` | Mirth Connect | 3 | 3 days |
| `bpm.audit.events` | CIB Seven | 3 | 30 days |
| `bridge.dead-letter` | Bridge (failures) | 1 | 30 days |

### 5.2 FHIR Data Model (ADR-005)

| FHIR Resource | Purpose | Tasy Source | MV Soul Source |
|---|---|---|---|
| `Patient` | Demographics, identifiers | `PACIENTE` | `PACIENTE` |
| `Coverage` | Insurance, eligibility, payer | `CONVENIO_PACIENTE` | `CONVENIO_PAC` |
| `Encounter` | Admission, visit context | `ATENDIMENTO` | `ATENDIME` |
| `Observation` | Vital signs, lab results | `SINAL_VITAL`, `EXAME` | `SINAL_VITAL`, `RESULTADO_EXAME` |
| `Claim` | Billing, TISS representation | `CONTA_MEDICA` + `ITEM_CONTA` | `ITREG_FAT` |
| `ClaimResponse` | Payer response, denials | `GLOSA` | `GLOSA_CONV` |
| `Practitioner` | Physicians, nurses | `PROFISSIONAL` | `PRESTADOR` |
| `Location` | Rooms, beds, surgical suites | `UNIDADE` | `UNIDADE_INT` |
| `MedicationRequest` | Prescriptions | `PRESCRICAO` | `PRESCRICAO` |

---

## 6. Infrastructure

### 6.1 Kubernetes Topology (ADR-009, ADR-012)

```
EKS Cluster
├── Namespace: orchestration
│   ├── cibseven-engine (1 replica Phase 1, 2 Phase 2)
│   ├── cibseven-cockpit
│   └── cibseven-tasklist
├── Namespace: workers
│   ├── worker-eligibility (HPA: 1–4 replicas)
│   ├── worker-tiss (HPA: 1–3 replicas)
│   ├── worker-denial (HPA: 1–2 replicas)
│   ├── worker-whatsapp (HPA: 1–2 replicas)
│   ├── worker-clinical (HPA: 1–3 replicas)
│   ├── worker-payment (HPA: 1–2 replicas)
│   └── worker-production (HPA: 1–3 replicas)
├── Namespace: integration
│   ├── cdc-to-bpm-bridge (2 replicas)
│   ├── mirth-connect
│   ├── debezium-connect
│   └── hapi-fhir
├── Namespace: data
│   ├── kafka (KRaft, 3 brokers)
│   ├── redis-sentinel (3 nodes)
│   └── elasticsearch (3 nodes)
└── Namespace: monitoring
    ├── prometheus
    ├── grafana
    ├── alertmanager
    ├── fluentd
    └── kibana
```

PostgreSQL 16 runs as AWS RDS (Multi-AZ) outside the cluster.

### 6.2 Environment Matrix

| Environment | Infrastructure | Engine Replicas | Data | Purpose |
|---|---|---|---|---|
| `local` | Docker Compose | 1 | Ephemeral | Developer workstation |
| `dev` | EKS (shared) | 1 | Persistent, synthetic | Integration testing |
| `staging` | EKS (isolated) | 2 | Persistent, anonymized prod copy | Pre-production validation |
| `prod` | EKS (HA) | 2 | Production | Live operations |

---

## 7. LGPD and Compliance (ADR-011)

### 7.1 Data Handling Rules

| Rule | Implementation |
|---|---|
| No PII in process variables | Variables store FHIR resource IDs only (`Patient/12345`, not `João Silva`) |
| History TTL (default) | 180 days for completed process instances |
| History TTL (revenue cycle) | 2,190 days (6 years) — ANS requirement |
| History TTL (clinical alerts) | 365 days |
| Encryption at rest | PostgreSQL TDE |
| Encryption in transit | TLS 1.3 on all endpoints |
| Access audit | pgaudit extension on PostgreSQL |
| PII validation | AustaWorker rejects known PII patterns (CPF, email) before task completion |
| ONA Nível 3 compliance | New digital flows designed adherent to ONA standards; quarterly internal audits |

---

## 8. KPIs and Success Criteria

### 8.1 Revenue Cycle KPIs (Phase 1 — Hospital do Futuro targets)

| KPI | Current Baseline | Target (12 months) | Hospital do Futuro Target | Measurement |
|---|---|---|---|---|
| Account closure time | 5–7 days | < 48 hours | < 24 hours | Discharge → Account closed |
| Task automation rate | 30% | 70% | 90% | Automated tasks / Total tasks |
| Glosa (denial) rate | 8–12% | < 4% | < 3% | Value denied / Value billed |
| Average days to payment | 90 days | < 50 days | < 45 days | Billing → Payment received |
| Accounts without manual intervention | 20% | 60% | 80% | Auto-processed / Total |
| Coding precision | 85% | 95% | 99.5% | Correct codes / Total coded |
| Denial reversal rate | 40% | 60% | 75% | Reversed / Total denied |
| Financial posting | D+3 | D+1 | D+0 (same day) | Service → Posted |

### 8.2 Clinical and Operational KPIs (Phase 2–3)

| KPI | Target | Measurement |
|---|---|---|
| Sepsis detection time | < 5 min | CDC event → Notification |
| Authorization SLA (within 48h) | > 95% | BPMN timer events |
| Surgical start-on-time rate | 95% | Scheduled vs. actual start |
| 30-day readmission rate | < 5% | Readmissions / Discharges |
| Digital self-resolution (access) | 85% | Auto-resolved / Total access requests |
| Post-discharge NPS response rate | > 40% | Responses / Discharges |
| Platform availability | 99.5% | CIB Seven + critical workers uptime |

---

## 9. Implementation Phases

### Phase 1 — Foundation + Revenue Cycle MVP (Weeks 1–16)

- EKS cluster, PostgreSQL, Kafka, Redis, Elasticsearch provisioned
- CIB Seven engine deployed (1 replica), Basic Auth configurado
- AustaWorker Python base framework published
- Docker Compose for local development; CI/CD pipelines operational
- Revenue cycle main process + 10 sub-processes (10-stage model) deployed
- 6+ Python workers implemented (eligibility, TISS, denial, payment, production, clinical)
- Debezium CDC configured for Tasy (initial tables: ATENDIMENTO, CONTA_MEDICA, ITEM_CONTA, PRESCRICAO, SINAL_VITAL)
- HAPI FHIR populated via Tasy adapters
- Single payer pilot (Bradesco Saúde) in **shadow mode** (2 weeks parallel with manual processes)
- Go-live revenue cycle for `austa-hospital` tenant

### Phase 2 — Access + Discharge + Scale (Weeks 17–28)

- Patient Access orchestrator + 6 sub-processes deployed
- Discharge & Care Transition process deployed
- All major payers onboarded in DMN rules (Unimed, SulAmérica, Amil)
- MV Soul CDC integration for AMH hospital units
- Engine scaled to 2 replicas (ADR-012)
- Patient experience processes (WhatsApp follow-up, NPS)
- Cross-tenant analytics via ins7ght
- OmniCash denial prediction model (Phase 1 ML)

### Phase 3 — Clinical Operations + Intelligence (Weeks 29–40)

- Clinical Operations orchestrator + 8 sub-processes deployed
- Clinical alerts (sepsis, NEWS2)
- Surgical services coordination
- OmniCash code optimization and AR forecasting
- VBHC outcomes management per payer contract
- CMMN case management for chronic/complex patients

### Phase 4 — Platform + Continuous Optimization (Weeks 41+)

- Platform domain processes (supply chain, workforce, clinical risk)
- IoT/RFID full integration for charge capture
- Process mining and continuous optimization
- Center of Excellence (CoE) established
- Preparation for JCI certification pathway

---

## 10. Team Composition

| Role | Count | Phase Allocation | Key Skills |
|---|---|---|---|
| Tech Lead / BPM Architect | 1 | 100% all phases | Camunda 7 expertise, Java + Python, BPMN/DMN |
| Java Developer | 1 | 50% Phase 1, 25% Phase 2+ | Spring Boot, CIB Seven config |
| Python Developer | 3–4 | 100% all phases | FastAPI, Python 3.12, async, ML basics |
| Integration Developer | 2 | 100% Phase 1–2, 50% Phase 3+ | Mirth Connect, FHIR, HL7, Debezium, CDC |
| Business Analyst | 2 | 100% all phases | BPMN/DMN modeling, hospital domain, billing expertise |
| DevOps / SRE | 1 | 100% Phase 1, 50% Phase 2+ | Kubernetes, Terraform, CI/CD, Prometheus |

### Year 1 Budget

| Item | Annual Cost | Notes |
|---|---|---|
| CIB Seven licensing | R$ 0 | Apache 2.0 |
| CIB ins7ght (Enterprise) | R$ 60,000 | Process analytics |
| AWS infrastructure (EKS) | R$ 216,000 | Engine, workers, RDS, MSK, caching |
| Team (~8.5 FTEs) | R$ 1,000,000–1,200,000 | Mix Jr–Sr, CLT + benefits |
| Training | R$ 35,000 | CIB Seven admin, BPMN/DMN for analysts |
| **Total Year 1** | **R$ 1,311,000–1,511,000** | |

**Comparison:** Camunda 8 SaaS alternative: R$ 3.89M–5.79M/year (licensing alone: R$ 2.7M–4.6M).

---

## 11. Risk Matrix

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| CIB Seven discontinued | Low | High | Apache 2.0 code, self-support possible. 1,000+ enterprise community. |
| Tasy CDC (Oracle LogMiner) blocked by DBA | Medium | High | Fallback to polling. Bridge abstracts event source. Early IT engagement. |
| HAPI FHIR performance at scale | Medium | Medium | Configurable indexes, Redis caching. Load test in Phase 1. |
| Worker team turnover | Medium | Medium | Python (widely available), AustaWorker framework reduces onboarding. |
| DMN rule drift between hospital units | Low | Medium | Quarterly analyst review. CI/CD generates DMN inventory matrix. |
| LGPD violation (PII in process variables) | Low | High | AustaWorker PII validator, CI static analysis, team training. |
| Payer portal integration failures (TISS) | High | Medium | Retry with backoff, manual fallback, dead-letter queue. |
| ONA Nível 3 compliance gaps from new flows | Low | High | Quarterly audits, ONA-adherent design reviews, change impact assessment. |

---

## 12. References

- [ADR Index](../adr/) — 12 Architecture Decision Records
- [Development Standards Guide](../guides/development-standards.md)
- [Repository Structure Guide](../guides/repository-structure.md)
- [Hospital Digital Manifesto](../../Manifesto_Hospital_Digital_AUSTA.docx) — 4 domains, 29 subprocesses, 5 journeys
- [Hospital do Futuro — Revenue Cycle Digital](../../Hospital_do_Futuro_Ciclo_Receita_Digital.docx) — 10-stage model
- [CIB Seven Documentation](https://docs.cibseven.org)
- [HAPI FHIR Documentation](https://hapifhir.io/hapi-fhir/docs/)
- [Debezium Documentation](https://debezium.io/documentation/)
- [ANS TISS Standards](https://www.gov.br/ans/pt-br/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-2013-tiss)
