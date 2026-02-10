# Pendências para Desenvolvedores

**Versão:** 1.1
**Data:** 10 de Fevereiro de 2026
**Última Atualização:** Wave 0.5 - Infrastructure Acceleration
**Baseado em:** [Especificação Técnica Consolidada v1.1](../Technical%20specification/technical-specification.md)

> Tarefas que **não podem ser automatizadas por agentes de IA** e requerem trabalho manual de desenvolvedores humanos, DevOps, analistas de negócio ou stakeholders hospitalares.

---

## ✅ NOVO: Artefatos Gerados pelo AI (Wave 0.5)

Os seguintes artefatos foram gerados e estão prontos para uso:

| Artefato | Localização | Descrição |
|----------|-------------|-----------|
| **Helm Chart** | `helm/maestro/` | Chart completo com CIB7, Workers, FHIR, Kafka, Redis, Keycloak |
| **Values Dev** | `helm/maestro/values-dev.yaml` | Configuração para ambiente de desenvolvimento |
| **Values Staging** | `helm/maestro/values-staging.yaml` | Configuração para staging |
| **K8s Namespace** | `k8s/base/namespace.yaml` | Namespace, RBAC, quotas, limits |
| **K8s Secrets** | `k8s/base/secrets.yaml` | Templates de secrets (SUBSTITUIR VALORES!) |
| **K8s NetworkPolicies** | `k8s/base/network-policies.yaml` | Zero-trust networking |
| **CI/CD Pipeline** | `.github/workflows/ci-cd.yaml` | GitHub Actions completo |
| **Dockerfile CDC Bridge** | `Dockerfile.cdc-bridge` | Imagem para CDC-to-BPM bridge |
| **Dockerfile Webhook** | `Dockerfile.webhook-receiver` | Imagem para callback receiver |
| **Keycloak Realm** | `config/keycloak/austa-bpm-realm.json` | 14 clients OAuth2 configurados |
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

### 1.2 CI/CD Pipeline ✅ PARCIALMENTE PRONTO
- [x] Criar pipeline CI/CD (GitHub Actions) — **`.github/workflows/ci-cd.yaml`**
- [x] Configurar build automático dos workers Python (Docker images) — **Multi-stage build**
- [x] Configurar deploy automático para `dev`, `staging`, `prod` — **Helm upgrade via Actions**
- [x] Configurar análise estática para detecção de PII em variáveis de processo — **Bandit + grep check**
- [x] Configurar geração automática de inventário DMN no CI — **Artifact upload**
- [ ] **HUMANO**: Configurar secrets no GitHub (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, etc.)
- [ ] **HUMANO**: Criar environments no GitHub (dev, staging, production)

### 1.3 Docker e Kubernetes ✅ PARCIALMENTE PRONTO
- [x] Criar `docker-compose.yml` para ambiente local
- [x] Criar `Dockerfile` para workers Python
- [x] Criar `Dockerfile.cdc-bridge` para CDC bridge — **NOVO**
- [x] Criar `Dockerfile.webhook-receiver` para webhook receiver — **NOVO**
- [x] Criar Helm charts para todos os componentes — **`helm/maestro/`**
- [x] Configurar HPA para cada worker — **Via values.yaml autoscaling**
- [x] Configurar `cdc-to-bpm-bridge` com 2 réplicas — **Via Helm**
- [ ] **HUMANO**: Aplicar secrets reais (substituir CHANGE_ME em `k8s/base/secrets.yaml`)
- [ ] **HUMANO**: Configurar External Secrets Operator para AWS Secrets Manager (prod)

### 1.4 Ambientes ✅ CONFIGURAÇÃO PRONTA
- [x] Configurar ambiente `local` (Docker Compose) — **`docker-compose.yml`**
- [x] Configurar ambiente `dev` — **`helm/maestro/values-dev.yaml`**
- [x] Configurar ambiente `staging` — **`helm/maestro/values-staging.yaml`**
- [x] Configurar ambiente `prod` — **`helm/maestro/values.yaml` (padrão)**
- [ ] **HUMANO**: Provisionar clusters EKS para cada ambiente


---

## 2. CIB Seven Engine (Java)

### 2.1 Configuração do Engine
- [ ] Deploy CIB Seven 2.1.3 no K8s com configuração conforme spec (pool sizes, history cleanup, multi-tenancy)
- [ ] Configurar multi-tenancy com 4 tenants: `austa-hospital`, `amh-sp-morumbi`, `amh-rj-barra`, `amh-mg-bh`
- [ ] Configurar `default-tenant: austa-hospital`
- [ ] Configurar External Task lock duration (300000ms) e retry timeout (30000ms)
- [ ] Deploy Cockpit e Tasklist

### 2.2 Keycloak / Segurança
- [ ] Criar realm `austa-bpm` no Keycloak 24
- [ ] Criar 8 clients com `client_credentials` grant (worker-eligibility, worker-tiss, worker-denial, worker-whatsapp, worker-clinical, worker-payment, cdc-bridge, omnicash-intelligence)
- [ ] Configurar scopes: `external-task`, `fhir-read`, `fhir-write`, `process-start`, `message-correlate`, `history-read`
- [ ] Criar 4 grupos (hospital units) e 4 roles (admin, operator, analyst, viewer)
- [ ] Integrar CIB Seven com Keycloak para autenticação

---

## 3. Integração com ERPs (Trabalho Crítico — Depende de Acesso)

### 3.1 Debezium CDC — Tasy (Oracle)
- [ ] **Negociar acesso ao Oracle LogMiner com DBA do Tasy** (risco médio-alto)
- [ ] Configurar Debezium connector para Oracle (tabelas: `ATENDIMENTO`, `CONTA_MEDICA`, `ITEM_CONTA`, `PRESCRICAO`, `SINAL_VITAL`)
- [ ] Criar tópicos Kafka conforme spec (`tasy.AUSTA.ATENDIMENTO`, etc.)
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

### 3.5 cdc-to-bpm-bridge (Python)
- [ ] Implementar consumer Kafka → REST API CIB Seven
- [ ] Implementar lógica de start/correlate process instances
- [ ] Configurar dead-letter queue (`bridge.dead-letter`)
- [ ] Implementar retry com backoff

---

## 4. Workers Python — Configuração de Runtime

### 4.1 Framework Base (✅ Parcialmente Implementado)
- [x] Criar `pyproject.toml` com dependências do projeto
- [x] Configurar `camunda-external-task-client-python3` para conectar ao CIB Seven (`worker_runner.py`)
- [x] Auto-discovery de 184 workers via `registry.py` (padrões `@worker` e `WORKER_TYPE`)
- [x] Health checks HTTP para K8s probes (`:8000/health`)
- [x] Logging estruturado (structlog)
- [x] Dockerfile + Docker Compose com 4 workers por domínio
- [x] Prometheus scrape config alinhado aos serviços Docker
- [ ] Validação de PII (rejeitar CPF, email em variáveis de processo)
- [ ] Autenticação via Keycloak (client_credentials) — config preparada mas requer realm ativo
- [ ] Métricas Prometheus nos workers (endpoint `/metrics`)

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

### 5.1 Deploy de Processos
- [ ] Validar e fazer deploy dos 42 arquivos BPMN no CIB Seven via API
- [ ] Configurar tenant-specific deployments onde necessário
- [ ] Testar timer events (SLA enforcement) em ambiente real
- [ ] Validar call activities entre processos (revenue-cycle-main → sub-processes)

### 5.2 DMN — Deploy e Validação
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

- [ ] Planejar cutover para `austa-hospital` (Fase 1)
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
