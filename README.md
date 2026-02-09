**Hospital Digital Orchestration** — CIB Seven · BPMN/DMN ·

---

## What is this?

A BPM-based orchestration platform that serves as the **digital nervous system** for AUSTA hospital operations. It coordinates the **entire hospital** across four operational domains and five patient journeys — from first contact to post-discharge follow-up, from admission to payment reconciliation.

The platform replaces fragmented, department-siloed workflows with **orchestrated journeys** that accompany the patient through the complete care and billing lifecycle, connecting clinical, administrative, and financial systems through automated BPMN processes and a centralized decision rules engine (DMN).

> *"Se o paciente precisa nos procurar para saber o que acontece com ele, já falhamos em antecipar sua necessidade."*  
> — Hospital Digital Manifesto, AUSTA

### Scope Boundary

This platform orchestrates **hospital operations only**. The AUSTA Saúde healthcare plan (operadora) will have a separate, similar orchestration platform. Payers (Bradesco, Unimed, SulAmérica, Amil, AUSTA Saúde, etc.) are external entities the hospitals bill — they are not tenants of this platform.

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────┐
│  Channels: WhatsApp · Portal · Cockpit · Grafana        │
├─────────────────────────────────────────────────────────┤
│  Orchestration: CIB Seven 2.1.3 (BPMN · DMN · CMMN)    │
│  Single Engine · Multi-Tenant · External Task Pattern    │
├─────────────────────────────────────────────────────────┤
│  Workers: Python 3.12 External Tasks (stateless, HPA)   │
│  eligibility · tiss · denial · whatsapp · clinical · …  │
├─────────────────────────────────────────────────────────┤
│  Intelligence: OmniCash AI/ML Layer                      │
│  denial prediction · code optimization · AR forecasting  │
├─────────────────────────────────────────────────────────┤
│  Integration: Debezium CDC · Kafka 3.7 · Mirth 4.5.2    │
│  HAPI FHIR R4 7.4.0 · Tasy Adapter · MV Soul Adapter   │
├─────────────────────────────────────────────────────────┤
│  Data: PostgreSQL 16 · Redis 7.2 · Elasticsearch 8.13   │
├─────────────────────────────────────────────────────────┤
│  Infra: EKS · Keycloak 24 · Prometheus · Grafana 11     │
└─────────────────────────────────────────────────────────┘
```

## Hospital Digital Model

### 5 Patient Journeys (cross-cutting, orchestrated)

1. **Jornada de Acesso** — From first contact to patient prepared for care
2. **Jornada de Cuidado** — From admission to discharge with documented outcomes
3. **Jornada de Continuidade** — From post-discharge to stabilization (home care, ambulatory follow-up)
4. **Jornada de Relacionamento** — From first interaction to loyalty (patient and physician)
5. **Jornada Financeira** — From eligibility verification to complete payment

### 4 Operational Domains (29 subprocesses)

| Domain | Subprocesses | Phase |
|---|---|---|
| **Acesso Digital e Experiência** | 6 (demand capture, scheduling, identity, clearance, intake, check-in) | 2–3 |
| **Operações Clínicas e Cuidado** | 8 (triage, admission, care team, prescriptions, diagnostics, medications, surgery, discharge) | 2–3 |
| **Ciclo de Receita e Contratação** | 8 (charge capture, documentation, coding, denial management, patient billing, payer contracts, revenue optimization, VBHC) | **1 (MVP)** |
| **Plataforma, Supply Chain e Risco** | 7 (workforce, supply chain, facilities, clinical risk, data platform, cybersecurity, automation ops) | 3–4 |

## Key Numbers

| Metric | Value |
|---|---|
| Hospital tenants | 4 (austa-hospital, amh-sp-morumbi, amh-rj-barra, amh-mg-bh) |
| External payers | Multiple (Bradesco, Unimed, SulAmérica, Amil, AUSTA Saúde, etc.) |
| Total subprocesses | 29 across 4 domains |
| BPMN processes (Phase 1) | 1 main + 10 sub-processes (revenue cycle) |
| DMN decision tables | Global + per-tenant overrides, payer rules as input parameters |
| Workers | 6+ Python External Task workers (growing per domain) |
| Licensing cost | R$ 0 (CIB Seven Apache 2.0) |
| Year 1 budget | R$ 1.3–1.5M |

## Quick Start (Local Development)

### Prerequisites

- Docker Desktop with 8GB+ RAM allocated
- Python 3.12+
- Node.js 18+ (engine config tooling only)
- Git

### 1. Clone and start infrastructure

```bash
git clone git@github.com:austa/austa-orchestration-platform.git
cd austa-orchestration-platform
docker compose up -d
```

This starts: CIB Seven engine, PostgreSQL, Kafka (KRaft), Redis, HAPI FHIR, Mirth Connect, Keycloak, Prometheus, Grafana.

### 2. Verify engine is running

```bash
curl http://localhost:8080/engine-rest/engine
# Expected: [{"name":"default"}]
```

### 3. Deploy BPMN and DMN

```bash
./scripts/deploy-processes.sh local
# Deploys all BPMN/DMN from /bpmn and /dmn/global to the engine
```

### 4. Start a worker (example: eligibility)

```bash
cd workers/worker-eligibility
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
# Worker connects to engine, subscribes to 'verify-eligibility' topic
```

### 5. Start a test process

```bash
curl -X POST http://localhost:8080/engine-rest/process-definition/key/revenue-cycle-main/tenant-id/austa-hospital/start \
  -H "Content-Type: application/json" \
  -d '{"variables": {"encounterFhirId": {"value": "Encounter/test-001", "type": "String"}}}'
```

### 6. Monitor

| Service | URL |
|---|---|
| CIB Seven Cockpit | http://localhost:8080/cibseven/app/cockpit |
| CIB Seven Tasklist | http://localhost:8080/cibseven/app/tasklist |
| Grafana | http://localhost:3000 (admin/admin) |
| Kafka UI | http://localhost:8081 |
| HAPI FHIR | http://localhost:8082/fhir/metadata |
| Keycloak | http://localhost:8180/admin (admin/admin) |
| Prometheus | http://localhost:9090 |

## Repository Structure

```
/
├── bpmn/                      # Executable BPMN process models
├── dmn/                       # DMN decision tables (global + tenant overrides)
├── workers/                   # Python External Task workers
│   ├── worker-base/           # Shared AustaWorker framework
│   ├── worker-eligibility/
│   ├── worker-tiss/
│   ├── worker-denial/
│   ├── worker-whatsapp/
│   ├── worker-clinical/
│   └── worker-payment/
├── adapters/                  # ERP integration adapters
├── bridge/                    # CDC-to-BPM bridge service
├── engine/                    # CIB Seven Spring Boot configuration
├── infra/                     # Infrastructure-as-Code
├── tests/                     # E2E and load tests
├── scripts/                   # Deployment, bootstrap, utilities
├── docs/                      # All documentation
│   ├── adr/                   # Architecture Decision Records
│   ├── specs/                 # Technical specifications
│   ├── guides/                # Development and operations guides
│   └── runbooks/              # Incident response procedures
├── docker-compose.yml
├── CODEOWNERS
└── README.md                  # ← You are here
```

See [docs/guides/repository-structure.md](docs/guides/repository-structure.md) for detailed folder descriptions.

## Documentation Index

### Architecture

| Document | Description |
|---|---|
| [docs/specs/technical-specification.md](docs/specs/technical-specification.md) | Consolidated technical specification (single source of truth) |
| [docs/adr/](docs/adr/) | 12 Architecture Decision Records |

### Development

| Document | Description |
|---|---|
| [docs/guides/development-standards.md](docs/guides/development-standards.md) | Code style, Git conventions, BPMN/DMN naming, PR rules |
| [docs/guides/repository-structure.md](docs/guides/repository-structure.md) | Mono-repo layout, CODEOWNERS, CI/CD path filtering |

### Operations

| Document | Description |
|---|---|
| docs/runbooks/ | Incident response procedures (TBD) |
| docs/specs/api-contracts.md | OpenAPI specs and event schemas (TBD) |
| docs/specs/data-dictionary.md | Process variables, Kafka topics, FHIR profiles (TBD) |

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Orchestration | CIB Seven | 2.1.3 |
| Workers | Python | 3.12 |
| External Task Client | camunda-external-task-client-python3 | 4.5.0 |
| FHIR Server | HAPI FHIR R4 (JPA) | 7.4.0 |
| Integration Engine | Mirth Connect | 4.5.2 |
| CDC | Debezium | 2.7 |
| Event Streaming | Apache Kafka (KRaft) | 3.7 |
| Database | PostgreSQL | 16 |
| Cache | Redis (Sentinel) | 7.2 |
| Search | Elasticsearch | 8.13 |
| Identity | Keycloak | 24 |
| Metrics | Prometheus | 2.51 |
| Dashboards | Grafana | 11 |
| Process Analytics | CIB ins7ght | Enterprise |
| Container Orchestration | AWS EKS | Latest |
| IaC | Terraform/OpenTofu | 1.7+ |

## License

- **CIB Seven Engine:** Apache License 2.0
- **Platform Code:** Proprietary — Grupo AUSTA / AMH. All rights reserved.

## Contact

- **Architecture:** architecture@austa.com.br
- **DevOps:** devops@austa.com.br
- **Project Lead:** TBD
