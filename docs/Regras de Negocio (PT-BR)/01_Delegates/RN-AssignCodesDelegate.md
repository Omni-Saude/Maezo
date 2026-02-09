# RN-AssignCodesDelegate - Atribuição de Códigos Médicos

## Identificação
- **ID**: RN-CODING-002
- **Nome**: AssignCodesDelegate
- **Categoria**: Codificação Médica
- **Versão**: 1.0.0
- **Data**: 2025-12-23
- **Bean BPMN**: `assignCodes`

## Visão Geral
Delegate responsável por atribuir códigos médicos (ICD-10 para diagnósticos e TUSS para procedimentos) utilizando engine de codificação alimentado por IA.

## Responsabilidades

### 1. Atribuição de Códigos ICD-10
- Recupera lista de diagnósticos do atendimento
- Utiliza serviço de IA para mapear diagnósticos → códigos ICD-10
- Valida especificidade dos códigos atribuídos
- Prioriza códigos específicos sobre códigos não especificados (.9)

### 2. Atribuição de Códigos TUSS
- Recupera lista de procedimentos realizados
- Mapeia procedimentos → códigos TUSS da tabela oficial
- Valida completude da codificação de procedimentos
- Mantém rastreabilidade procedimento → código

### 3. Validação de Qualidade
- Calcula score de qualidade da codificação (0.0-1.0)
- Penaliza uso excessivo de códigos não especificados
- Emite alertas para codificações de baixa qualidade (<0.7)
- Valida completude: todos os diagnósticos/procedimentos devem ter códigos

### 4. Rastreabilidade
- Mantém mapeamento detalhado: diagnóstico → código ICD
- Mantém mapeamento detalhado: procedimento → código TUSS
- Registra método de codificação (AI_POWERED)
- Suporta idempotência para evitar recodificação

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `encounterId` | String | Sim | Identificador único do atendimento |
| `procedures` | List&lt;String&gt; | Não | Lista de procedimentos realizados |
| `diagnoses` | List&lt;String&gt; | Não | Lista de diagnósticos |

**Validação**: Pelo menos `procedures` OU `diagnoses` deve ser fornecido.

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `procedureCodes` | List&lt;String&gt; | Códigos TUSS atribuídos para procedimentos |
| `diagnosisCodes` | List&lt;String&gt; | Códigos ICD-10 atribuídos para diagnósticos |
| `procedureCodeMap` | Map&lt;String, String&gt; | Mapeamento procedimento → código TUSS |
| `diagnosisCodeMap` | Map&lt;String, String&gt; | Mapeamento diagnóstico → código ICD-10 |
| `codingComplete` | Boolean | `true` se todos os itens foram codificados |
| `codingQuality` | Double | Score de qualidade 0.0-1.0 (1.0 = melhor) |
| `codingMethod` | String | Sempre "AI_POWERED" |

## Erros BPMN

| Código | Mensagem | Causa | Ação |
|--------|----------|-------|------|
| `INVALID_ENCOUNTER` | Encounter ID is required | Encounter ID nulo/vazio | Verificar entrada |
| `MISSING_CLINICAL_DATA` | At least one procedure or diagnosis is required | Nenhum dado clínico fornecido | Verificar coleta de dados |
| `CODING_FAILED` | Code assignment failed | Erro no serviço de codificação | Revisar logs |

## Cálculo de Score de Qualidade

```
Fórmula:
qualityScore = 1.0 - (códigos não específicos / total de códigos)

Exemplo:
- 5 diagnósticos codificados
- 2 códigos terminam em .9 (não específicos)
- qualityScore = 1.0 - (2/5) = 0.60 = 60%

Classificação:
- ≥ 0.9: Excelente
- 0.7 - 0.89: Bom
- < 0.7: Baixa qualidade (requer revisão)
```

## Algoritmo de Validação

```
1. Validar entrada:
   - encounterId não pode ser nulo/vazio
   - Pelo menos procedures OU diagnoses deve existir

2. Atribuir códigos via CodingService:
   - procedureCodeMap = assignProcedureCodes(procedures)
   - diagnosisCodeMap = assignDiagnosisCodes(diagnoses)

3. Extrair listas de códigos:
   - procedureCodes = values(procedureCodeMap)
   - diagnosisCodes = values(diagnosisCodeMap)

4. Validar completude:
   - codingComplete = (size(procedureCodes) == size(procedures)) AND
                      (size(diagnosisCodes) == size(diagnoses))

5. Calcular qualidade:
   - Contar códigos não específicos (terminam em .9)
   - codingQuality = 1.0 - (unspecified / total)

6. Emitir alertas:
   - Se codingQuality < 0.7: log.warn("LOW CODING QUALITY")
```

## Integração com CodingService

### Atribuição de Códigos de Procedimentos
```java
Map<String, String> procedureCodeMap =
    codingService.assignProcedureCodes(procedures, encounterId);
```

### Atribuição de Códigos de Diagnósticos
```java
Map<String, String> diagnosisCodeMap =
    codingService.assignDiagnosisCodes(diagnoses, encounterId);
```

## Idempotência

**Requer Idempotência**: Sim

**Parâmetros de Idempotência**:
- `encounterId`: Garante que mesmo atendimento não seja recodificado

**Comportamento**:
- Se executado múltiplas vezes para o mesmo encounter, retorna mesmos códigos
- Evita sobrescrever codificação manual/revisada

## Casos de Uso

### Caso 1: Codificação Completa com Alta Qualidade
**Entrada**:
```json
{
  "encounterId": "ATD-2025-001",
  "diagnoses": ["Diabetes mellitus tipo 2", "Hipertensão arterial"],
  "procedures": ["Consulta médica", "Glicemia de jejum"]
}
```

**Saída**:
```json
{
  "diagnosisCodes": ["E11.9", "I10"],
  "procedureCodes": ["10101012", "40301010"],
  "codingComplete": true,
  "codingQuality": 0.5,
  "codingMethod": "AI_POWERED"
}
```

**Observação**: Quality = 0.5 porque ambos diagnósticos usam códigos .9

### Caso 2: Codificação com Especificidade Alta
**Entrada**:
```json
{
  "encounterId": "ATD-2025-002",
  "diagnoses": [
    "Diabetes mellitus tipo 2 com complicações renais",
    "Hipertensão arterial essencial"
  ]
}
```

**Saída**:
```json
{
  "diagnosisCodes": ["E11.21", "I10"],
  "codingComplete": true,
  "codingQuality": 1.0,
  "codingMethod": "AI_POWERED"
}
```

**Observação**: Quality = 1.0 porque E11.21 é específico (não termina em .9)

### Caso 3: Codificação Incompleta
**Entrada**:
```json
{
  "encounterId": "ATD-2025-003",
  "diagnoses": ["Diagnóstico não documentado", "Sintomas inespecíficos"],
  "procedures": ["Procedimento experimental"]
}
```

**Saída**:
```json
{
  "diagnosisCodes": ["R69"],
  "procedureCodes": [],
  "codingComplete": false,
  "codingQuality": 0.5,
  "codingMethod": "AI_POWERED"
}
```

**Log Warning**: "Incomplete procedure coding: expected 1, assigned 0"

## Regras de Negócio

### RN-CODING-002-001: Validação de Entrada
- **Descrição**: Encounter ID é obrigatório
- **Prioridade**: CRÍTICA
- **Validação**: `encounterId != null && !encounterId.isEmpty()`

### RN-CODING-002-002: Requisito de Dados Clínicos
- **Descrição**: Pelo menos diagnósticos ou procedimentos devem ser fornecidos
- **Prioridade**: CRÍTICA
- **Validação**: `!procedures.isEmpty() || !diagnoses.isEmpty()`

### RN-CODING-002-003: Completude da Codificação
- **Descrição**: Todos os itens clínicos devem ter códigos atribuídos
- **Prioridade**: ALTA
- **Validação**: `procedureCodes.size() == procedures.size() && diagnosisCodes.size() == diagnoses.size()`

### RN-CODING-002-004: Qualidade Mínima
- **Descrição**: Score de qualidade abaixo de 0.7 requer revisão
- **Prioridade**: MÉDIA
- **Ação**: Emitir warning log

## Integrações

### CodingService (Interno)
- **Método**: `assignProcedureCodes(procedures, encounterId)`
- **Retorno**: `Map<String, String>` - Procedimento → Código TUSS
- **Método**: `assignDiagnosisCodes(diagnoses, encounterId)`
- **Retorno**: `Map<String, String>` - Diagnóstico → Código ICD-10

## Conformidade Regulatória

### TISS 4.0 (ANS)
- Utiliza tabela TUSS oficial para codificação de procedimentos
- Mantém rastreabilidade procedimento → código

### ICD-10 (CID-10)
- Utiliza tabela ICD-10 oficial da OMS
- Prioriza códigos específicos sobre não especificados

## Métricas e KPIs

### Indicadores de Qualidade
- **Taxa de Completude**: `(codingComplete count / total) * 100%`
- **Score Médio de Qualidade**: `AVG(codingQuality)`
- **Taxa de Códigos Específicos**: `(specific codes / total codes) * 100%`

### Metas
- Taxa de Completude > 95%
- Score Médio de Qualidade > 0.80
- Taxa de Códigos Específicos > 80%

## Dependências
- `CodingService`: Serviço de codificação alimentado por IA
- Tabela TUSS oficial (ANS)
- Tabela ICD-10 (CID-10)

## Versionamento
- **v1.0.0**: Implementação inicial com IA-powered coding

## Referências
- Tabela TUSS: https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar
- ICD-10: https://icd.who.int/browse10/2019/en
- RN-COD-AIDRGCoding: Documentação de codificação DRG com IA
