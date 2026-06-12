# FHIR Sync Service — Padrão Arquitetural Completo

> **Objetivo:** Documentar o padrão end-to-end para sincronização de dados do ERP Tasy (Oracle) para HAPI FHIR R4, incluindo CDC via Debezium, transformações Avro, adapters Python e escrita idempotente no FHIR.

## Índice

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Fluxo de Dados End-to-End](#2-fluxo-de-dados-end-to-end)
3. [Componentes e Responsabilidades](#3-componentes-e-responsabilidades)
4. [Padrão de Criação de Novo Adapter](#4-padrão-de-criação-de-novo-adapter)
5. [Padrão de Adição de Nova Tabela](#5-padrão-de-adição-de-nova-tabela)
6. [Descobrir Colunas Oracle (via Avro Schema)](#6-descobrir-colunas-oracle-via-avro-schema)
7. [Padrões de Mapeamento](#7-padrões-de-mapeamento)
8. [Debugging e Troubleshooting](#8-debugging-e-troubleshooting)
9. [Checklist para PR de Novo Recurso FHIR](#9-checklist-para-pr-de-novo-recurso-fhir)

---

## 1. Visão Geral da Arquitetura

```
┌─────────────┐     ┌──────────┐     ┌──────────┐     ┌─────────────┐     ┌─────────┐
│  Tasy Oracle│────▶│ Debezium │────▶│  Kafka   │────▶│ FHIR Sync   │────▶│  HAPI   │
│   (ERP)     │ CDC │ (Connect)│Avro │  Topics  │ Avro│  (Python)   │ REST│  FHIR   │
└─────────────┘     └──────────┘     └──────────┘     └─────────────┘     └─────────┘
                         │                                     │
                         │ SMT: ExtractNewRecordState          │ Usa:
                         │ (envelope → flat)                   │  - 21+ Adapters
                         │                                     │  - Router
                         │ Tópicos: tasy.TASY.TABELA           │  - Conditional Update
                         │                                     │
                         ▼                                     ▼
                    Schema Registry                       PostgreSQL
                    (Avro schemas)                        (HAPI storage)
```

### Decisões Arquiteturais Chave

| Decisão | Escolha | Motivo |
|---------|---------|--------|
| **Formato Kafka** | Avro + Schema Registry | Schema evolution, tipos nativos, menor payload |
| **Layout Debezium** | Flat (ExtractNewRecordState) | Alinhado com datalake, sem navegar `after` |
| **Write strategy** | Conditional Update (`PUT ?identifier=...`) | Idempotente, sem duplicatas |
| **Referential integrity** | Desabilitada no HAPI | Permite chegar out-of-order |
| **Consumer group** | `fhir-sync` (separado do CDC Bridge) | Independência, sem interferência |
| **Error handling** | 3x retry (5xx) + dead-letter (4xx/validação) | Resiliência + observabilidade |

---

## 2. Fluxo de Dados End-to-End

### Exemplo: INSERT em `TASY.ATENDIMENTO_PACIENTE`

1. **Oracle** → Aplicação Tasy faz INSERT na tabela
2. **Debezium LogMiner** captura o evento do redo log (~1-3s latency)
3. **SMT `ExtractNewRecordState`** converte envelope → flat:
   ```json
   {
     "NR_ATENDIMENTO": 1529,
     "CD_PESSOA_FISICA": "12345",
     "DT_ENTRADA": "2026-04-10T14:30:00",
     "IE_TIPO_ATENDIMENTO": 2,
     "__op": "c",
     "__ts_ms": 1729847234000,
     "__source_table": "ATENDIMENTO_PACIENTE"
   }
   ```
4. **Kafka topic** `tasy.TASY.ATENDIMENTO_PACIENTE` recebe mensagem Avro
5. **FHIR Sync Consumer** (aiokafka) consome da partição
6. **Avro Deserializer** lê schema ID + decodifica payload via `fastavro`
7. **Event Parser** (flat) extrai:
   - `table_name` = "ATENDIMENTO_PACIENTE"
   - `operation` = `c` (CREATE)
   - `record_data` = dicionário sem metadados `__*`
8. **Router** resolve tabela+operação → `AdapterRoute(TasyEncounterAdapter, "Encounter", ...)`
9. **Column Map** renomeia colunas Oracle → campos esperados pelo adapter:
   ```python
   "CD_PESSOA_FISICA" → "NR_PACIENTE"
   "DT_ENTRADA" → "DT_ATENDIMENTO"
   "IE_TIPO_ATENDIMENTO" → "TP_ATENDIMENTO"
   ```
10. **Adapter** `TasyEncounterAdapter.adapt()` constrói recurso FHIR:
    ```json
    {
      "resourceType": "Encounter",
      "identifier": [{"system": "http://tasy.com/fhir/identifier/atendimento", "value": "1529"}],
      "status": "in-progress",
      "class": {"code": "IMP", ...},
      "subject": {"reference": "Patient/12345"},
      "period": {"start": "2026-04-10T14:30:00"}
    }
    ```
11. **FHIR Writer** faz `PUT /Encounter?identifier=http://tasy.com/fhir/identifier/atendimento|1529` (conditional update)
12. **HAPI FHIR** cria ou atualiza o recurso (idempotente)

---

## 3. Componentes e Responsabilidades

### 3.1 Debezium Oracle Connector

**Arquivo:** `config/debezium/oracle-connector.json`

**Config chave:**
```json
{
  "connector.class": "io.debezium.connector.oracle.OracleConnector",
  "database.hostname": "${TASY_DB_HOST}",
  "topic.prefix": "tasy",
  "table.include.list": "TASY.TABELA1,TASY.TABELA2,...",
  "key.converter": "io.confluent.connect.avro.AvroConverter",
  "value.converter": "io.confluent.connect.avro.AvroConverter",
  "transforms": "unwrap",
  "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
  "transforms.unwrap.drop.tombstones": "false",
  "transforms.unwrap.delete.handling.mode": "rewrite",
  "transforms.unwrap.add.fields": "op,ts_ms,source.table,source.scn",
  "decimal.handling.mode": "string",
  "snapshot.mode": "always"
}
```

**Variantes em produção:**
- `tasy-flat-v5` — snapshot sempre, flat Avro, 140 tabelas do hospital
- `austa-snapshot-v2` — snapshot envelope, 81 tabelas da operadora

### 3.2 FHIR Sync Service

**Localização:** `src/healthcare_platform/shared/fhir_sync/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `app.py` | Orchestrator (signal handling, startup/shutdown) |
| `consumer.py` | Kafka consumer loop + parse + route + write |
| `router.py` | `TABLE_ADAPTER_MAP` + `apply_column_map()` |
| `fhir_writer.py` | Wrapper com retry/backoff sobre FHIRClient |
| `avro_deserializer.py` | Schema Registry + fastavro + datetime conversion |
| `flat_event_parser.py` | Parse flat format (ExtractNewRecordState) |
| `health.py` | Liveness/readiness/Prometheus metrics (port 8092) |
| `dead_letter.py` | Publicar erros em `fhir-sync.dead-letter` |
| `config.py` | Pydantic settings (Kafka, FHIR, DLQ, Schema Registry) |

### 3.3 Adapters Tasy → FHIR

**Localização:** `src/healthcare_platform/shared/integrations/tasy_adapters/`

**Base class:** `BaseTasyFhirAdapter`
- `_build_identifier()`, `_build_reference()`, `_build_coding()`, `_build_codeable_concept()`
- `_sanitize_for_lgpd()` — redação de PII (NM_PACIENTE, NR_CPF, etc.)
- `_track_conversion_success()`, `_track_conversion_error()` — Prometheus
- `_validate_required_fields()` — valida campos obrigatórios

**Adapters implementados (23):**
- `TasyPatientAdapter` (V02) — PESSOA_FISICA/PACIENTE
- `TasyEncounterAdapter` (V01) — ATENDIMENTO_PACIENTE
- `TasyCoverageAdapter` (V05) — ATEND_CATEGORIA_CONVENIO
- `TasyOrganizationAdapter` (V24) — CONVENIO
- `TasyProcedureAdapter` (V04) — PROCEDIMENTO_PACIENTE
- `TasyAuthorizationAdapter` (V06) — AUTORIZACAO_CONVENIO → ClaimResponse
- `TasyPractitionerAdapter` (V07) — MEDICO + MEDICO_ESPECIALIDADE
- `TasyConditionAdapter` (V03) — DIAGNOSTICO_DOENCA
- (+15 outros)

### 3.4 Router (TABLE_ADAPTER_MAP)

**Arquivo:** `src/healthcare_platform/shared/fhir_sync/router.py`

**Formato:**
```python
TABLE_ADAPTER_MAP = {
    "ORACLE_TABLE_NAME": {
        "c": [AdapterRoute(AdapterClass, "FhirResource", id_system, id_field, columns_map)],
        "u": [mesma rota ou diferente],
        "r": [mesma rota para snapshot read],
    },
}
```

**Column Map:** dict de renomeação `"COLUNA_ORACLE": "CAMPO_ADAPTER"`. Também aplica conversões automáticas:
- IDs numéricos → string
- `TP_ATENDIMENTO` numérico → letra (1→I, 2→A, ...)
- `IE_ATIVO` variações → S/N (A/I, 1/0, True/False)

---

## 4. Padrão de Criação de Novo Adapter

Passo a passo para adicionar um novo recurso FHIR (ex: Observation para sinais vitais):

### Passo 1 — Identificar tabela Oracle

Consultar specification do time de automação (`docs/fhir-tasy/v*.md`) ou pedir SQL de referência. Ex:
- Tabela: `TASY.SINAL_VITAL_PACIENTE`
- FHIR target: `Observation`
- PK: `NR_SEQ_SINAL`
- Refs: `NR_ATENDIMENTO` (Encounter), `CD_PESSOA_FISICA` (Patient)

### Passo 2 — Descobrir colunas reais via Avro schema

```bash
# Se tabela já está no Debezium:
docker exec $(docker ps -q -f name=maezo_schema_registry) curl -sf \
  "http://localhost:8081/subjects/tasy.TASY.SINAL_VITAL_PACIENTE-value/versions/latest" \
  > /tmp/schema.json

python3 -c "
import json
with open('/tmp/schema.json') as f:
    r = json.load(f)
schema = json.loads(r['schema'])
# Para flat, os fields são diretos no root
for f in schema['fields']:
    print(f['name'])
"
```

Se ainda não está no Debezium, adicionar primeiro (ver Passo 7).

### Passo 3 — Criar o adapter

**Arquivo:** `src/healthcare_platform/shared/integrations/tasy_adapters/<resource>_adapter.py`

**Template:**
```python
"""Tasy <TABELA> to FHIR <Resource> R4 adapter."""
from __future__ import annotations
from typing import Any
from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import BaseTasyFhirAdapter


class Tasy<Resource>Adapter(BaseTasyFhirAdapter):
    ADAPTER_TYPE = "<type>"
    FHIR_RESOURCE_TYPE = "<Resource>"

    TASY_<TYPE>_SYSTEM = "http://tasy.com/fhir/identifier/<type>"

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_required_fields(tasy_data, ["NR_SEQ_PK", ...])

            resource: dict[str, Any] = {
                "resourceType": "<Resource>",
                "meta": {
                    "profile": ["http://hl7.org/fhir/StructureDefinition/<Resource>"],
                    "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
                },
                "identifier": [
                    self._build_identifier(
                        system=self.TASY_<TYPE>_SYSTEM,
                        value=str(tasy_data["NR_SEQ_PK"]),
                    )
                ],
                # ... campos específicos
            }

            self._track_conversion_success()
            return resource

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error("Failed to convert ...", extra={"error": str(exc)})
            raise
```

### Passo 4 — Registrar no `__init__.py`

```python
# tasy_adapters/__init__.py
from healthcare_platform.shared.integrations.tasy_adapters.<resource>_adapter import (
    Tasy<Resource>Adapter,
)

__all__ = [..., "Tasy<Resource>Adapter"]
```

### Passo 5 — Adicionar column map no router

```python
# fhir_sync/router.py
_<RESOURCE>_COLUMNS = {
    "NR_SEQ_PK_ORACLE": "NR_SEQ_PK",  # PK
    "CD_PESSOA_FISICA": "NR_PACIENTE",  # FK Patient
    "NR_ATENDIMENTO": "NR_ATENDIMENTO",  # FK Encounter
    # ... colunas do Oracle → campos do adapter
}
```

### Passo 6 — Adicionar rota no TABLE_ADAPTER_MAP

```python
TABLE_ADAPTER_MAP = {
    ...
    "<TABELA_ORACLE>": {
        op: _route(
            Tasy<Resource>Adapter, "<Resource>",
            "http://tasy.com/fhir/identifier/<type>",  # identifier system
            "NR_SEQ_PK",  # identifier field (mapped name)
            _<RESOURCE>_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
}
```

### Passo 7 — Adicionar tabela ao Debezium (se não existir)

```bash
docker exec $(docker ps -q -f name=maezo_debezium) curl -sf \
  http://localhost:8083/connectors/tasy-flat-v5/config | \
  python3 -c "
import sys,json
c=json.load(sys.stdin)
c['table.include.list'] += ',TASY.<TABELA>'
print(json.dumps(c))
" | docker exec -i $(docker ps -q -f name=maezo_debezium) curl -sf \
    -X PUT http://localhost:8083/connectors/tasy-flat-v5/config \
    -H 'Content-Type: application/json' -d @-
```

### Passo 8 — Adicionar tópico ao FHIR Sync config

```python
# fhir_sync/config.py
topics = [
    ...,
    "tasy.TASY.<TABELA>",
]
```

### Passo 9 — Build + deploy

```bash
docker build -f Dockerfile.fhir-sync -t maezo-fhir-sync:local .
sudo docker service rm maezo_fhir_sync
sudo -E docker stack deploy -c docker-compose.swarm.local.yml maezo
```

### Passo 10 — Validar

```bash
# Contar recursos criados
docker exec $(docker ps -q -f name=maezo_hapi_fhir) curl -sf \
  "http://localhost:8080/fhir/<Resource>?_summary=count"

# Ver um exemplo
docker exec $(docker ps -q -f name=maezo_hapi_fhir) curl -sf \
  "http://localhost:8080/fhir/<Resource>?_count=1"

# Verificar erros
docker exec $(docker ps -q -f name=maezo_fhir_sync) curl -sf \
  http://localhost:8092/metrics | grep -E "upserts|errors"
```

---

## 5. Padrão de Adição de Nova Tabela

Nem toda tabela vira um recurso FHIR próprio — algumas são enriquecimento (JOIN virtual). Nesse caso, o padrão é diferente:

### Caso A — Tabela = 1 Recurso FHIR (padrão)
Seguir a seção 4 completa.

### Caso B — Tabela enriquece outro recurso (ex: setor no Encounter)

Duas abordagens:

**B.1 — Lookup em memória (stream enrichment)**

Cacheia valores lidos de outro tópico durante o consumo:

```python
# Exemplo: cache de Setor por NR_ATENDIMENTO
class FHIRSyncConsumer:
    def __init__(...):
        self._setor_cache: dict[int, int] = {}  # nr_atendimento -> cd_setor

    async def _process_message(self, raw, tenant):
        event = _parse_event(raw)
        if event.table_name == "ATEND_PACIENTE_UNIDADE":
            self._setor_cache[event.record_data["NR_ATENDIMENTO"]] = \
                event.record_data["CD_SETOR_ATENDIMENTO"]
            return  # não gera recurso FHIR
        # ... processar outras tabelas usando _setor_cache
```

**B.2 — Enriquecimento via FHIR read (lookup)**

Antes de gravar o recurso, consulta HAPI FHIR:

```python
# No adapter
async def adapt(self, tasy_data):
    # Se precisa buscar dados de outro recurso já no FHIR:
    if not tasy_data.get("NR_PACIENTE") and tasy_data.get("NR_ATENDIMENTO"):
        encounter = await self._fhir_client.search(
            "Encounter",
            {"identifier": f"http://tasy.com/fhir/identifier/atendimento|{tasy_data['NR_ATENDIMENTO']}"},
        )
        if encounter:
            tasy_data["NR_PACIENTE"] = encounter[0]["subject"]["reference"].split("/")[-1]
```

### Caso C — Tabela é puramente domínio/lookup (ex: CID, TIPO_ACOMODACAO)

Não vira recurso FHIR. Usada para enriquecer `display` dos `CodeableConcept`. Pode ser:
- **Cache em memória** (init do consumer, load de Kafka)
- **Polling periódico** (muda raramente, vale load direto do Oracle)

---

## 6. Descobrir Colunas Oracle (via Avro Schema)

### Opção 1 — Schema Registry (tabela já no Debezium)

```bash
# Listar todos os subjects
docker exec $(docker ps -q -f name=maezo_schema_registry) curl -sf \
  http://localhost:8081/subjects | python3 -m json.tool

# Baixar schema de uma tabela
docker exec $(docker ps -q -f name=maezo_schema_registry) curl -sf \
  "http://localhost:8081/subjects/tasy.TASY.MEDICO-value/versions/latest" \
  > /tmp/schema.json

# Extrair nomes de colunas
python3 -c "
import json
with open('/tmp/schema.json') as f:
    r = json.load(f)
schema = json.loads(r['schema'])
# Flat layout: fields direto no root
for f in schema.get('fields', []):
    if not f['name'].startswith('__'):
        tp = f['type']
        if isinstance(tp, list):
            tp = [t if isinstance(t, str) else t.get('type', '?') for t in tp]
        print(f['name'], '→', tp)
"
```

### Opção 2 — Consumir uma mensagem raw

```bash
KAFKA_ID=$(docker ps --no-trunc -q -f name=maezo_kafka.1 | head -1)
docker exec $KAFKA_ID kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic tasy.TASY.<TABELA> \
  --from-beginning --max-messages 1 --timeout-ms 5000 2>/dev/null | \
python3 -c "
import sys, json
msg = json.load(sys.stdin)
# Para flat format, os campos estão no root
for k in sorted(msg.keys()):
    if not k.startswith('__'):
        v = msg[k]
        print(f'  {k}: {repr(v)[:60]}')
"
```

### Opção 3 — Consultar DBA / SQL no Oracle

Se não tiver acesso ao Debezium, pedir SQL:
```sql
SELECT column_name, data_type, nullable
FROM all_tab_columns
WHERE owner = 'TASY' AND table_name = '<TABELA>'
ORDER BY column_id;
```

---

## 7. Padrões de Mapeamento

### 7.1 Identifiers FHIR

Sempre incluir o **Tasy ID** como primeiro identifier:

```python
"identifier": [
    self._build_identifier(
        system="http://tasy.com/fhir/identifier/<tipo>",
        value=str(tasy_data["NR_SEQ_PK"]),
    )
]
```

Para `PUT ?identifier=`, **o system e value devem bater exatamente** com o identifier do recurso — se não, HAPI retorna `HAPI-0929`.

### 7.2 Identifier systems padronizados

| Tipo | System |
|------|--------|
| Atendimento | `http://tasy.com/fhir/identifier/atendimento` |
| Paciente (MRN) | `http://tasy.com/fhir/identifier/mrn` |
| CPF | `http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf` |
| CNPJ | `http://rnds.saude.gov.br/fhir/r4/NamingSystem/cnpj` |
| Convênio | `http://tasy.com/fhir/identifier/convenio` |
| Autorização | `http://tasy.com/fhir/identifier/autorizacao` |
| Procedimento | `http://tasy.com/fhir/identifier/procedimento` |
| Médico | `http://tasy.com/fhir/identifier/medico` |
| CRM | `http://www.cfm.org.br/fhir/NamingSystem/crm` |
| CID-10 | `http://hl7.org/fhir/sid/icd-10` |
| TUSS | `http://www.ans.gov.br/tuss` |
| CBO | `http://www.saude.gov.br/fhir/r4/CodeSystem/BRCBO` |
| ANS | `http://www.ans.gov.br/registry` |

### 7.3 Referências (Reference)

**Sempre** usar referência por Tasy PK como literal:
```python
"subject": {"reference": f"Patient/{NR_PACIENTE_TASY}"}
```

Com `hapi.fhir.enforce_referential_integrity_on_write: false`, o Patient pode chegar depois — FHIR não valida existência.

### 7.4 Datas

- Oracle `TIMESTAMP` → Avro `long` (epoch millis) via `logicalType: timestamp-millis`
- SMT `ExtractNewRecordState` **não converte** para ISO
- `avro_deserializer._convert_datetimes()` detecta ints `> 1_000_000_000_000` e converte para `YYYY-MM-DDTHH:MM:SS`

### 7.5 Flags Oracle `IE_*` (VARCHAR2 1 char)

Comum: `S/N`, `A/I`, `1/0`. O router em `apply_column_map()` normaliza `IE_ATIVO` para `S/N`. Outros flags `IE_*` devem ser tratados no próprio adapter com um dict MAP explícito.

### 7.6 Códigos numéricos → letras

Ex: `IE_TIPO_ATENDIMENTO` no Oracle é `int16` (1, 2, 3) mas o adapter espera letra (`I`, `A`, `E`). O router faz a conversão em `apply_column_map()`:

```python
_ENCOUNTER_TYPE_MAP = {1: "I", 2: "A", 3: "E", 4: "U", 5: "D"}
if "TP_ATENDIMENTO" in mapped and isinstance(mapped["TP_ATENDIMENTO"], int):
    mapped["TP_ATENDIMENTO"] = _ENCOUNTER_TYPE_MAP.get(mapped["TP_ATENDIMENTO"], "A")
```

---

## 8. Debugging e Troubleshooting

### 8.1 Ver erros em tempo real

```bash
# Métricas agregadas
docker exec $(docker ps -q -f name=maezo_fhir_sync) curl -sf http://localhost:8092/metrics

# Logs do FHIR Sync
docker service logs maezo_fhir_sync --tail 50 --since 1m

# Erros específicos (gramática HAPI)
docker service logs maezo_fhir_sync --tail 200 | grep "HAPI-" | sort | uniq -c | sort -rn
```

### 8.2 Principais códigos de erro HAPI

| Código | Significado | Como resolver |
|--------|-------------|---------------|
| `HAPI-0450` | JSON inválido | Tipo de campo errado (ex: epoch millis em `birthDate`) |
| `HAPI-0929` | Conditional create mismatch | Identifier no resource ≠ identifier na URL |
| `HAPI-0931` | Reference inválida | Referência para tipo errado (ex: `ClaimResponse.request → Claim`) |
| `HAPI-1094` | Resource not found | Referential integrity — usar `enforce_referential_integrity_on_write: false` |
| `HAPI-1821` | Date format inválido | Epoch millis em vez de ISO-8601 |

### 8.3 Resetar offsets do consumer (reprocessar)

```bash
KAFKA_ID=$(docker ps --no-trunc -q -f name=maezo_kafka.1 | head -1)

# Parar consumer
sudo docker service scale maezo_fhir_sync=0

# Resetar offset
docker exec $KAFKA_ID kafka-consumer-groups \
  --bootstrap-server kafka:9092 \
  --group fhir-sync \
  --reset-offsets --to-earliest \
  --topic tasy.TASY.<TABELA> --execute

# Reiniciar
sudo docker service scale maezo_fhir_sync=1
```

### 8.4 Forçar novo snapshot Debezium

```bash
# Option A: recriar connector com novo nome (offsets limpos)
docker exec $(docker ps -q -f name=maezo_debezium) curl -sf \
  http://localhost:8083/connectors/tasy-flat-v5/config > /tmp/config.json
docker exec $(docker ps -q -f name=maezo_debezium) curl -sf \
  -X DELETE http://localhost:8083/connectors/tasy-flat-v5

python3 -c "
import json
with open('/tmp/config.json') as f: c = json.load(f)
c['schema.history.internal.kafka.topic'] = '_debezium.history.tasy-v6'
c.pop('name', None)
with open('/tmp/new.json','w') as f: json.dump({'name':'tasy-flat-v6','config':c}, f)
"

cat /tmp/new.json | docker exec -i $(docker ps -q -f name=maezo_debezium) \
  curl -sf -X POST http://localhost:8083/connectors \
  -H 'Content-Type: application/json' -d @-
```

### 8.5 Checar lag do consumer

```bash
KAFKA_ID=$(docker ps --no-trunc -q -f name=maezo_kafka.1 | head -1)
docker exec $KAFKA_ID kafka-consumer-groups \
  --bootstrap-server kafka:9092 \
  --group fhir-sync --describe | column -t
```

---

## 9. Checklist para PR de Novo Recurso FHIR

Antes de abrir PR, verificar:

- [ ] Adapter criado em `src/healthcare_platform/shared/integrations/tasy_adapters/<nome>_adapter.py`
- [ ] Adapter herda de `BaseTasyFhirAdapter`
- [ ] Adapter implementa `ADAPTER_TYPE` e `FHIR_RESOURCE_TYPE`
- [ ] `_validate_required_fields()` com campos essenciais
- [ ] Identifier system definido como constante de classe
- [ ] `_track_conversion_success()` / `_track_conversion_error()` em todos os paths
- [ ] Registrado em `tasy_adapters/__init__.py` (import + `__all__`)
- [ ] Column map criado em `fhir_sync/router.py` (`_<RESOURCE>_COLUMNS`)
- [ ] Rota adicionada em `TABLE_ADAPTER_MAP` para `c`, `u`, `r`
- [ ] Tópico Kafka adicionado em `fhir_sync/config.py`
- [ ] Tabela no Debezium connector (via API ou `oracle-connector.json`)
- [ ] Identifier do resource **casa** com o da URL (sistema + campo PK)
- [ ] References por Tasy PK literal (`Patient/{NR_PACIENTE}`)
- [ ] Datas em formato ISO-8601 (ou deixar `_convert_datetimes()` tratar)
- [ ] Sem PII em logs (`_sanitize_for_lgpd()`)
- [ ] Build: `docker build -f Dockerfile.fhir-sync -t maezo-fhir-sync:local .`
- [ ] Deploy: `sudo docker service rm maezo_fhir_sync && sudo -E docker stack deploy ...`
- [ ] Validar: contagem FHIR > 0, sem processing errors, sample resource válido
- [ ] Doc atualizada em `docs/fhir-tasy/v<N> - VW_FHIR_<NOME>.md`

---

## Referências

- [ADR-004: Debezium CDC](../adr/004-debezium-cdc-erp-integration.md)
- [ADR-005: HAPI FHIR R4 Canonical Store](../adr/005-hapi-fhir-r4-canonical-store.md)
- [HL7 FHIR R4 Spec](https://hl7.org/fhir/R4/)
- [Debezium Oracle Connector](https://debezium.io/documentation/reference/stable/connectors/oracle.html)
- [ExtractNewRecordState SMT](https://debezium.io/documentation/reference/stable/transformations/event-flattening.html)
