<p align="center">
  <img src="docs/assets/maestro-logo.png" alt="Maestro" width="280" />
</p>

<h1 align="center">Maestro</h1>

<p align="center">
  <strong>Plataforma de Orquestração Hospitalar</strong><br/>
  <em>Saúde em harmonia.</em>
</p>

<p align="center">
  <a href="#o-problema">O Problema</a> •
  <a href="#a-solução">A Solução</a> •
  <a href="#capacidades">Capacidades</a> •
  <a href="#para-quem">Para Quem</a> •
  <a href="#especificações-técnicas">Especificações</a>
</p>

---

## O Problema

Hospitais brasileiros perdem **R$ 2-4 bilhões por ano** com vazamentos de receita evitáveis:

| Dor | Impacto |
|-----|---------|
| 🔴 **Glosas** | 8-15% do faturamento negado pelas operadoras |
| 🔴 **Autorização Manual** | 48+ horas aguardando resposta de autorização prévia |
| 🔴 **Sistemas Fragmentados** | Tasy, MV, FHIR, operadoras — nenhum conversa com o outro |
| 🔴 **Falhas de Conformidade** | Violações ANS, TISS, LGPD por processos manuais |
| 🔴 **Ciclo de Receita Lento** | 45-90 dias em média até o recebimento |
| 🔴 **Documentação Clínica** | Prontuários incompletos = contas glosadas |

> *"Se o paciente precisa nos procurar para saber o que acontece com ele, já falhamos em antecipar sua necessidade."*

---

## A Solução

**Maestro** é o **sistema nervoso digital** das operações hospitalares.

Substitui fluxos fragmentados e isolados por departamento por **jornadas orquestradas** que acompanham o paciente do primeiro contato ao recebimento final — conectando sistemas clínicos, administrativos e financeiros através de **processos BPMN automatizados** e **mais de 600 regras de negócio inteligentes (DMN)**.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│    Acesso          Operações         Ciclo de      Pagamento│
│    do Paciente →   Clínicas     →    Receita   →   Operadora│
│                                                             │
│    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                    Maestro Orquestra                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### O Que Muda

| Antes do Maestro | Depois do Maestro |
|------------------|-------------------|
| Glosa descoberta no pagamento | Glosa **prevenida** na captura |
| Verificação de elegibilidade manual (horas) | Elegibilidade em tempo real (segundos) |
| Autorizações em papel | Fluxo digital com acompanhamento de SLA |
| Handoffs departamentais isolados | Jornada do paciente orquestrada |
| Conformidade reativa | Conformidade proativa em cada etapa |
| Vazamento de receita desconhecido | Cada real visível, rastreado, recuperado |

---

## Capacidades

### 🏥 Acesso do Paciente
- **Captura de Demanda** — Atendimento omnichannel (WhatsApp, Portal, Call Center)
- **Agendamento Inteligente** — Otimização de capacidade, alocação de recursos
- **Identificação e Cadastro** — Prevenção de duplicidade, qualidade de dados
- **Liberação Financeira** — Elegibilidade em tempo real, autorização prévia
- **Admissão Digital** — Internação sem papel, gestão de consentimentos
- **Fluxo de Check-in** — Gestão de filas, otimização de tempo de espera

### 🩺 Operações Clínicas
- **Coordenação da Equipe de Cuidado** — Atribuições, handoffs, comunicação
- **Suporte à Decisão Clínica** — Interações medicamentosas, alertas de sepse, valores críticos
- **Conformidade Documental** — Campos obrigatórios, sugestões de codificação, checagens de qualidade
- **Planejamento de Alta** — Score de prontidão, agendamento de seguimento

### 💰 Ciclo de Receita
- **Captura de Produção** — Tempo real, sem perda de lançamentos
- **Otimização de Codificação** — Sugestões TUSS, CID-10, CBHPM
- **Prevenção de Glosas** — 600+ regras identificam problemas antes do envio
- **Conformidade TISS** — Geração automática de XML, validação de schema
- **Gestão de Negativas** — Workflows de recurso, análise de causa raiz
- **Conciliação de Pagamentos** — Parsing CNAB, matching automático, detecção de variância

### 🔒 Serviços de Plataforma
- **Multi-Tenant** — Uma plataforma, múltiplos hospitais, dados isolados
- **Conformidade Regulatória** — ANS, ANVISA, LGPD nativos
- **Credenciamento** — Gestão de prestadores, unidades, contratos
- **Analytics & BI** — Dashboards em tempo real, relatórios executivos

---

## Os Números

| Métrica | Valor |
|---------|-------|
| **Workers** | 184 processadores de tarefas automatizados |
| **Regras de Negócio (DMN)** | 838 tabelas de decisão |
| **Processos BPMN** | 42 fluxos orquestrados |
| **Domínios Cobertos** | 4 (Acesso, Clínico, Receita, Plataforma) |
| **Tenants Suportados** | 4 hospitais (AUSTA, AMH-SP, AMH-RJ, AMH-MG) |
| **Integrações com Operadoras** | Bradesco, Unimed, SulAmérica, Amil, + outras |
| **Padrões de Conformidade** | ANS, TISS 4.0, LGPD, ANVISA |

---

## Para Quem

### CFOs e Diretores de Ciclo de Receita
> "Reduzimos a taxa de glosa de 12% para 4% em 6 meses. O Maestro se paga sozinho."

- Visualize cada real no seu pipeline de receita
- Preveja fluxo de caixa com forecasting baseado em IA
- Reduza dias em contas a receber de 60 para 35

### CIOs e Diretores de TI
> "Uma plataforma substituiu 7 projetos de integração. Nossa equipe finalmente dorme à noite."

- Camada única de orquestração para todos os sistemas
- Fim das integrações ponto-a-ponto
- Construído em padrões abertos (BPMN, DMN, FHIR R4)

### Oficiais de Qualidade e Compliance
> "Auditoria LGPD? Passamos com zero achados. Tudo é rastreável."

- Cada interação com o paciente registrada e auditável
- Regras de conformidade aplicadas automaticamente
- Alertas em tempo real para prazos regulatórios

---

## 5 Jornadas do Paciente

O Maestro orquestra a experiência completa do paciente em **5 jornadas interconectadas**:

1. **Jornada de Acesso** — Do primeiro contato ao paciente pronto para o cuidado
2. **Jornada de Cuidado** — Da admissão à alta com desfechos documentados
3. **Jornada de Continuidade** — Da pós-alta à estabilização
4. **Jornada de Relacionamento** — Da primeira interação à fidelização
5. **Jornada Financeira** — Da verificação de elegibilidade ao recebimento completo

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│  Canais: WhatsApp · Portal · Cockpit · Grafana              │
├─────────────────────────────────────────────────────────────┤
│  Orquestração: CIB Seven 2.1.3 (BPMN · DMN · CMMN)          │
│  Engine Único · Multi-Tenant · Padrão External Task         │
├─────────────────────────────────────────────────────────────┤
│  Workers: Python 3.12 (184 processadores stateless)         │
│  elegibilidade · tiss · glosa · whatsapp · clínico · …      │
├─────────────────────────────────────────────────────────────┤
│  Inteligência: 838 Tabelas de Decisão DMN                   │
│  prevenção de glosa · regras de codificação · conformidade  │
├─────────────────────────────────────────────────────────────┤
│  Integração: Debezium CDC · Kafka · HAPI FHIR R4            │
│  Adaptador Tasy · Adaptador MV Soul · Cliente TISS          │
├─────────────────────────────────────────────────────────────┤
│  Dados: PostgreSQL 16 · Redis 7.2 · Elasticsearch 8.13      │
├─────────────────────────────────────────────────────────────┤
│  Infra: EKS · Keycloak 24 · Prometheus · Grafana 11         │
└─────────────────────────────────────────────────────────────┘
```

---

## Início Rápido

### Pré-requisitos
- Docker Desktop (8GB+ RAM)
- Python 3.11+
- Git

### 1. Clone e Inicie
```bash
git clone git@github.com:your-org/maestro.git
cd maestro
docker compose up -d
```

### 2. Verifique o Engine
```bash
curl http://localhost:8080/engine-rest/engine
# Esperado: [{"name":"default"}]
```

### 3. Acesse os Dashboards

| Serviço | URL | Credenciais |
|---------|-----|-------------|
| Cockpit (Monitor de Processos) | http://localhost:8080/cibseven/app/cockpit | admin/admin |
| Tasklist (Tarefas Humanas) | http://localhost:8080/cibseven/app/tasklist | admin/admin |
| Grafana (Métricas) | http://localhost:3000 | admin/admin |
| HAPI FHIR | http://localhost:8082/fhir/metadata | — |
| Keycloak (Identidade) | http://localhost:8180/admin | admin/admin |

---

## Stack Tecnológica

| Camada | Tecnologia | Versão |
|--------|------------|--------|
| Orquestração | CIB Seven | 2.1.3 |
| Workers | Python | 3.12 |
| Servidor FHIR | HAPI FHIR R4 | 7.4.0 |
| CDC | Debezium | 2.7 |
| Streaming | Apache Kafka | 3.7 |
| Banco de Dados | PostgreSQL | 16 |
| Cache | Redis | 7.2 |
| Identidade | Keycloak | 24 |
| Observabilidade | Prometheus + Grafana | Mais recente |

---

## Estrutura do Repositório

```
maestro/
├── healthcare_platform/       # Código principal da plataforma
│   ├── patient_access/        # 46 workers, 7 BPMN, 68 DMN
│   ├── clinical_operations/   # 20 workers, 4 BPMN, 371 DMN
│   ├── revenue_cycle/         # 89 workers, 14 BPMN, 237 DMN
│   ├── platform_services/     # 29 workers, 6 BPMN, 94 DMN
│   └── shared/                # Multi-tenant, integrações, domínio
├── tests/                     # 182 testes (unitários, integração, DMN)
├── docs/                      # ADRs, specs, guias de migração
├── config/                    # Observabilidade (Prometheus, Grafana)
└── scripts/                   # Ferramentas de deploy e migração
```

---

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [Especificação Técnica](docs/Technical%20specification/technical-specification.md) | Arquitetura completa do sistema |
| [ADRs](docs/ADRs/) | 13 Registros de Decisão de Arquitetura |
| [Guia de Migração](docs/Migration/) | Migração de sistemas legados |
| [Regras de Negócio](docs/Regras%20de%20Negocio%20(PT-BR)/) | Inventário completo de regras |

---

## Estatísticas Técnicas do Projeto

### Artefatos Implementados

| Artefato | Quantidade | Status |
|----------|-----------|--------|
| **Workers Python** | 184 (de 161 planejados) | ✅ Superado |
| **Tabelas DMN** | 838 (de 667 planejadas) | ✅ Superado |
| **Processos BPMN** | 42 (de 31 planejados) | ✅ Superado |
| **Testes automatizados** | 182 | 🔄 Em expansão |
| **Arquivos Python total** | 317 | — |
| **ADRs documentados** | 13 | ✅ Completo |

### Distribuição por Domínio

| Domínio | Workers | BPMN | DMN | Arquivos Python |
|---------|---------|------|-----|-----------------|
| **Ciclo de Receita** | 89 | 14 | 237 | 124 |
| **Acesso do Paciente** | 46 | 7 | 68 | 50 |
| **Serviços de Plataforma** | 29 | 6 | 94 | 61 |
| **Operações Clínicas** | 20 | 4 | 371 | 47 |
| **Shared (Multi-tenant)** | — | — | — | 34 |

### Cobertura por Fase de Implementação

| Fase | Escopo | Workers | BPMN | Status |
|------|--------|---------|------|--------|
| **Fase 1** — Revenue Cycle MVP | Faturamento, codificação, glosas, pagamentos | 89 | 14 | 🟡 Código pronto, infra pendente |
| **Fase 2** — Acesso + Alta | Agendamento, elegibilidade, check-in, alta | 46 | 7 | 🟡 Código pronto, infra pendente |
| **Fase 3** — Operações Clínicas | Triagem, sepse, cirúrgico, medicamentos | 20 | 4 | 🟡 Código pronto, infra pendente |
| **Fase 4** — Plataforma | Supply chain, analytics, compliance | 29 | 6 | 🟡 Código pronto, infra pendente |

---

## Próximos Passos para Deploy

### 🚀 DevOps Quick Start — Wave 0.5 Infra (NOVO)

Infraestrutura como código pronta para acelerar seu deploy:

| Artefato | Localização | O que contém |
|----------|-------------|--------------|
| **Helm Chart completo** | [`helm/maestro/`](helm/README.md) | Chart.yaml, values.yaml, templates para todos os serviços |
| **Values por ambiente** | `helm/maestro/values-{dev,staging}.yaml` | Configurações específicas por ambiente |
| **K8s Base Manifests** | `k8s/base/` | Namespace, RBAC, Secrets, Network Policies |
| **CI/CD Pipeline** | `.github/workflows/ci-cd.yaml` | Build, test, security scan, deploy multi-stage |
| **Dockerfiles adicionais** | `Dockerfile.cdc-bridge`, `Dockerfile.webhook-receiver` | Containers para CDC e webhooks TASY |
| **Keycloak Realm** | `config/keycloak/austa-bpm-realm.json` | 5 clients (admin + 4 domain workers) |

**Para começar:**
```bash
# 1. Revisar README do Helm
cat helm/README.md

# 2. Dry-run local para validar templates
helm template maestro helm/maestro -f helm/maestro/values-dev.yaml

# 3. Install em cluster dev
helm install maestro helm/maestro -n maestro --create-namespace -f helm/maestro/values-dev.yaml
```

> 📖 **Guia detalhado:** [`helm/README.md`](helm/README.md) — Inclui checklist DevOps, troubleshooting e roadmap de deploy.

---

### O Que Falta (Infraestrutura e Integração)

O código da plataforma (workers, BPMN, DMN) está implementado. As pendências são de **infraestrutura, integração e operação** — itens que requerem acesso a ambientes reais e configuração manual.

| Pendência | Criticidade | Responsável |
|-----------|-------------|-------------|
| **Cluster EKS + RDS + Kafka + Redis** | 🔴 Bloqueante | DevOps/SRE |
| **CI/CD Pipeline** | ✅ **Implementado** (.github/workflows/ci-cd.yaml) | — |
| **Docker Compose + Dockerfiles** | ✅ Implementado | — |
| **Helm Charts / K8s Manifests** | ✅ **Implementado** (helm/, k8s/) | — |
| **pyproject.toml / requirements.txt** | ✅ Implementado | — |
| **Keycloak realm + clients** | 🔴 Bloqueante | Java Dev |
| **Deploy CIB Seven 2.1.3** | 🔴 Bloqueante | Java Dev / BPM Architect |
| **Debezium CDC → Tasy Oracle** | 🟠 Alta | Integration Dev + DBA |
| **HAPI FHIR + adaptadores Tasy→FHIR** | 🟠 Alta | Integration Dev |
| **Mirth Connect HL7** | 🟡 Média | Integration Dev |
| **APIs reais das operadoras** | 🟠 Alta | Dev Python + Negócio |
| **WhatsApp Business API** | 🟡 Média | Dev Python |
| **Shadow mode com Bradesco** | 🟡 Média | Equipe completa |

### Runtime Bridge — Workers ↔ CIB Seven (Implementado)

O runtime que conecta os 184 workers ao engine CIB Seven já está pronto:

| Componente | Arquivo | Função |
|------------|---------|--------|
| **Worker Runner** | `healthcare_platform/shared/runtime/worker_runner.py` | Bootstrap que conecta workers ao External Task REST API via `camunda-external-task-client-python3` |
| **Worker Registry** | `healthcare_platform/shared/runtime/registry.py` | Auto-discovery dos 184 workers (padrões `@worker(topic=...)` e `WORKER_TYPE`) |
| **Dockerfile** | `Dockerfile` | Imagem Python 3.12 com health check em `:8000` |
| **Docker Compose** | `docker-compose.yml` | 12 serviços: engine + 4 workers + FHIR + Keycloak + Kafka + Redis + Prometheus + Grafana |
| **pyproject.toml** | `pyproject.toml` | Dependências Python (httpx, pydantic, structlog, camunda-client, etc.) |

```bash
# Subir ambiente local completo
docker compose up -d

# Workers por domínio (dentro do container)
python -m healthcare_platform.shared.runtime.worker_runner --domain revenue_cycle
python -m healthcare_platform.shared.runtime.worker_runner --domain clinical_operations
python -m healthcare_platform.shared.runtime.worker_runner --all
```

### Roadmap de Deploy

```
Semana 1-4:   Infraestrutura (EKS, RDS, Kafka, Redis, CI/CD, Docker)
Semana 5-8:   Engine + Keycloak + FHIR + CDC Tasy
Semana 9-12:  Deploy workers + BPMN/DMN + testes integração
Semana 13-14: Shadow mode (Bradesco Saúde, paralelo com manual)
Semana 15-16: Go-live revenue cycle (tenant austa-hospital)
```

> Detalhes completos em [Pendências para Desenvolvedores](docs/Pendencias%20para%20desenvolvedores/pendencias-desenvolvedores.md)

---

## Licença

- **CIB Seven Engine:** Apache License 2.0
- **Plataforma Maestro:** Proprietário

---

<p align="center">
  <strong>Maestro</strong><br/>
  <em>Saúde em harmonia.</em>
</p>
