# MAEZO — Motor de Automação de Ecossistemas e Orquestração

> Plataforma BPM enterprise para orquestração de fluxos hospitalares.
> Stack: **Docker Swarm · AWS RDS PostgreSQL 16 · CIB Seven 2.1.3 · HAPI FHIR R4 · Apache Kafka**

---

## O que é o MAEZO?

O MAEZO é a plataforma de automação da Austa Healthcare. Ele orquestra os processos de negócio do hospital usando um motor BPM (CIB Seven, fork do Camunda 7), integrando sistemas externos como o ERP Tasy, operadoras de saúde, e plataformas FHIR.

**Em uma frase:** cada ação clínica, financeira ou administrativa que precisa de decisão automatizada passa pelo MAEZO.

---

## Domínios de Negócio

| Sigla | Nome | O que faz | Pasta |
|-------|------|-----------|-------|
| **CO** | Clinical Operations | Triagem, leito, alertas clínicos, medicação, cirurgia | `src/healthcare_platform/clinical_operations/` |
| **RC** | Revenue Cycle | Faturamento, codificação, glosa, cobrança, produção | `src/healthcare_platform/revenue_cycle/` |
| **PA** | Patient Access | Agendamento, admissão, identificação, engajamento | `src/healthcare_platform/patient_access/` |
| **PS** | Platform Services | Compliance, analytics, credenciamento, integração | `src/healthcare_platform/platform_services/` |
| **CE** | Contract Extraction | Extração automática de regras de contratos em DMN | `src/healthcare_platform/contract_extraction/` |

---

## Arquitetura em 30 segundos

```
Tasy ERP (Oracle)
    │ CDC via Debezium
    ▼
Apache Kafka ──► cdc_bridge (Python: Kafka → CIB Seven)
                     ├── inicia processo BPMN
                     └── roteamento por tenant (extraído do tópico)

CIB Seven BPM Engine
    ├── Executa 59 processos BPMN
    ├── Avalia 1.274+ tabelas DMN
    └── External Task Pattern:
            ├── Workers Python fazem fetchAndLock()
            ├── Executam lógica (geralmente: evaluate_dmn())
            └── Completam ou reportam erro

HAPI FHIR R4 ← fhir_sync normaliza dados para padrão FHIR

Webhooks (FastAPI em src/healthcare_platform/shared/webhooks/)
    ├── Recebe callbacks de operadoras (APAC, PIX, CNES)
    ├── Valida HMAC + idempotência (PostgreSQL)
    └── Correlaciona mensagem no processo CIB Seven correspondente
    Nota: módulo existe mas não tem service no docker-compose atual.

AWS RDS PostgreSQL 16
    ├── Schema cibseven    — estado do motor BPM
    ├── Schema hapi_fhir   — recursos FHIR R4
    └── Schema maestro     — dados de negócio, idempotência, dead-letter
```

---

## Stack Técnico

| Componente | Tecnologia | Versão | Porta |
|------------|-----------|--------|-------|
| BPM Engine | CIB Seven | 2.1.3 | 8080 |
| FHIR Store | HAPI FHIR | R4 v7.4.0 | 8080 (interno) |
| Streaming | Apache Kafka KRaft | 7.7.0 | 9092 |
| CDC Connector | Debezium Oracle | 2.7 | 8083 |
| Workers | Python | 3.11+ | — |
| Banco de dados | AWS RDS PostgreSQL | 16 | 5432 |
| Proxy/SSL | Traefik | v3.0 | 443/80 |
| Contract API | FastAPI (ce_api) | — | 8000 |

**Autenticação:** Basic Auth (CIB Seven) — sem Keycloak (ADR-020)
**Multi-tenant:** tenant extraído do tópico Kafka + path `/tenant-id/{id}` (CIB Seven)

**Organização de tenants no CIB Seven (por domínio e projeto):**
| Tenant | Domínio | Projeto |
|--------|---------|---------|
| `Maezo_rc` | Revenue Cycle | MAEZO |
| `Maezo_co` | Clinical Operations | MAEZO |
| `Maezo_pa` | Patient Access | MAEZO |
| `Maezo_ps` | Platform Services | MAEZO |
| `Maezo_ce` | Contract Extraction | MAEZO |

Para um segundo projeto, usar `--tenant-prefix ZZ` → gera `ZZ_rc`, `ZZ_co`, etc.

---

## Workers — Como Funcionam

Os workers Python rodam em containers e implementam o padrão **External Task** do CIB Seven:

```
                    CIB Seven                Workers Python
                    ─────────                ──────────────
Processo BPMN chega a um Service Task
                 │
                 ▼
         fetchAndLock(topic)  ◄──────  Worker faz polling (cada 5s)
                 │
                 ▼
         Worker recebe tarefa
                 │
                 ▼
         evaluate_dmn("chave_dmn")  ──► Consulta tabela DMN no CIB Seven
                 │
                 ▼
         Resultado das regras
                 │
                 ▼
         complete(variables)  ──────►  Processo avança
```

**80% das regras não precisam de Python.** O worker apenas delega para DMN:

```python
class EligibilityWorker(BaseExternalTaskWorker):
    topic = "validate_eligibility"

    async def execute(self, task):
        result = await self.evaluate_dmn(
            "eligibility_authorization_matrix",
            input_vars=task.variables
        )
        return result
```

---

## Convenções de Nomenclatura

### BPMN
```
SP-{DOMINIO}-{NNN}_{Titulo_Snake}.bpmn
Exemplos:
  SP-CO-001_Triage_Clinical_Routing.bpmn
  SP-RC-003_Billing_Submission.bpmn
  SP-PA-001_Patient_Registration.bpmn
```

### DMN
```
{categoria}_{subcategoria}_{NNN}.dmn
Exemplos:
  syn_aki_006.dmn          (síndrome AKI, tabela 6)
  ddi_bleed_008.dmn        (interação medicamentosa, sangramento)
  eligibility_matrix_001.dmn
```

O atributo `name` de cada decisão segue o padrão de rastreabilidade:
```
[SP-RC-00X | subdominio/pasta] Nome da Decisão
Exemplos:
  [SP-RC-006 | billing/submission] Verificar Submissão TISS
  [SP-RC-007 | glosa_prevention/duplicate] Verificar Componente Bundle
  [SP-RC-005 | coding_audit/fraud_scoring] Fraud Score 001
```
Isso permite localizar no Cockpit do CIB Seven todas as decisões de um processo
filtrando pelo código `SP-RC-00X` na coluna Name.

### Workers (arquivos Python)
```
{descricao_snake}_worker.py
Exemplos:
  validate_eligibility_worker.py
  detect_sepsis_worker.py
  apply_contract_rules_worker.py
```

### Tópicos Kafka (topics)
```
{dominio}_{acao}
Exemplos:
  validate_eligibility
  detect_sepsis
  apply_glosa_rules
  enrich_patient_fhir
```

---

## Como Rodar Localmente (Dev)

```bash
# 1. Clonar e configurar ambiente
git clone <repo>
cd Healthcare-Orchest-CIB7
cp .env.example .env
# Editar .env com valores locais (usar localhost no lugar de RDS_HOST)

# 2. Instalar dependências Python
pip install -e ".[dev]"

# 3. Subir infraestrutura local (apenas dev — não usar em produção)
# CIB Seven + PostgreSQL local
docker run -d --name cib7-local \
  -e CIBSEVEN_BPM_ADMIN_USER=admin \
  -e CIBSEVEN_BPM_ADMIN_PASSWORD=admin \
  -p 8080:8080 \
  cibseven/cibseven-bpm-platform:2.1.3

# 4. Deploy de processos no CIB Seven (script unificado)
# Deploy completo de um domínio com tenant:
python scripts/deploy/deploy_processes.py \
  --url http://localhost:8080/engine-rest \
  --domain revenue_cycle \
  --tenant-prefix Maezo

# Limpar engine e republicar apenas BPMNs de um domínio:
python scripts/deploy/deploy_processes.py \
  --url http://localhost:8080/engine-rest \
  --clean --domain revenue_cycle --bpmn-only --tenant-prefix Maezo

# Flags disponíveis:
#   --domain <nome>         filtra por domínio (revenue_cycle, clinical_operations, ...)
#   --tenant-prefix <proj>  prefixo do tenant (Maezo → Maezo_rc, Maezo_co, ...)
#   --clean                 remove todos os deployments antes de publicar
#   --bpmn-only / --dmn-only  publica apenas BPMN ou apenas DMN
#   --dry-run               lista o que seria publicado sem enviar

# 5. Rodar workers de um domínio
CIB7_USER=admin CIB7_PASSWORD=admin \
python -m healthcare_platform.shared.runtime.worker_runner \
  --domain revenue_cycle

# 6. Rodar testes
pytest tests/ -v -m "not requires_engine"
```

---

## Deploy Produção (Docker Swarm)

```bash
# 1. Criar Docker Swarm secrets
echo "$RDS_PASSWORD"       | docker secret create postgres_password -
echo "$CIB7_ADMIN_PASS"    | docker secret create cib7_admin_password -

# 2. Gerar CLUSTER_ID válido para Kafka KRaft
export KAFKA_CLUSTER_ID=$(docker run --rm confluentinc/cp-kafka:7.7.0 \
  kafka-storage random-uuid)

# 3. Exportar variáveis de ambiente
export RDS_HOST=maezo.xxxx.us-east-1.rds.amazonaws.com
export RDS_USER=maestro
export CIB7_USER=admin
export DOMAIN=austa.com.br
export IMAGE_TAG=$(git rev-parse --short HEAD)

# 4. Deploy
docker stack deploy -c docker-compose.swarm.yml maestro

# 5. Verificar
docker service ls

# 6. Registrar conector Debezium (após ~60s)
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @config/debezium/oracle-connector.json
```

---

## Documentação Adicional

| Documento | O que é |
|-----------|---------|
| [MAP.md](MAP.md) | Mapa completo: onde está cada arquivo |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Como adicionar workers, DMN, BPMN, domínios |
| [docs/architecture/MAEZO-Arquitetura-2026.html](docs/architecture/MAEZO-Arquitetura-2026.html) | Arquitetura visual interativa |
| [docs/adr/](docs/adr/) | 20 decisões arquiteturais (ADRs) |
| [config/topic_registry.yaml](config/topic_registry.yaml) | Registry de todos os 400+ workers/topics |
| [config/correlation_keys.yaml](config/correlation_keys.yaml) | Chaves de correlação inter-processo |

---

*MAEZO Healthcare Platform · Austa Healthcare · Confidencial*
