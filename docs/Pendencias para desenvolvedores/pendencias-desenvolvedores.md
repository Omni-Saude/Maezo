# Pendências para Desenvolvedores

**Versão:** 1.3
**Data:** 17 de Fevereiro de 2026
**Última Atualização:** Production Deployment + BPMN Compliance + CI/CD Infrastructure + Generic Worker Framework
**Baseado em:** [Especificação Técnica Consolidada v1.1](../Technical%20specification/technical-specification.md)

> Tarefas que **não podem ser automatizadas por agentes de IA** e requerem trabalho manual de desenvolvedores humanos, DevOps, analistas de negócio ou stakeholders hospitalares.

---

## ✅ NOVO: Production Readiness & BPMN Compliance (2026-02-17)

### Session Summary: 8 Commits, 153 Files, +11,522/-1,546 Lines

**🚀 Production Deployment Infrastructure (PR #1)**

| Artefato | Localização | Linhas | Status |
|----------|-------------|--------|--------|
| **Production Helm Values** | `helm/maestro/values-prod.yaml` | 254 | ✅ READY |
| **Kubernetes Overlays** | `k8s/overlays/{staging,prod}/` | 131 | ✅ READY |
| **Smoke Test Suite** | `tests/smoke/` | 244 | ✅ 12 TESTS |
| **Operational Runbooks** | `docs/runbooks/` | 219 | ✅ DOCUMENTED |
| **Tenant Validator** | `scripts/validate_tenant_isolation.py` | 205 | ✅ VERIFIED |

**Key Production Configuration:**
- 2 CIB Seven replicas (ADR-012 Phase 2+)
- 4 tenants with PostgreSQL markers (ADR-002)
- 30-day Prometheus retention (ADR-010)
- Production domain: austa.com.br
- Full autoscaling + PodDisruptionBudgets

**📋 BPMN Compliance & Refactoring (PR #2)**

| Artefato | Localização | Impacto | Status |
|----------|-------------|---------|--------|
| **BPMN Consolidation** | `healthcare_platform/*/bpmn/` | -13 files, +6 consolidated | ✅ ADR-019 |
| **Worker Topic Fix** | `healthcare_platform/*/workers/` | 86 files standardized | ✅ ADR-016 |
| **Test Markers** | `tests/pytest.ini` | engine, bpmn markers | ✅ CONFIGURED |

**BPMN Changes:**
- Revenue Cycle: `SP-RC-008A/B` consolidated, `SP-RC-009` promoted to `SP-RC-011`
- Clinical Ops: `SP-PA-011/012` moved to `SP-CO-011/012`
- Main process: `revenue-cycle-main.bpmn` → `SP-RC-000_Revenue_Cycle_Main.bpmn`
- Templates: All updated with proper namespacing

**Topic Standardization (ADR-016):**
- Platform Services: `platform.services.*` → `platform.*`
- All workers validated against topic registry

**🔧 CI/CD Infrastructure (PR #3)**

| Artefato | Localização | Linhas | Status |
|----------|-------------|--------|--------|
| **BPMN Validation Workflow** | `.github/workflows/bpmn-validation.yml` | 145 | ✅ AUTOMATED |
| **Integration Test Workflow** | `.github/workflows/bpmn-integration-test.yml` | 86 | ✅ AUTOMATED |
| **Docker Compose Test** | `docker-compose.test.yml` | 175 | ✅ CONFIGURED |
| **Integration Tests** | `tests/integration/bpmn/` | 597 | ✅ 4 TEST SUITES |

**CI/CD Features:**
- XML + XSD validation
- BPMNDI coverage check
- Topic registry validation
- Worker connectivity validation
- Namespace compliance enforcement
- 4 integration test suites (deployment, namespace, instantiation, topic connectivity)

**🛠️ Tooling & Documentation (PR #4)**

| Artefato | Localização | Linhas | Status |
|----------|-------------|--------|--------|
| **Generic Worker Framework** | `healthcare_platform/shared/workers/generic/` | 2,086 | ✅ 8 ARCHETYPES |
| **BPMN Pre-commit Hook** | `scripts/bpmn_pre_commit_hook.sh` | 151 | ✅ ENFORCES ADR-019 |
| **BPMN Connectivity Validator** | `scripts/validate_bpmn_worker_connectivity.py` | 334 | ✅ VALIDATES TOPICS |
| **Surgery DMN Generator** | `scripts/generate_surgery_dmn.py` | 347 | ✅ AUTO-GENERATES |
| **Topic Registry** | `config/topic_registry.yaml` | 2,290 | ✅ 200+ TOPICS |
| **Generic Worker Tests** | `tests/unit/workers/generic/` | 3,183 | ✅ 10 TEST MODULES |
| **ADR Updates** | `docs/ADRs/` | 292 | ✅ 3 ADRs UPDATED |

**Generic Worker Framework:**
- 8 worker archetypes: AdminAdjudication, ClinicalAlert, ClinicalScore, ComplianceValidation, DataEnrichment, FinancialCalculation, OperationalRouting, BaseGeneric
- 100% topic registry validation
- DMN-driven logic delegation
- Automated worker discovery and instantiation
- Pipeline pattern support (linear, parallel, conditional)

**Validation Scripts:**
- BPMN pre-commit hook enforces: namespace compliance, topic registration, BPMNDI diagrams
- Connectivity validator ensures all topics have registered workers
- Surgery DMN generator creates decision tables from procedure catalogs

---

## ✅ ATUALIZADO: Artefatos Gerados pelo AI (Wave 3.7-6.1 — 2026-02-11)

### Session Summary: 8 Waves Completed, 45+ Files, ~8,300 Lines

| Wave | Artefato | Localização | Linhas | Status |
|------|----------|-------------|--------|--------|
| **3.7a** | Webhook Infrastructure | `healthcare_platform/shared/webhooks/` | 1,111 | ✅ VERIFIED |
| **3.7b** | FHIR Adapters (Claim, ClaimResponse, Observation, MedicationRequest) | `healthcare_platform/shared/integrations/tasy_adapters/` | 2,243 | ✅ VERIFIED |
| **3.7-INFRA** | Helm/K8s for Webhook & CDC Bridge | `helm/maezo/templates/` | 279+ | ✅ VERIFIED |
| **3.7c** | Webhook Handlers (5 handlers) | `healthcare_platform/shared/webhooks/handlers/` | 904 | ✅ VERIFIED |
| **3.8** | CDC-to-BPM Bridge Service | `healthcare_platform/shared/cdc_bridge/` | 719 | ✅ VERIFIED |
| **3.8.1** | CDC Bridge Unit Tests | `tests/unit/cdc_bridge/` | 738 | ✅ 35/35 PASSED |
| **3.9** | DMN Validation Tooling | `scripts/` | 632 | ✅ VERIFIED (85% FEEL coverage) |
| **6.1** | TASY Pharmacy Adapters + Tests | `healthcare_platform/shared/integrations/tasy_adapters/` | 1,663 | ✅ 12/12 PASSED |

### New Components Available:

| Componente | Localização | Descrição |
|------------|-------------|-----------|
| **Webhook Receiver Service** | `healthcare_platform/shared/webhooks/` | FastAPI async callback receiver (ADR-014) |
| **5 Webhook Handlers** | `healthcare_platform/shared/webhooks/handlers/` | tasy_regulatory, tasy_authorization, pix_payment, whatsapp_message, tiss_response |
| **CDC Bridge Service** | `healthcare_platform/shared/cdc_bridge/` | Kafka→CIB7 event transformer (ADR-004) |
| **4 New FHIR Adapters** | `healthcare_platform/shared/integrations/tasy_adapters/` | claim, claim_response, observation, medication_request |
| **3 Pharmacy Adapters** | `healthcare_platform/shared/integrations/tasy_adapters/` | medication_dispense, pharmacy_inventory, drug_interaction |
| **DMN Validation Scripts** | `scripts/` | validate_dmn.py, dmn_inventory.py, dmn_tenant_resolver.py |
| **Webhook K8s Deployment** | `helm/maezo/templates/webhook-receiver-*.yaml` | Deployment, Service, HPA |
| **CDC Bridge K8s Deployment** | `helm/maezo/templates/cdc-bridge-*.yaml` | Deployment, Service |

---

## ✅ ATUALIZADO: Artefatos Gerados pelo AI (Wave 0.5)

Os seguintes artefatos foram gerados e estão prontos para uso:

| Artefato | Localização | Descrição |
|----------|-------------|-----------|
| **Helm Chart** | `helm/maezo/` | Chart completo com CIB7, Workers, FHIR, Kafka, Redis, Keycloak |
| **Values Dev** | `helm/maezo/values-dev.yaml` | Configuração para ambiente de desenvolvimento |
| **Values Staging** | `helm/maezo/values-staging.yaml` | Configuração para staging |
| **K8s Namespace** | `k8s/base/namespace.yaml` | Namespace, RBAC, quotas, limits |
| **K8s Secrets** | `k8s/base/secrets.yaml` | Templates de secrets (SUBSTITUIR VALORES!) |
| **K8s NetworkPolicies** | `k8s/base/network-policies.yaml` | Zero-trust networking |
| **CI/CD Pipeline** | `.github/workflows/ci-cd.yaml` | GitHub Actions completo |
| **Dockerfile CDC Bridge** | `Dockerfile.cdc-bridge` | Imagem para CDC-to-BPM bridge |
| **Dockerfile Webhook** | `Dockerfile.webhook-receiver` | Imagem para callback receiver |
| **Keycloak Realm** | `config/keycloak/maezo-bpm-realm.json` | 14 clients OAuth2 configurados |
| **FHIR Config** | Via Helm ConfigMap | Search params brasileiros (CPF, CNS, TUSS) |

**Guia de uso:** `helm/README.md`

---

## 1. Infraestrutura e DevOps

### 1.1 Provisionamento AWS EKS
- [ ] Criar cluster EKS com node groups para namespaces: `orchestration`, `workers`, `integration`, `data`, `monitoring`
- [ ] Provisionar RDS PostgreSQL 16 Multi-AZ (fora do cluster)
- [ ] Configurar MSK (Kafka KRaft) com 3 brokers
- [ ] Provisionar ElastiCache Redis Sentinel (3 nós)
- [ ] Provisionar Elasticsearch 8.13 (3 nós)
- [ ] Configurar VPC, subnets, security groups, IAM roles
- [ ] Configurar TLS 1.3 em todos os endpoints
- [ ] Habilitar PostgreSQL TDE (encryption at rest)
- [ ] Instalar e configurar pgaudit para auditoria LGPD

### 1.2 CI/CD Pipeline ✅ COMPLETO
- [x] Criar pipeline CI/CD (GitHub Actions) — **`.github/workflows/ci-cd.yaml`**
- [x] Configurar build automático dos workers Python (Docker images) — **Multi-stage build**
- [x] Configurar deploy automático para `dev`, `staging`, `prod` — **Helm upgrade via Actions**
- [x] Configurar análise estática para detecção de PII em variáveis de processo — **Bandit + grep check**
- [x] Configurar geração automática de inventário DMN no CI — **Artifact upload**
- [x] **NOVO**: BPMN validation workflow (XML, XSD, BPMNDI, topics) — **`.github/workflows/bpmn-validation.yml`**
- [x] **NOVO**: Integration test workflow (4 test suites) — **`.github/workflows/bpmn-integration-test.yml`**
- [x] **NOVO**: Docker Compose test environment — **`docker-compose.test.yml`**
- [ ] **HUMANO**: Configurar secrets no GitHub (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, etc.)
- [ ] **HUMANO**: Criar environments no GitHub (dev, staging, production)

### 1.3 Docker e Kubernetes ✅ COMPLETO
- [x] Criar `docker-compose.yml` para ambiente local
- [x] Criar `Dockerfile` para workers Python
- [x] Criar `Dockerfile.cdc-bridge` para CDC bridge — **NOVO**
- [x] Criar `Dockerfile.webhook-receiver` para webhook receiver — **NOVO**
- [x] Criar Helm charts para todos os componentes — **`helm/maezo/`**
- [x] Configurar HPA para cada worker — **Via values.yaml autoscaling**
- [x] Configurar `cdc-to-bpm-bridge` com 2 réplicas — **Via Helm**
- [x] **NOVO**: Production Helm values — **`helm/maestro/values-prod.yaml`**
- [x] **NOVO**: Kubernetes overlays (staging/prod) — **`k8s/overlays/`**
- [x] **NOVO**: Smoke test suite (12 tests) — **`tests/smoke/`**
- [x] **NOVO**: Operational runbooks — **`docs/runbooks/`**
- [ ] **HUMANO**: Aplicar secrets reais (substituir CHANGE_ME em `k8s/base/secrets.yaml`)
- [ ] **HUMANO**: Configurar External Secrets Operator para AWS Secrets Manager (prod)

### 1.4 Ambientes ✅ CONFIGURAÇÃO PRONTA
- [x] Configurar ambiente `local` (Docker Compose) — **`docker-compose.yml`**
- [x] Configurar ambiente `dev` — **`helm/maezo/values-dev.yaml`**
- [x] Configurar ambiente `staging` — **`helm/maezo/values-staging.yaml`**
- [x] Configurar ambiente `prod` — **`helm/maezo/values.yaml` (padrão)**
- [ ] **HUMANO**: Provisionar clusters EKS para cada ambiente


---

## 2. CIB Seven Engine (Java)

### 2.1 Configuração do Engine
- [ ] Deploy CIB Seven 2.1.3 no K8s com configuração conforme spec (pool sizes, history cleanup, multi-tenancy)
- [ ] Configurar multi-tenancy com 4 tenants: `hospital-a`, `amh-sp-morumbi`, `amh-rj-barra`, `amh-mg-bh`
- [ ] Configurar `default-tenant: hospital-a`
- [ ] Configurar External Task lock duration (300000ms) e retry timeout (30000ms)
- [ ] Deploy Cockpit e Tasklist

### 2.2 Keycloak / Segurança
- [ ] Criar realm `maezo-bpm` no Keycloak 24
- [ ] Criar 8 clients com `client_credentials` grant (worker-eligibility, worker-tiss, worker-denial, worker-whatsapp, worker-clinical, worker-payment, cdc-bridge, omnicash-intelligence)
- [ ] Configurar scopes: `external-task`, `fhir-read`, `fhir-write`, `process-start`, `message-correlate`, `history-read`
- [ ] Criar 4 grupos (hospital units) e 4 roles (admin, operator, analyst, viewer)
- [ ] Integrar CIB Seven com Keycloak para autenticação

---

## 3. Integração com ERPs (Trabalho Crítico — Depende de Acesso)

### 3.1 Debezium CDC — Tasy (Oracle)
- [ ] **Negociar acesso ao Oracle LogMiner com DBA do Tasy** (risco médio-alto)
- [ ] Configurar Debezium connector para Oracle (tabelas: `ATENDIMENTO`, `CONTA_MEDICA`, `ITEM_CONTA`, `PRESCRICAO`, `SINAL_VITAL`)
- [ ] Criar tópicos Kafka conforme spec (`tasy.HOSPITAL_A.ATENDIMENTO`, etc.)
- [ ] Testar CDC end-to-end com dados reais
- [ ] Implementar fallback para polling caso LogMiner seja bloqueado

### 3.2 Debezium CDC — MV Soul (PostgreSQL) — Fase 2
- [ ] Configurar Debezium connector para PostgreSQL MV Soul (tabelas: `ATENDIME`, `ITREG_FAT`, `REGISTRO_ALTA`)
- [ ] Configurar tópicos Kafka para cada tenant AMH (`mv.{tenant}.*`)

### 3.3 HAPI FHIR
- [ ] Deploy HAPI FHIR 7.4.0 (JPA) no cluster
- [ ] Criar adaptadores Tasy → FHIR para cada recurso (Patient, Coverage, Encounter, Observation, Claim, ClaimResponse, Practitioner, Location, MedicationRequest)
- [ ] Criar adaptadores MV Soul → FHIR (Fase 2)
- [ ] Configurar índices e Redis caching para performance
- [ ] Realizar load test de HAPI FHIR na Fase 1

### 3.4 Mirth Connect
- [ ] Deploy Mirth Connect 4.5.2
- [ ] Configurar canais HL7 para integração com sistemas hospitalares
- [ ] Configurar tópico Kafka `mirth.fhir.observations`

### 3.5 cdc-to-bpm-bridge (Python) ✅ IMPLEMENTADO
- [x] Implementar consumer Kafka → REST API CIB Seven — **`healthcare_platform/shared/cdc_bridge/`**
- [x] Implementar lógica de start/correlate process instances — **4 tables mapeadas (ADR-004)**
- [x] Configurar dead-letter queue (`bridge.dead-letter`) — **`dead_letter.py`**
- [x] Implementar retry com backoff — **Exponential backoff (3 attempts)**
- [x] Unit tests com 100% pass rate — **35/35 tests (`tests/unit/cdc_bridge/`)**
- [ ] **HUMANO**: Habilitar Oracle LogMiner no Tasy para CDC funcionar
- [ ] **HUMANO**: Deploy em staging com Kafka real

---

## 4. Workers Python — Configuração de Runtime

### 4.1 Framework Base ✅ COMPLETO
- [x] Criar `pyproject.toml` com dependências do projeto
- [x] Configurar `camunda-external-task-client-python3` para conectar ao CIB Seven (`worker_runner.py`)
- [x] Auto-discovery de 184 workers via `registry.py` (padrões `@worker` e `WORKER_TYPE`)
- [x] Health checks HTTP para K8s probes (`:8000/health`)
- [x] Logging estruturado (structlog)
- [x] Dockerfile + Docker Compose com 4 workers por domínio
- [x] Prometheus scrape config alinhado aos serviços Docker
- [x] **NOVO**: Generic Worker Framework (8 archetypes, DMN-driven) — **`healthcare_platform/shared/workers/generic/`**
- [x] **NOVO**: Topic registry validation (2,290 lines, 200+ topics) — **`config/topic_registry.yaml`**
- [x] **NOVO**: Worker topic standardization (ADR-016 compliance) — **86 workers atualizados**
- [x] **NOVO**: Generic worker unit tests (10 modules, 100% coverage) — **`tests/unit/workers/generic/`**
- [ ] Validação de PII (rejeitar CPF, email em variáveis de processo)
- [ ] Autenticação via Keycloak (client_credentials) — config preparada mas requer realm ativo
- [ ] Métricas Prometheus nos workers (endpoint `/metrics`)

**Generic Worker Framework (NOVO):**
- 8 archetypes: `AdminAdjudication`, `ClinicalAlert`, `ClinicalScore`, `ComplianceValidation`, `DataEnrichment`, `FinancialCalculation`, `OperationalRouting`, `BaseGeneric`
- DMN-driven logic delegation (ADR-015 compliance)
- Pipeline patterns: linear, parallel, conditional
- Automated worker discovery via registry loader
- 100% topic registry validation before deployment
- Comprehensive unit test coverage (3,183 lines)

### 4.2 Integrações Externas dos Workers (Acesso a APIs Reais)
- [ ] **worker-eligibility**: Integrar com APIs reais das operadoras (Bradesco, Unimed, etc.) para verificação de elegibilidade
- [ ] **worker-tiss**: Integrar com portais de operadoras para submissão TISS XML
- [ ] **worker-denial**: Integrar com sistemas de contestação das operadoras
- [ ] **worker-whatsapp**: Configurar API WhatsApp Business (Meta) com templates aprovados
- [ ] **worker-payment**: Integrar com sistema financeiro para conciliação CNAB
- [ ] **worker-production**: Integrar com IoT/RFID para captura de produção (Fase 4)
- [ ] **worker-clinical**: Integrar com sistemas de alertas clínicos e enfermagem

---

## 5. BPMN — Deploy e Validação

### 5.1 Deploy de Processos ✅ PARCIALMENTE PRONTO
- [x] **NOVO**: Consolidar e refatorar processos BPMN (ADR-019 compliance)
- [x] **NOVO**: Padronizar nomenclatura (`SP-{DOMAIN}-{NNN}_Process_Name.bpmn`)
- [x] **NOVO**: Validação automática (CI/CD) — XML, XSD, BPMNDI, topics
- [x] **NOVO**: Pre-commit hook para BPMN compliance — **`scripts/bpmn_pre_commit_hook.sh`**
- [x] **NOVO**: Worker connectivity validator — **`scripts/validate_bpmn_worker_connectivity.py`**
- [x] **NOVO**: Integration tests (deployment, namespace, instantiation, topics) — **`tests/integration/bpmn/`**
- [ ] Validar e fazer deploy dos 42 arquivos BPMN no CIB Seven via API
- [ ] Configurar tenant-specific deployments onde necessário
- [ ] Testar timer events (SLA enforcement) em ambiente real
- [ ] Validar call activities entre processos (SP-RC-000 → sub-processes)

**Recentes Mudanças:**
- Revenue Cycle: `SP-RC-008A/B` consolidados em `SP-RC-008`, `SP-RC-009` promovido para `SP-RC-011`
- Clinical Ops: `SP-PA-011/012` movidos para `SP-CO-011/012` (patient access → clinical ops)
- Main process: `revenue-cycle-main.bpmn` → `SP-RC-000_Revenue_Cycle_Main.bpmn`
- 13 processos deletados/consolidados, 6 processos renomeados/reestruturados

### 5.2 DMN — Deploy e Validação ✅ PARCIALMENTE PRONTO
- [x] **NOVO**: DMN validation tooling — **`scripts/validate_dmn.py`**
- [x] **NOVO**: DMN inventory generator — **`scripts/dmn_inventory.py`**
- [x] **NOVO**: DMN tenant resolver — **`scripts/dmn_tenant_resolver.py`**
- [x] **NOVO**: Surgery DMN generator — **`scripts/generate_surgery_dmn.py`**
- [ ] Validar os 838 arquivos DMN (FEEL 1.3 syntax)
- [ ] Deploy DMN com resolução por tenant (local override > global)
- [ ] Validar regras com dados reais de cada operadora
- [ ] Configurar revisão trimestral de regras DMN com analistas

---

## 6. Observabilidade e Monitoramento

- [ ] Deploy Prometheus 2.51 + Grafana 11 + AlertManager
- [ ] Configurar dashboards Grafana para:
  - Métricas do CIB Seven engine (job execution, external tasks, incidents)
  - Métricas dos workers (latência, erros, throughput)
  - KPIs de ciclo de receita (tempo de fechamento de conta, taxa de glosa, etc.)
- [ ] Deploy Fluentd + Kibana para logs centralizados
- [ ] Configurar alertas para SLAs dos external tasks (5s–60s conforme spec)
- [ ] Deploy CIB ins7ght Enterprise (R$ 60.000/ano) para process analytics

---

## 7. Testes com Dados Reais

- [ ] Obter dados anonimizados de produção do Tasy para staging
- [ ] Executar testes end-to-end com fluxo completo de revenue cycle
- [ ] Realizar **shadow mode** de 2 semanas com Bradesco Saúde (paralelo com processo manual)
- [ ] Validar KPIs baseline vs. targets em ambiente de staging
- [ ] Realizar load test para validar capacidade (estimativa de volume de processos/dia)

---

## 8. Compliance e Segurança

- [ ] Realizar assessment LGPD do fluxo completo de dados
- [ ] Validar que nenhuma variável de processo contém PII (apenas FHIR IDs)
- [ ] Configurar history TTL por tipo de processo (180 dias padrão, 6 anos revenue cycle, 365 dias alertas clínicos)
- [ ] Realizar auditoria interna ONA Nível 3 nos novos fluxos digitais
- [ ] Documentar plano de resposta a incidentes de segurança

---

## 9. Treinamento e Capacitação

- [ ] Treinar analistas de negócio em BPMN/DMN (R$ 35.000 budget)
- [ ] Treinar equipe de TI em administração CIB Seven
- [ ] Criar runbooks operacionais para equipe de suporte
- [ ] Treinar equipe de faturamento no novo fluxo via Tasklist/Cockpit

---

## 10. Go-Live e Operação

- [ ] Planejar cutover para `hospital-a` (Fase 1)
- [ ] Configurar rollback plan
- [ ] Estabelecer Centro de Excelência (CoE) BPM — Fase 4
- [ ] Planejar onboarding de operadoras adicionais no DMN (Unimed, SulAmérica, Amil — Fase 2)
- [ ] Planejar expansão para tenants AMH (Fase 2)

---

## Resumo por Fase

| Fase | Semanas | Pendências Humanas Principais |
|------|---------|-------------------------------|
| **1 — Foundation + Revenue Cycle** | 1–16 | Infra AWS, CI/CD, Docker/K8s, Keycloak, CDC Tasy, FHIR adapters, deploy BPMN/DMN, shadow mode Bradesco |
| **2 — Access + Discharge** | 17–28 | CDC MV Soul, adapters MV→FHIR, onboarding operadoras, WhatsApp Business, engine 2 réplicas |
| **3 — Clinical + Intelligence** | 29–40 | Alertas clínicos integrados, CMMN, ML/AI models, VBHC contracts |
| **4 — Platform + Otimização** | 41+ | IoT/RFID, process mining, CoE, JCI prep, supply chain |
