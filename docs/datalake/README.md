# Camada Raw Tasy — Guia para o time do datalake

> **Contexto:** resposta à auditoria de 2026-04-22 sobre fontes raw ausentes no `sources.yml` do projeto dbt.

## TL;DR

- **195 tópicos** no Confluent Schema Registry (112 `tasy.TASY.*` + 83 `austa.TASY.*`)
- **2 connectors Debezium** em uso, com layouts Avro diferentes
- **`sources.yml`** completo gerado em [`sources.yml`](./sources.yml) pronto para copiar ao projeto dbt
- **Estrutura S3:** `s3a://{{ var('raw_bucket') }}/raw-tasy/stream/<tópico>/`

## Mudanças recentes que impactam o dbt

### 1. `tasy.TASY.*` passou de JSON para Avro flat

A partir de **2026-04-23**, o connector `tasy-flat-v5` produz **Avro flat** (com SMT `ExtractNewRecordState`) em vez de JSON envelope antigo. Isso impacta:

- **Bronze models existentes** com `SELECT *` continuam funcionando (o layout flat mantém compatibilidade)
- **Novos registros** nos tópicos têm campos `__op`, `__ts_ms`, `__source_table`, `__source_scn` no topo
- **Offsets antigos** do tópico ainda podem ter JSON envelope misturado com Avro flat — considerar reset após 2026-04-30 quando a retention Kafka expirar

### 2. Novos tópicos (tabelas adicionadas em 2026-04-23)

Para o SP-RC-002 foram adicionados 7 tópicos novos que o datalake pode querer ingerir:

| Tópico | Uso no FHIR | Volume esperado |
|--------|-------------|-----------------|
| `tasy.TASY.MEDICO` | Practitioner | ~baixo |
| `tasy.TASY.MEDICO_ESPECIALIDADE` | qualification do Practitioner | baixo |
| `tasy.TASY.DIAGNOSTICO_DOENCA` | Condition (CID-10) | médio |
| `tasy.TASY.PROCEDIMENTO_AUTORIZADO` | Claim.item / ClaimResponse.item | médio |
| `tasy.TASY.CONVENIO_ESTABELECIMENTO` | Organization (NR_ANS) | baixo |
| `tasy.TASY.PLANO_CONVENIO` | Coverage.class.plan | baixo |
| `tasy.TASY.CID` | lookup CID-10 | baixo (domínio) |
| `tasy.TASY.ATEND_CATEGORIA_CONVENIO` | Coverage | alto (300K+ records) |

## Layouts Avro por connector

### `tasy-flat-v5` (hospital) — flat

**Todos** os tópicos `tasy.TASY.*` estão em layout **flat** após o SMT `ExtractNewRecordState`:

```json
{
  "NR_ATENDIMENTO": 1529,
  "CD_PESSOA_FISICA": "12345",
  "DT_ENTRADA": 1729847234000,
  "IE_TIPO_ATENDIMENTO": 2,
  "__op": "c",
  "__ts_ms": 1729847234000,
  "__source_table": "ATENDIMENTO_PACIENTE",
  "__source_scn": "6764953663465"
}
```

Compatible com a macro `bronze_raw_incremental_flat` existente.

### `austa-snapshot-v2` (operadora) — misto

Os tópicos `austa.TASY.*` têm **dois formatos** conforme documentado na auditoria anterior:

**Envelope** (`bronze_raw_incremental_austa_envelope`):
- AREA_PROCEDIMENTO, CBO_SAUDE, CONVENIO, ESPECIALIDADE_PROC, GRAU_PARENTESCO, GRUPO_PROC, PESSOA_JURIDICA, PLS_LOTE_MENSALIDADE, PLS_ROL_GRUPO_PROC, PLS_ROL_PROCEDIMENTO, TIPO_PESSOA_JURIDICA, TISS_MOTIVO_GLOSA

**Flat** (`bronze_raw_incremental_austa_flat`):
- AUSTA_BENEFICIARIO, AUSTA_CONTA, AUSTA_MENSALIDADE, AUSTA_PRESTADOR, AUSTA_PROC_E_MAT, AUSTA_REQUISICAO, PESSOA_FISICA, PESSOA_JURIDICA_COMPL, PLS_MENSALIDADE, PLS_MENSALIDADE_SEGURADO, PROCEDIMENTO, SUS_MUNICIPIO

## Como usar o `sources.yml` gerado

### 1. Copiar para o projeto dbt

```bash
cp sources.yml <caminho-do-dbt>/models/sources.yml
```

### 2. Configurar a variável `raw_bucket` no `dbt_project.yml`

```yaml
vars:
  raw_bucket: lakehouse-raw-prod  # ou o nome do bucket
```

### 3. Remover entrada órfã `bronze_tasy_paciente`

A entrada `source: bronze` → `bronze_tasy_paciente` deve ser removida (é legada e o modelo não existe mais).

### 4. Refatorar bronze models para usar `source()` em vez de path fixo

**Antes:**
```sql
{% set raw_path = 's3a://' ~ var('raw_bucket') ~ '/raw-tasy/stream/tasy.TASY.CONVENIO/' %}
SELECT * FROM avro.`{{ raw_path }}`
```

**Depois:**
```sql
SELECT * FROM {{ source('raw_tasy', 'convenio') }}
```

Isso habilita linhagem no dbt docs e facilita manutenção.

### 5. Ajustar as macros para aceitar `source()`

```sql
-- macros/bronze_raw_incremental_flat.sql
{% macro bronze_raw_incremental_flat(source_name, table_name) %}
SELECT *
FROM {{ source(source_name, table_name) }}
{% if is_incremental() %}
WHERE __ts_ms > (SELECT COALESCE(MAX(__ts_ms), 0) FROM {{ this }})
{% endif %}
{% endmacro %}
```

Uso:
```sql
-- models/bronze/bronze_tasy_convenio.sql
{{ bronze_raw_incremental_flat('raw_tasy', 'convenio') }}
```

## Arquivos

- [`sources.yml`](./sources.yml) — 195 tabelas catalogadas (112 `raw_tasy` + 83 `raw_austa`)
- [`README.md`](./README.md) — este documento

## Perguntas abertas

1. **Retention Kafka:** qual é o retention atual dos tópicos? Se for 7 dias, os dados antigos do snapshot inicial podem ter expirado — validar antes de refazer bronze.

2. **Format mudou:** decidir se faz re-snapshot agora (bronze reprocessa tudo) ou aceita o mix flat + envelope antigo no mesmo tópico até a retention resolver sozinho.

3. **Tabelas novas:** decidir se já criam bronze para as 8 tabelas adicionadas em 2026-04-23 ou deixam para uma próxima onda.

4. **Silver/Gold:** com sources catalogados, o datalake pode criar `refs` nos modelos silver diretamente — cronograma?
