# MAP — Mapa do Projeto MAEZO

> Guia de navegação: onde está cada tipo de arquivo no projeto.
> Para entender o projeto, leia primeiro: [PROJECT.md](PROJECT.md)

---

## Estrutura Raiz

```
Healthcare-Orchest-CIB7/
│
├── PROJECT.md                   ← O que é o MAEZO, arquitetura, como iniciar
├── MAP.md                       ← Este arquivo: onde está cada coisa
├── CONTRIBUTING.md              ← Como adicionar workers, DMN, BPMN, domínios
├── README.md                    ← Resumo rápido
│
├── pyproject.toml               ← Dependências Python + config pytest/ruff/mypy
├── .env.example                 ← Template de variáveis de ambiente
├── .gitignore
├── .dockerignore
│
├── Dockerfile                   ← Imagem base (workers RC, CO, PA, PS)
├── Dockerfile.worker            ← Imagem workers com entrypoint configurado
├── Dockerfile.contract-extraction ← Imagem FastAPI contract extraction
├── docker-compose.swarm.yml     ← Stack Docker Swarm completo (11 serviços)
│
├── src/                         ← CÓDIGO PRINCIPAL (único source of truth)
├── config/                      ← Configuração declarativa
├── tests/                       ← Suite de testes
├── scripts/                     ← Utilitários para desenvolvedores
├── docs/                        ← Documentação técnica
└── .github/workflows/           ← CI/CD (GitHub Actions)
```

---

## `src/` — Código Principal

```
src/healthcare_platform/
│
├── __init__.py
│
├── clinical_operations/              ← Domínio CO: Operações Clínicas
│   ├── __init__.py
│   ├── bpmn/                         ← Processos BPMN (SP-CO-NNN_*.bpmn)
│   │   ├── SP-CO-001_Triage_Clinical_Routing.bpmn
│   │   ├── SP-CO-002_Admission_Bed_Management.bpmn
│   │   ├── SP-CA-001_Sepsis_Detection.bpmn
│   │   └── ... (14+ arquivos)
│   ├── dmn/                          ← Tabelas DMN de regras clínicas
│   │   ├── clinical_safety/
│   │   │   ├── aki/                  ← Lesão renal aguda (AKI scoring)
│   │   │   ├── allergy/              ← Triagem de alergias
│   │   │   ├── bleed/                ← Risco de sangramento
│   │   │   ├── cardiac/              ← Monitoramento cardíaco
│   │   │   ├── ddi/                  ← Interações medicamentosas
│   │   │   │   ├── bleed/, hepato/, major/, moderate/, nephro/, qt/, serotonin/
│   │   │   ├── ddx/                  ← Diagnóstico diferencial
│   │   │   │   ├── allergy/, cardiac/, neuro/, renal/, respiratory/
│   │   │   ├── analytics/, cds/, compliance/, contraind/, critical/, cross_cutting/
│   │   ├── surgical/                 ← Regras de centro cirúrgico
│   │   └── doctor_patient/           ← Interação médico-paciente
│   ├── workers/                      ← Workers Python (External Task)
│   │   ├── adverse_event_detection_worker.py
│   │   ├── care_planning_worker.py
│   │   ├── detect_sepsis_worker.py
│   │   └── ... (50+ workers)
│   ├── services/                     ← Serviços auxiliares Python
│   └── tests/                        ← Testes do domínio CO
│
├── revenue_cycle/                    ← Domínio RC: Ciclo de Receita
│   ├── __init__.py
│   ├── bpmn/                         ← Processos BPMN de faturamento
│   ├── dmn/                          ← Regras DMN de receita
│   ├── workers/                      ← Workers RC (nível domínio)
│   ├── billing/                      ← Subdomain: Faturamento
│   │   ├── bpmn/, dmn/, workers/
│   ├── coding/                       ← Subdomain: Codificação médica
│   │   ├── bpmn/, dmn/, workers/
│   ├── glosa/                        ← Subdomain: Gestão de glosa
│   │   ├── bpmn/, dmn/, workers/
│   ├── production/                   ← Subdomain: Produção hospitalar
│   │   ├── bpmn/, dmn/, workers/
│   ├── collection/                   ← Subdomain: Cobrança
│   └── services/
│
├── patient_access/                   ← Domínio PA: Acesso do Paciente
│   ├── __init__.py
│   ├── bpmn/                         ← Processos BPMN de acesso
│   ├── dmn/                          ← Regras de autorização, identificação
│   │   ├── authorization/, identification/, scheduling/
│   ├── workers/                      ← Workers PA
│   ├── engagement/                   ← Subdomain: Engajamento
│   │   └── workers/
│   ├── registration/                 ← Subdomain: Registro/admissão
│   │   └── workers/
│   ├── scheduling/                   ← Subdomain: Agendamento
│   │   └── workers/
│   └── tests/
│
├── platform_services/                ← Domínio PS: Serviços de Plataforma
│   ├── __init__.py
│   ├── bpmn/                         ← Processos BPMN plataforma
│   ├── dmn/                          ← Regras de compliance, analytics
│   │   ├── analytics/, compliance/, communication/, credentialing/
│   ├── workers/                      ← Workers PS
│   ├── analytics/                    ← Subdomain: Analytics
│   │   └── workers/
│   ├── integration/                  ← Subdomain: Integrações externas
│   │   └── workers/
│   ├── revenue_optimization/         ← Subdomain: Otimização de receita
│   │   └── workers/
│   ├── services/
│   └── tests/
│
├── contract_extraction/              ← Domínio CE: Extração de Contratos
│   ├── __init__.py
│   ├── app.py                        ← FastAPI app (ce_api)
│   ├── router.py, models.py, schemas.py, validators.py
│   ├── dmn_generator.py              ← Gera DMN a partir de contratos
│   ├── feel_compiler.py              ← Compilador FEEL 1.3
│   ├── extraction/
│   │   ├── extractor.py              ← Pipeline de extração
│   │   ├── clause_parser.py          ← Parser de cláusulas
│   │   └── builders/                 ← Builders por tipo de regra
│   │       ├── authorization_builder.py
│   │       ├── pricing_builder.py
│   │       ├── glosa_builder.py
│   │       └── ... (8 builders)
│   ├── dmn_templates/                ← Templates Jinja2 para DMN
│   ├── migrations/                   ← Migrações de banco
│   └── tests/
│
└── shared/                           ← Código compartilhado entre domínios
    ├── workers/
    │   ├── base.py                   ← BaseExternalTaskWorker (herdar aqui)
    │   ├── registry.py               ← Auto-discovery de workers
    │   └── runner.py                 ← Event loop + CLI
    ├── integrations/
    │   ├── tasy_api_client.py        ← Cliente REST Tasy ERP
    │   ├── tasy_adapters/            ← Adaptadores FHIR para dados Tasy
    │   ├── fhir_service.py           ← Cliente HAPI FHIR R4
    │   ├── tiss_client.py            ← TISS (operadoras)
    │   ├── lis_client.py             ← LIS (laboratório)
    │   └── ... (10+ clientes)
    ├── webhooks/
    │   ├── app.py                    ← FastAPI webhook receiver
    │   ├── handlers/                 ← Handlers por sistema externo
    │   └── security/
    │       ├── idempotency.py        ← Deduplicação via PostgreSQL
    │       └── jwt_validator.py
    ├── cdc_bridge/                   ← CDC: consome Kafka → inicia processo no CIB Seven
    │   ├── kafka_consumer.py
    │   └── process_mapper.py
    ├── domain/
    │   ├── entities.py               ← Entidades de domínio (dataclasses)
    │   ├── enums.py                  ← Enums compartilhados
    │   ├── events.py                 ← Eventos de domínio
    │   └── exceptions.py            ← Exceções customizadas
    ├── dmn/                          ← Serviço DMN (federation + tenant resolver)
    ├── observability/
    │   ├── logging.py                ← structlog + OpenTelemetry
    │   └── metrics.py                ← Métricas customizadas
    └── runtime/
        └── worker_runner.py          ← Entrypoint para containers de workers
```

---

## `config/` — Configuração Declarativa

```
config/
├── correlation_keys.yaml    ← Chaves de correlação entre processos inter-domínio
│                              (ex: patientFhirId, encounterFhirId, tenantId)
├── topic_registry.yaml      ← Registry master de todos os 400+ workers
│                              (archetype, dmn_key, input/output map, retry policy)
├── postgres/
│   └── init-swarm.sql       ← Bootstrap do RDS: schemas, tabelas, pg_cron
└── debezium/
    └── oracle-connector.json ← Conector CDC Debezium → Oracle Tasy
```

---

## `tests/` — Suite de Testes

```
tests/
├── conftest.py              ← Fixtures compartilhadas (banco, CIB7 mock, FHIR mock)
├── pytest.ini               ← Configuração pytest (markers, asyncio mode)
├── unit/                    ← Testes unitários (sem dependências externas)
│   ├── clinical_operations/
│   ├── revenue_cycle/
│   ├── patient_access/
│   └── platform_services/
├── dmn/                     ← Testes de tabelas DMN (validação FEEL)
├── integration/             ← Testes de integração (requerem banco PostgreSQL)
├── smoke/                   ← Smoke tests (verificação básica de serviços)
└── fixtures/                ← Dados de teste (JSON, FHIR resources)
```

---

## `scripts/` — Utilitários de Desenvolvimento

### `scripts/deploy/` — Implantação
| Script | O que faz | Quando usar |
|--------|-----------|-------------|
| `bootstrap.sh` | Orquestra todo o bootstrap pós-deploy (BPMN + Kafka) | Após `docker stack deploy` |
| `deploy_swarm.sh` | Deploy completo do Docker Swarm com validações | Release em produção |
| `deploy_processes.py` | Deploya BPMN/DMN no CIB Seven via REST API | Parte do bootstrap |
| `create_kafka_topics.sh` | Cria tópicos Kafka CDC (`tasy.{tenant}.{table}`) | Parte do bootstrap |

### `scripts/validate/` — Validação / Lint
| Script | O que faz | Quando usar |
|--------|-----------|-------------|
| `validate_bpmn_worker_connectivity.py` | Valida que todos os topics nos BPMN existem em `topic_registry.yaml` | Antes de PR |
| `validate_dmn.py` | Valida sintaxe FEEL 1.3 em todas as tabelas DMN | CI/CD + antes de PR |
| `validate_tenant_isolation.py` | Verifica que não há tenant hardcoded em variáveis BPMN | Compliance LGPD |
| `bpmn_pre_commit_hook.sh` | Hook pré-commit que valida BPMN | Setup do repo |

### `scripts/dev/` — Desenvolvimento Local
| Script | O que faz | Quando usar |
|--------|-----------|-------------|
| `start_local.sh` | Sobe stack local completo (Docker Compose) | Desenvolvimento |
| `run_e2e_tests.sh` | Executa suite E2E contra stack local | Validação pré-PR |
| `smoke_test.sh` | Smoke test rápido contra qualquer ambiente | Pós-deploy |

### `scripts/generate/` — Geração / Manutenção
| Script | O que faz | Quando usar |
|--------|-----------|-------------|
| `dmn_inventory.py` | Gera catálogo JSON de todos os arquivos DMN | Documentação |
| `dmn_tenant_resolver.py` | Resolve qual DMN usar (global vs tenant-override) | Debug de regras |
| `generate_surgery_dmn.py` | Gera DMN para novos procedimentos cirúrgicos | Adicionar cirurgia |
| `generate_payment_mapping_docx.py` | Gera matriz operadora × código × preço | Contratos |
| `add_glosa_methods.py` | Injeta novos métodos no cliente Tasy (glosa) | Evolução integração |
| `fix_dmn_schema.py` | Corrige incompatibilidades XSD em DMN legados | Importação de DMN |

---

## `docs/` — Documentação Técnica

```
docs/
├── adr/                            ← Decisões Arquiteturais (Architecture Decision Records)
│   ├── 001-cib7-as-bpm-engine.md
│   ├── 002-single-engine-tenant.md
│   ├── 003-python-external-task-workers.md
│   ├── 004-debezium-cdc.md
│   ├── 005-hapi-fhir-r4.md
│   ├── 006-kafka-rest-bridge.md
│   ├── 007-dmn-federation-tenant-overrides.md
│   ├── 009-mono-repo-folder-per-concern.md
│   ├── 010-observability-stack.md
│   ├── 011-lgpd-history-ttl.md
│   ├── 012-engine-replicas-phased.md
│   ├── 013-claude-flow-swarm.md
│   ├── 014-webhook-receivers.md
│   ├── 015-worker-archetypes-dmn-delegation.md
│   ├── 016-topic-naming-convention.md
│   ├── 017-anti-pattern-enforcement.md
│   ├── 018-atomization-blueprint.md
│   ├── 019-bpmn-compliance-mandatory.md
│   └── 020-basic-auth-sem-keycloak.md
├── architecture/                   ← Arquitetura visual + especificações técnicas
│   ├── MAEZO-Arquitetura-2026.html ← Arquitetura visual interativa (v2.2)
│   └── technical-specification/    ← Especificações técnicas detalhadas
├── migration/                      ← Guias de migração V1→V2
│   ├── CIB7_WORKER_TEMPLATE.md    ← Template para novos workers
│   ├── QUICK_START_GUIDE.md       ← Getting started rápido
│   └── MIGRATION_SUMMARY.md       ← Resumo da migração concluída
├── handoffs/                       ← Handoffs entre sessões de desenvolvimento
│   └── HANDOFF.yaml               ← Estado atual do projeto (ler primeiro)
├── pending/                        ← Tarefas pendentes para desenvolvedores
│   └── pendencias-desenvolvedores.md
├── runbooks/                       ← Operações de produção
│   ├── DEPLOYMENT.md
│   ├── OPERATIONS.md
│   └── INCIDENT_RESPONSE.md
├── integrations/                   ← Documentação de integrações externas
│   ├── tasy-integration.md
│   ├── fhir-mapping.md
│   └── tiss-4-0.md
├── implementation/                 ← Guias de implementação BPMN
├── audit/                          ← Relatórios de auditoria de swarms
└── archive/                        ← Documentação histórica (não usar para referência)
    ├── ADR-008-keycloak-superseded.md
    ├── workers-v0/                  ← Workers V0 (deprecated)
    └── bpmn-v0/                    ← BPMN antigos (deprecated)
```

---

## Achando um Arquivo Específico

### "Quero encontrar o worker de [funcionalidade]"
```bash
find src/ -name "*{palavra}*_worker.py"
# Exemplo: find src/ -name "*sepsis*"
```

### "Quero encontrar a regra DMN de [categoria]"
```bash
find src/ -name "*.dmn" | grep "{palavra}"
# Exemplo: find src/ -name "*.dmn" | grep "aki"
# Ou: python scripts/generate/dmn_inventory.py | grep "aki"
```

### "Quero encontrar o processo BPMN de [domínio]"
```bash
find src/ -name "*.bpmn"
# Exemplo por domínio:
find src/healthcare_platform/revenue_cycle -name "*.bpmn"
```

### "Quero encontrar o tópico [nome] no registry"
```bash
grep -A 10 "topic_name:" config/topic_registry.yaml
```

### "Quero ver todas as correlações entre processos"
```bash
cat config/correlation_keys.yaml
```
