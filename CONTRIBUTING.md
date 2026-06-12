# CONTRIBUTING — Como Adicionar uma Nova "Caixinha"

> Este guia explica como adicionar novas regras, fluxos, integrações e domínios ao MAEZO.
> Leia antes: [PROJECT.md](PROJECT.md) | [MAP.md](MAP.md)

---

## Índice

1. [Novo Worker (regra + ação)](#1-novo-worker)
2. [Nova Tabela DMN (regra de negócio)](#2-nova-tabela-dmn)
3. [Novo Processo BPMN (fluxo)](#3-novo-processo-bpmn)
4. [Nova Integração Externa](#4-nova-integração-externa)
5. [Novo Domínio (Bounded Context)](#5-novo-domínio)
6. [Convenções de Nomenclatura](#6-convenções-de-nomenclatura)
7. [Checklist antes do PR](#7-checklist-antes-do-pr)

---

## 1. Novo Worker

Um worker executa uma tarefa do processo BPMN (External Task Pattern). Na maioria dos casos, apenas delega para uma tabela DMN.

### Passo a Passo

**1.1 Identificar o domínio:**

| Prefixo do tópico | Domínio | Pasta |
|-------------------|---------|-------|
| `validate_`, `authorize_`, `check_eligibility_*` | Revenue Cycle | `src/healthcare_platform/revenue_cycle/` |
| `detect_`, `assess_`, `monitor_`, `clinical_*` | Clinical Operations | `src/healthcare_platform/clinical_operations/workers/` |
| `schedule_`, `admit_`, `identify_`, `patient_*` | Patient Access | `src/healthcare_platform/patient_access/workers/` |
| `compliance_`, `credential_`, `analytics_*` | Platform Services | `src/healthcare_platform/platform_services/workers/` |

**1.2 Criar o arquivo do worker:**

```
src/healthcare_platform/{dominio}/workers/{nome}_worker.py
```

**1.3 Template mínimo (archetype DMN — 80% dos casos):**

```python
"""Worker para [descrição do que faz].

Topic: {nome_do_topico}
Archetype: {ADMIN_ADJUDICATION | CLINICAL_ALERT | CLINICAL_SCORE |
            OPERATIONAL_ROUTING | COMPLIANCE_VALIDATION |
            FINANCIAL_CALCULATION | DATA_ENRICHMENT}
DMN: {chave_da_tabela_dmn}
"""
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker


class NomeFuncionalidadeWorker(BaseExternalTaskWorker):
    topic = "nome_do_topico"  # deve existir em config/topic_registry.yaml

    async def execute(self, task):
        result = await self.evaluate_dmn(
            "chave_da_tabela_dmn",
            input_vars=task.variables,
        )
        return result
```

**1.4 Registrar o tópico em `config/topic_registry.yaml`:**

```yaml
topics:
  nome_do_topico:
    archetype: ADMIN_ADJUDICATION       # Um dos 7 archetypes
    dmn_key: chave_da_tabela_dmn        # Chave da tabela no CIB Seven
    dmn_category: global                # global ou tenant (override por hospital)
    input_map:
      variavel_bpmn: parametro_dmn      # Mapeamento variáveis BPMN → input DMN
    output_map:
      resultado_dmn: variavel_bpmn_out  # Mapeamento output DMN → variáveis BPMN
    error_strategy: fail_closed         # fail_closed (bloqueia) ou fail_safe (continua)
    timeout_ms: 30000                   # Lock duration (ms)
    retry_backoff: exponential          # Estratégia de retry
```

**1.5 Criar teste:**

```
tests/unit/{dominio}/test_{nome}_worker.py
```

```python
import pytest
from unittest.mock import AsyncMock, patch
from healthcare_platform.{dominio}.workers.{nome}_worker import NomeFuncionalidadeWorker

@pytest.mark.asyncio
async def test_nome_funcionalidade_worker_happy_path():
    worker = NomeFuncionalidadeWorker()
    task = AsyncMock()
    task.variables = {"patientId": "PAT-001", "payerId": "UNIMED"}

    with patch.object(worker, "evaluate_dmn", return_value={"eligible": True}) as mock_dmn:
        result = await worker.execute(task)

    mock_dmn.assert_called_once_with("chave_da_tabela_dmn", input_vars=task.variables)
    assert result["eligible"] is True
```

---

## 2. Nova Tabela DMN

Uma tabela DMN define regras de negócio de forma declarativa (sem código Python).

### Onde criar

```
# Regra global (mesma para todos os hospitais):
src/healthcare_platform/{dominio}/dmn/{subcategoria}/{nome}_{NNN}.dmn

# Regra específica por tenant (hospital):
src/healthcare_platform/{dominio}/dmn/{subcategoria}/tenant_{hospital-id}/{nome}_{NNN}.dmn
```

### Naming convention

```
{categoria}_{subcategoria}_{NNN}.dmn

Exemplos:
  eligibility_unimed_003.dmn      # Elegibilidade Unimed, tabela 3
  syn_aki_007.dmn                 # Síndrome AKI, tabela 7
  ddi_hepato_004.dmn              # DDI hepatotóxico, tabela 4
  compliance_tiss_002.dmn         # Compliance TISS 4.0, tabela 2
```

### Número sequencial (NNN)

Sempre verificar o último número usado na subcategoria antes de criar:

```bash
ls src/healthcare_platform/{dominio}/dmn/{subcategoria}/ | sort | tail -3
```

### Referenciar no topic_registry.yaml

```yaml
topics:
  meu_topico:
    dmn_key: eligibility_unimed_003    # Nome do arquivo sem .dmn
    # OU para pipeline de múltiplas tabelas:
    dmn_pipeline:
      - vital_signs_assessment
      - qsofa_scoring
      - sepsis_risk_classification
```

---

## 3. Novo Processo BPMN

Um processo BPMN define um fluxo de trabalho completo.

### Onde criar

```
src/healthcare_platform/{dominio}/bpmn/SP-{DOMINIO}-{NNN}_{Titulo}.bpmn
```

### Naming convention

```
SP-{DOMINIO}-{NNN}_{Titulo_Em_Palavras}.bpmn

Prefixos de domínio:
  SP-CO-NNN   Clinical Operations
  SP-RC-NNN   Revenue Cycle
  SP-PA-NNN   Patient Access
  SP-PS-NNN   Platform Services

Exemplos:
  SP-CO-013_Medication_Safety_Check.bpmn
  SP-RC-009_Glosa_Appeal_Process.bpmn
  SP-PA-006_Emergency_Fast_Track.bpmn
```

### Número sequencial (NNN)

```bash
ls src/healthcare_platform/{dominio}/bpmn/ | sort | tail -3
```

### Regras obrigatórias para BPMN (ADR-019)

1. **Namespace:** usar `camunda:` (não `zeebe:`)
2. **Service Tasks:** cada um deve ter um `topic` que existe em `topic_registry.yaml`
3. **Tenant:** todas as variáveis devem incluir `tenantId` (nunca hardcodar)
4. **Error events:** sempre definir boundary events para erros críticos
5. **Validar antes de commit:**
   ```bash
   python scripts/validate/validate_bpmn_worker_connectivity.py
   ```

---

## 4. Nova Integração Externa

Integrações externas ficam em `src/healthcare_platform/shared/integrations/`.

### Onde criar

```
src/healthcare_platform/shared/integrations/{sistema}_client.py
```

### Template

```python
"""Cliente de integração com {Sistema}.

Documentação: docs/integrations/{sistema}.md
"""
import httpx
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


class SistemaClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def get_dados(self, id: str) -> dict:
        resp = await self._client.get(f"/endpoint/{id}")
        resp.raise_for_status()
        return resp.json()
```

### Adicionar variável de ambiente

Em `.env.example`:
```bash
SISTEMA_API_URL=https://api.sistema.com
SISTEMA_API_KEY=changeme
```

Em `docker-compose.swarm.yml` (nos workers relevantes):
```yaml
environment:
  SISTEMA_API_URL: ${SISTEMA_API_URL}
  SISTEMA_API_KEY_FILE: /run/secrets/sistema_api_key
```

---

## 5. Novo Domínio

Para adicionar um novo bounded context (área de negócio completa).

### 5.1 Criar estrutura de pastas

```bash
mkdir -p src/healthcare_platform/{novo_dominio}/{bpmn,dmn,workers,services,tests}
touch src/healthcare_platform/{novo_dominio}/__init__.py
touch src/healthcare_platform/{novo_dominio}/workers/__init__.py
```

### 5.2 Definir prefixo de tópicos

Escolher um prefixo único e documentar em `config/topic_registry.yaml`:

```yaml
# Adicionar seção para o novo domínio
# Prefixo: {sigla}_*
# Exemplos: nd_* (Nursing Documentation), lm_* (Lab Management)
```

### 5.3 Adicionar ao docker-compose.swarm.yml

```yaml
workers_{sigla}:
  image: ${IMAGE_WORKERS}:${IMAGE_TAG}
  environment:
    WORKER_DOMAIN: {novo_dominio}
    CIB7_BASE_URL: http://cib7:8080/engine-rest
    CIB7_USER: ${CIB7_USER}
    CIB7_PASSWORD_FILE: /run/secrets/cib7_admin_password
    DATABASE_URL: postgresql://${RDS_USER}@${RDS_HOST}:5432/maestro
  secrets: [cib7_admin_password, postgres_password]
  networks: [maestro_net]
  deploy:
    replicas: 1
    stop_grace_period: 90s
```

### 5.4 Atualizar documentação

- Adicionar linha em [MAP.md](MAP.md) — seção Domínios
- Adicionar seção em [PROJECT.md](PROJECT.md) — tabela de Domínios
- Criar `docs/adr/0{NNN}-{descricao}.md` se houver decisão arquitetural nova

---

## 6. Convenções de Nomenclatura

### Arquivos Python (workers)
```
{descricao_snake_case}_worker.py
```

### Arquivos DMN
```
{categoria}_{subcategoria}_{NNN:03d}.dmn
```

### Arquivos BPMN
```
SP-{DOMINIO}-{NNN:03d}_{Titulo_Capitalizado}.bpmn
```

### Tópicos (topics) em topic_registry.yaml
```
{verbo}_{objeto}           → validate_eligibility
{dominio}_{acao}           → clinical_assessment
{categoria}_{subcategoria} → sepsis_detection
```

### Variáveis BPMN
```
camelCase, sem prefixo de domínio
tenantId, patientFhirId, encounterFhirId, claimFhirId
NÃO usar: tenant_id, TENANT_ID, hospitalCode (hardcoded)
```

### Schemas DMN
```
Inputs:  camelCase (igual às variáveis BPMN)
Outputs: camelCase descritivo (eligible, riskLevel, actionRequired)
```

---

## 7. Checklist antes do PR

```
[ ] Worker criado em src/healthcare_platform/{dominio}/workers/
[ ] Tópico registrado em config/topic_registry.yaml
[ ] Tabela DMN criada (se nova) com naming correto
[ ] BPMN criado (se novo) com naming correto
[ ] Teste unitário criado em tests/unit/{dominio}/
[ ] Validações passando:
    - python scripts/validate/validate_bpmn_worker_connectivity.py
    - python scripts/validate/validate_dmn.py
    - python scripts/validate/validate_tenant_isolation.py
[ ] Testes passando:
    - pytest tests/unit/ -v
[ ] Sem CPF/email hardcoded em BPMN/DMN (PII scan)
[ ] tenantId sempre como variável (nunca hardcoded)
[ ] MAP.md atualizado (se nova pasta criada)
```
