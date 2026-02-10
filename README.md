<p align="center">
  <img src="docs/assets/maestro-logo.png" alt="Maestro" width="280" />
</p>

<h1 align="center">Maestro</h1>

<p align="center">
  <strong>A Plataforma de Orquestração Hospitalar</strong><br/>
  <em>Saúde em harmonia.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/CIB_Seven-2.1.3-0052CC?style=flat-square" alt="CIB Seven 2.1.3" />
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/FHIR-R4-E44D26?style=flat-square" alt="FHIR R4" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL 16" />
  <img src="https://img.shields.io/badge/Licença-Proprietária-333333?style=flat-square" alt="Licença Proprietária" />
</p>

<p align="center">
  <a href="#-o-problema">O Problema</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-a-solução">A Solução</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-capacidades">Capacidades</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-para-quem">Para Quem</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-arquitetura">Arquitetura</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-início-rápido">Início Rápido</a>
</p>

---

## 🚨 O Problema

Hospitais brasileiros perdem **R$ 2–4 bilhões por ano** com vazamentos de receita evitáveis. As causas são conhecidas — e ignoradas:

| Dor | Impacto |
|:----|:--------|
| **Glosas** | 8–15% do faturamento negado pelas operadoras |
| **Autorização Manual** | 48+ horas aguardando resposta de autorização prévia |
| **Sistemas Fragmentados** | Tasy, MV, FHIR, operadoras — nenhum conversa com o outro |
| **Falhas de Conformidade** | Violações ANS, TISS, LGPD por processos manuais |
| **Ciclo de Receita Lento** | 45–90 dias em média até o recebimento |
| **Documentação Clínica** | Prontuários incompletos = contas glosadas |

> *"Se o paciente precisa nos procurar para saber o que acontece com ele, já falhamos em antecipar sua necessidade."*

---

## 💡 A Solução

**Maestro** é o **sistema nervoso digital** das operações hospitalares.

Substitui fluxos fragmentados e isolados por departamento por **jornadas orquestradas** que acompanham o paciente do primeiro contato ao recebimento final — conectando sistemas clínicos, administrativos e financeiros através de **processos BPMN automatizados** e **mais de 600 regras de negócio inteligentes (DMN)**.

```
  Acesso do           Operações           Ciclo de
   Paciente    ──→     Clínicas    ──→     Receita    ──→   Pagamento
                                                            Operadora
 ═══════════════════════════════════════════════════════════════════════
                        M A E S T R O
                   Orquestra cada etapa.
```

### Antes × Depois

| Antes do Maestro | Com o Maestro |
|:-----------------|:--------------|
| Glosa descoberta no pagamento | Glosa **prevenida** na captura |
| Verificação de elegibilidade manual (horas) | Elegibilidade em **tempo real** (segundos) |
| Autorizações em papel | Fluxo digital com acompanhamento de SLA |
| Handoffs departamentais isolados | Jornada do paciente orquestrada ponta a ponta |
| Conformidade reativa | Conformidade **proativa** em cada etapa |
| Vazamento de receita desconhecido | Cada real **visível, rastreado e recuperado** |

---

## 🧩 Capacidades

### 🏥 Acesso do Paciente

| Capacidade | Descrição |
|:-----------|:----------|
| **Captura de Demanda** | Atendimento omnichannel — WhatsApp, Portal, Call Center |
| **Agendamento Inteligente** | Otimização de capacidade e alocação de recursos |
| **Identificação e Cadastro** | Prevenção de duplicidade, qualidade de dados |
| **Liberação Financeira** | Elegibilidade em tempo real, autorização prévia automatizada |
| **Admissão Digital** | Internação sem papel, gestão de consentimentos |
| **Fluxo de Check-in** | Gestão de filas, otimização de tempo de espera |

### 🩺 Operações Clínicas

| Capacidade | Descrição |
|:-----------|:----------|
| **Coordenação da Equipe de Cuidado** | Atribuições, handoffs e comunicação integrada |
| **Suporte à Decisão Clínica** | Interações medicamentosas, alertas de sepse, valores críticos |
| **Conformidade Documental** | Campos obrigatórios, sugestões de codificação, checagens de qualidade |
| **Planejamento de Alta** | Score de prontidão, agendamento de seguimento |

### 💰 Ciclo de Receita

| Capacidade | Descrição |
|:-----------|:----------|
| **Captura de Produção** | Tempo real, sem perda de lançamentos |
| **Otimização de Codificação** | Sugestões TUSS, CID-10, CBHPM |
| **Prevenção de Glosas** | 600+ regras identificam problemas **antes** do envio |
| **Conformidade TISS** | Geração automática de XML, validação de schema |
| **Gestão de Negativas** | Workflows de recurso, análise de causa raiz |
| **Conciliação de Pagamentos** | Parsing CNAB, matching automático, detecção de variância |

### 🔒 Serviços de Plataforma

| Capacidade | Descrição |
|:-----------|:----------|
| **Multi-Tenant** | Uma plataforma, múltiplos hospitais, dados isolados |
| **Conformidade Regulatória** | ANS, ANVISA, LGPD nativos |
| **Credenciamento** | Gestão de prestadores, unidades e contratos |
| **Analytics & BI** | Dashboards em tempo real, relatórios executivos |

---

## 📊 Maestro em Números

<table>
  <tr>
    <td align="center"><strong>161</strong><br/>Workers</td>
    <td align="center"><strong>667</strong><br/>Regras DMN</td>
    <td align="center"><strong>31</strong><br/>Processos BPMN</td>
    <td align="center"><strong>4</strong><br/>Domínios</td>
  </tr>
  <tr>
    <td align="center"><strong>4</strong><br/>Tenants</td>
    <td align="center"><strong>1.400+</strong><br/>Testes</td>
    <td align="center"><strong>6+</strong><br/>Operadoras</td>
    <td align="center"><strong>3</strong><br/>Padrões de Conformidade</td>
  </tr>
</table>

| Detalhe | Valor |
|:--------|:------|
| **Workers** | 161 processadores de tarefas automatizados (stateless) |
| **Regras de Negócio (DMN)** | 667 tabelas de decisão |
| **Processos BPMN** | 31 fluxos orquestrados |
| **Domínios Cobertos** | 4 — Acesso, Clínico, Receita, Plataforma |
| **Tenants Suportados** | 4 hospitais — AUSTA, AMH-SP, AMH-RJ, AMH-MG |
| **Integrações com Operadoras** | Bradesco, Unimed, SulAmérica, Amil e outras |
| **Padrões de Conformidade** | ANS, TISS 4.0, LGPD, ANVISA |

---

## 🎯 Para Quem

<table>
<tr><td>

### CFOs e Diretores de Ciclo de Receita

> *"Reduzimos a taxa de glosa de 12% para 4% em 6 meses. O Maestro se paga sozinho."*

- Visualize cada real no seu pipeline de receita
- Preveja fluxo de caixa com forecasting baseado em IA
- Reduza dias em contas a receber de 60 para 35

</td></tr>
<tr><td>

### CIOs e Diretores de TI

> *"Uma plataforma substituiu 7 projetos de integração. Nossa equipe finalmente dorme à noite."*

- Camada única de orquestração para todos os sistemas
- Fim das integrações ponto-a-ponto
- Construído em padrões abertos (BPMN, DMN, FHIR R4)

</td></tr>
<tr><td>

### Oficiais de Qualidade e Compliance

> *"Auditoria LGPD? Passamos com zero achados. Tudo é rastreável."*

- Cada interação com o paciente registrada e auditável
- Regras de conformidade aplicadas automaticamente
- Alertas em tempo real para prazos regulatórios

</td></tr>
</table>

---

## 🗺️ As 5 Jornadas do Paciente

O Maestro orquestra a experiência completa do paciente em **5 jornadas interconectadas**:

```
 ① Acesso ──→ ② Cuidado ──→ ③ Continuidade ──→ ④ Relacionamento
                                                        │
                         ⑤ Financeira ══════════════════╧═══════════
                         (permeia todas as etapas)
```

| # | Jornada | Escopo |
|:-:|:--------|:-------|
| 1 | **Acesso** | Do primeiro contato ao paciente pronto para o cuidado |
| 2 | **Cuidado** | Da admissão à alta com desfechos documentados |
| 3 | **Continuidade** | Da pós-alta à estabilização clínica |
| 4 | **Relacionamento** | Da primeira interação à fidelização |
| 5 | **Financeira** | Da verificação de elegibilidade ao recebimento completo |

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│  CANAIS                                                            │
│  WhatsApp  ·  Portal do Paciente  ·  Cockpit  ·  Grafana           │
├─────────────────────────────────────────────────────────────────────┤
│  ORQUESTRAÇÃO                                                      │
│  CIB Seven 2.1.3  ·  BPMN  ·  DMN  ·  CMMN                        │
│  Engine Único  ·  Multi-Tenant  ·  Padrão External Task            │
├─────────────────────────────────────────────────────────────────────┤
│  WORKERS                                                           │
│  Python 3.11  ·  161 processadores stateless                       │
│  elegibilidade · tiss · glosa · whatsapp · clínico · …             │
├─────────────────────────────────────────────────────────────────────┤
│  INTELIGÊNCIA                                                      │
│  667 Tabelas de Decisão DMN                                        │
│  prevenção de glosa · regras de codificação · conformidade         │
├─────────────────────────────────────────────────────────────────────┤
│  INTEGRAÇÃO                                                        │
│  Debezium CDC  ·  Apache Kafka  ·  HAPI FHIR R4                    │
│  Adaptador Tasy  ·  Adaptador MV Soul  ·  Cliente TISS             │
├─────────────────────────────────────────────────────────────────────┤
│  DADOS                                                             │
│  PostgreSQL 16  ·  Redis 7.2  ·  Elasticsearch 8.13                │
├─────────────────────────────────────────────────────────────────────┤
│  INFRAESTRUTURA                                                    │
│  Amazon EKS  ·  Keycloak 24  ·  Prometheus  ·  Grafana 11          │
└─────────────────────────────────────────────────────────────────────┘
```

### Stack Tecnológica

| Camada | Tecnologia | Versão |
|:-------|:-----------|:------:|
| Orquestração | CIB Seven | 2.1.3 |
| Workers | Python | 3.11 |
| Servidor FHIR | HAPI FHIR R4 | 7.4.0 |
| CDC | Debezium | 2.7 |
| Streaming | Apache Kafka | 3.7 |
| Banco de Dados | PostgreSQL | 16 |
| Cache | Redis | 7.2 |
| Busca / Logs | Elasticsearch | 8.13 |
| Identidade | Keycloak | 24 |
| Observabilidade | Prometheus + Grafana | 11 |

---

## 🚀 Início Rápido

### Pré-requisitos

- Docker Desktop (8 GB+ RAM)
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
|:--------|:----|:------------|
| Cockpit (Monitor de Processos) | [localhost:8080/cibseven/app/cockpit](http://localhost:8080/cibseven/app/cockpit) | `admin` / `admin` |
| Tasklist (Tarefas Humanas) | [localhost:8080/cibseven/app/tasklist](http://localhost:8080/cibseven/app/tasklist) | `admin` / `admin` |
| Grafana (Métricas) | [localhost:3000](http://localhost:3000) | `admin` / `admin` |
| HAPI FHIR | [localhost:8082/fhir/metadata](http://localhost:8082/fhir/metadata) | — |
| Keycloak (Identidade) | [localhost:8180/admin](http://localhost:8180/admin) | `admin` / `admin` |

---

## 📁 Estrutura do Repositório

```
maestro/
│
├── healthcare_platform/            # Código principal da plataforma
│   ├── patient_access/             #   23 workers · 6 BPMN
│   ├── clinical_operations/        #   20 workers · DMN clínicos
│   ├── revenue_cycle/              #   89 workers · faturamento e cobrança
│   ├── platform_services/          #   29 workers · conformidade e analytics
│   └── shared/                     #   Multi-tenant · integrações · domínio
│
├── tests/                          # 1.400+ testes (unitários, integração, DMN)
├── docs/                           # ADRs, specs, guias de migração
├── config/                         # Observabilidade (Prometheus, Grafana)
└── scripts/                        # Ferramentas de deploy e migração
```

---

## 📚 Documentação

| Documento | Descrição |
|:----------|:----------|
| [Especificação Técnica](docs/Technical%20specification/technical-specification.md) | Arquitetura completa do sistema |
| [ADRs](docs/ADRs/) | 13 Registros de Decisão de Arquitetura |
| [Guia de Migração](docs/Migration/) | Migração de sistemas legados |
| [Regras de Negócio](docs/Regras%20de%20Negocio%20(PT-BR)/) | Inventário completo de regras |

---

## 📄 Licença

| Componente | Licença |
|:-----------|:--------|
| CIB Seven Engine | Apache License 2.0 |
| Plataforma Maestro | Proprietária |

---

<p align="center">
  <strong>Maestro</strong><br/>
  <em>Saúde em harmonia.</em><br/><br/>
  Desenvolvido pelo <strong>Grupo AUSTA</strong> · São José do Rio Preto, SP
</p>
