# RN-DataQualityDelegate - Validação de Qualidade de Dados

## Identificação
- **ID**: RN-ANALYTICS-002
- **Nome**: DataQualityDelegate
- **Categoria**: Analytics & BI
- **Subprocess**: SUB_09_Analytics_Reporting
- **Versão**: 2.0.0
- **Data**: 2025-01-08
- **Bean BPMN**: `dataQualityDelegate`
- **Prioridade**: CRÍTICA

## Visão Geral
Delegate responsável por validação abrangente de qualidade de dados em processos do ciclo de receita, realizando 5 tipos de validação: campos obrigatórios, formatos, consistência, duplicatas e integridade referencial.

## Responsabilidades

### 1. Validação de Campos Obrigatórios (Completeness)
- Identifica campos obrigatórios faltantes
- Calcula score de completude
- Reporta campos ausentes com severidade

### 2. Validação de Formato (Accuracy)
- CPF: Regex + dígito verificador
- Telefone: Formato brasileiro (XX) XXXXX-XXXX
- Email: RFC 5322 compliant
- CEP: XXXXX-XXX
- Datas: Formato ISO-8601

### 3. Validação de Consistência (Consistency)
- Datas lógicas (início < fim)
- Valores numéricos (min < max)
- Relacionamentos (chaves estrangeiras)
- Regras de negócio domain-specific

### 4. Detecção de Duplicatas (Uniqueness)
- Identifica registros duplicados
- Valida unicidade de campos-chave
- Sugere ações corretivas

### 5. Integridade Referencial (Integrity)
- Valida referências a outras entidades
- Verifica existência de registros relacionados
- Identifica registros órfãos

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `data_source` | String | Sim | Fonte dos dados (TASY, patient_registration, etc) |
| `data_type` | String | Sim | Tipo de dados (patient, insurance, billing) |
| `validation_data` | Map&lt;String, Object&gt; | Não* | Registro único para validação |
| `validation_batch` | List&lt;Map&lt;String, Object&gt;&gt; | Não* | Múltiplos registros para validação |
| `min_quality_threshold` | Double | Não | Score mínimo de qualidade (default: 0.75) |

*Pelo menos `validation_data` OU `validation_batch` deve ser fornecido.

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `data_quality_passed` | Boolean | `true` se qualidade >= threshold |
| `data_quality_score` | Double | Score geral de qualidade 0.0-1.0 |
| `data_quality_report` | DataQualityReport | Relatório completo de qualidade |
| `completeness_score` | Double | Score de completude 0.0-1.0 |
| `accuracy_score` | Double | Score de acurácia 0.0-1.0 |
| `consistency_score` | Double | Score de consistência 0.0-1.0 |
| `timeliness_score` | Double | Score de pontualidade 0.0-1.0 |
| `validation_failures` | List&lt;Map&lt;String, Object&gt;&gt; | Lista de problemas encontrados |
| `quality_issues_count` | Integer | Número total de problemas |
| `critical_issues_count` | Long | Número de problemas críticos |
| `data_quality_timestamp` | Long | Timestamp da validação (millis) |

## Erros BPMN

| Código | Mensagem | Causa | Ação |
|--------|----------|-------|------|
| `DATA_QUALITY_CRITICAL` | Data quality validation failed: N critical issues found | Score < threshold E critical issues > 0 | Corrigir problemas críticos |

## Dimensões de Qualidade de Dados

### 1. Completeness (Completude)
**Definição**: Proporção de campos obrigatórios preenchidos

**Cálculo**:
```
completeness = (campos preenchidos / campos obrigatórios) * 100%
```

**Exemplo**:
- Campos obrigatórios: nome, CPF, data_nascimento, telefone
- Preenchidos: nome, CPF, data_nascimento
- Completeness = 3/4 = 75%

### 2. Accuracy (Acurácia)
**Definição**: Proporção de dados que seguem formato correto

**Validações**:
- CPF: `\d{3}\.\d{3}\.\d{3}-\d{2}` + dígito verificador
- Email: `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`
- Telefone: `\(\d{2}\) \d{4,5}-\d{4}`

**Cálculo**:
```
accuracy = (campos válidos / total de campos) * 100%
```

### 3. Consistency (Consistência)
**Definição**: Dados seguem regras lógicas de negócio

**Regras**:
- `data_admissao <= data_alta`
- `idade >= 0 AND idade <= 150`
- `valor_cobrado >= 0`
- `sexo IN ('M', 'F', 'Outro')`

**Cálculo**:
```
consistency = (regras atendidas / total de regras) * 100%
```

### 4. Timeliness (Pontualidade)
**Definição**: Dados foram atualizados recentemente

**Cálculo**:
```
timeliness = 1.0 - (dias desde última atualização / 90)
```

**Exemplo**:
- Última atualização: 10 dias atrás
- timeliness = 1.0 - (10/90) = 0.89 = 89%

### 5. Uniqueness (Unicidade)
**Definição**: Ausência de duplicatas

**Detecção**:
- Registros com mesmo CPF
- Registros com mesmo email
- Registros com mesma carteirinha

## Algoritmo de Validação

```
1. Verificar modo de validação:
   - Se validation_batch existe: validação em lote
   - Caso contrário: validação de registro único

2. Executar DataQualityService:
   - validateDataQuality(dataSource, validationData, dataType)
   - OU validateBatchDataQuality(dataSource, batch, dataType)

3. Obter threshold mínimo:
   - min_quality_threshold (default: 0.75 = 75%)

4. Avaliar resultado:
   - passed = (overallQualityScore >= minThreshold)
   - criticalIssues = count(issues where severity == CRITICAL)

5. Converter problemas para formato serializável:
   - Para cada QualityIssue:
     - Extrair: type, severity, description, field, affectedRecords, suggestedFix
     - Adicionar a validation_failures

6. Verificar problemas críticos:
   - Se criticalIssues > 0 AND !passed:
     → throw BpmnError("DATA_QUALITY_CRITICAL")

7. Persistir resultados
```

## Estrutura de DataQualityReport

```java
class DataQualityReport {
    double overallQualityScore;    // 0.0-1.0
    double completenessScore;      // 0.0-1.0
    double accuracyScore;          // 0.0-1.0
    double consistencyScore;       // 0.0-1.0
    double timelinessScore;        // 0.0-1.0
    List<QualityIssue> qualityIssues;

    long countCriticalIssues() {
        return qualityIssues.stream()
            .filter(issue -> issue.severity == Severity.CRITICAL)
            .count();
    }
}

class QualityIssue {
    String issueType;          // MISSING_FIELD, INVALID_FORMAT, etc
    Severity severity;         // CRITICAL, HIGH, MEDIUM, LOW
    String description;        // Descrição do problema
    String fieldName;          // Campo afetado
    int affectedRecords;       // Número de registros afetados
    String suggestedFix;       // Sugestão de correção
}
```

## Casos de Uso

### Caso 1: Validação Bem-Sucedida
**Entrada**:
```json
{
  "data_source": "TASY",
  "data_type": "patient",
  "validation_data": {
    "nome": "João Silva",
    "cpf": "123.456.789-09",
    "data_nascimento": "1990-05-15",
    "telefone": "(11) 98765-4321",
    "email": "joao.silva@example.com"
  },
  "min_quality_threshold": 0.80
}
```

**Saída**:
```json
{
  "data_quality_passed": true,
  "data_quality_score": 0.95,
  "completeness_score": 1.0,
  "accuracy_score": 1.0,
  "consistency_score": 0.9,
  "timeliness_score": 0.9,
  "quality_issues_count": 0,
  "critical_issues_count": 0
}
```

### Caso 2: Falha por Problemas Críticos
**Entrada**:
```json
{
  "data_source": "patient_registration",
  "data_type": "patient",
  "validation_data": {
    "nome": "Maria",
    "cpf": "000.000.000-00",
    "data_nascimento": "2030-01-01",
    "telefone": "invalid",
    "email": "maria@"
  },
  "min_quality_threshold": 0.75
}
```

**Erro BPMN**:
```
BpmnError("DATA_QUALITY_CRITICAL",
  "Data quality validation failed: 3 critical issues found, quality score: 45.00%")
```

**validation_failures**:
```json
[
  {
    "type": "INVALID_FORMAT",
    "severity": "CRITICAL",
    "description": "CPF inválido (dígito verificador incorreto)",
    "field": "cpf",
    "affected_records": 1,
    "suggested_fix": "Verificar CPF com o paciente"
  },
  {
    "type": "INVALID_FORMAT",
    "severity": "CRITICAL",
    "description": "Data de nascimento no futuro",
    "field": "data_nascimento",
    "affected_records": 1,
    "suggested_fix": "Corrigir data de nascimento"
  },
  {
    "type": "INVALID_FORMAT",
    "severity": "HIGH",
    "description": "Formato de telefone inválido",
    "field": "telefone",
    "affected_records": 1,
    "suggested_fix": "Usar formato (XX) XXXXX-XXXX"
  }
]
```

### Caso 3: Validação em Lote
**Entrada**:
```json
{
  "data_source": "TASY",
  "data_type": "billing",
  "validation_batch": [
    {"guia_id": "G001", "valor": 1500.00, "data": "2025-01-10"},
    {"guia_id": "G002", "valor": -500.00, "data": "2025-01-11"},
    {"guia_id": "G003", "data": "2025-01-12"}
  ],
  "min_quality_threshold": 0.70
}
```

**Saída**:
```json
{
  "data_quality_passed": false,
  "data_quality_score": 0.67,
  "completeness_score": 0.67,
  "accuracy_score": 0.67,
  "consistency_score": 0.67,
  "quality_issues_count": 3,
  "critical_issues_count": 2
}
```

## Regras de Negócio

### RN-ANALYTICS-002-001: Threshold Mínimo
- **Descrição**: Score de qualidade mínimo padrão é 75%
- **Prioridade**: ALTA
- **Validação**: `overallQualityScore >= min_quality_threshold (default: 0.75)`

### RN-ANALYTICS-002-002: Problemas Críticos Impedem Processamento
- **Descrição**: Se há problemas críticos E score < threshold, lançar erro
- **Prioridade**: CRÍTICA
- **Validação**: `criticalIssues > 0 && !passed → throw BpmnError`

### RN-ANALYTICS-002-003: Validação de CPF
- **Descrição**: CPF deve ter formato válido E dígito verificador correto
- **Prioridade**: CRÍTICA
- **Regex**: `\d{3}\.\d{3}\.\d{3}-\d{2}`
- **Algoritmo**: Módulo 11 para dígitos verificadores

### RN-ANALYTICS-002-004: Validação de Email
- **Descrição**: Email deve seguir RFC 5322
- **Prioridade**: ALTA
- **Regex**: `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`

## Integração com DataQualityService

### Validação de Registro Único
```java
DataQualityReport report =
    dataQualityService.validateDataQuality(
        dataSource,
        validationData,
        dataType
    );
```

### Validação em Lote
```java
DataQualityReport report =
    dataQualityService.validateBatchDataQuality(
        dataSource,
        validationBatch,
        dataType
    );
```

## Idempotência

**Requer Idempotência**: Não

**Justificativa**: Validação de qualidade é operação read-only e pode ser executada múltiplas vezes sem efeitos colaterais.

## Conformidade Regulatória

### LGPD
- CPF é mascarado em logs (XXX.XXX.XXX-XX)
- Dados sensíveis não são incluídos em relatórios de erro

### TISS 4.0 (ANS)
- Valida formatos de dados conforme TISS
- Garante qualidade antes de envio para operadoras

## Métricas e KPIs

### Indicadores de Qualidade de Dados
- **Score Médio Geral**: `AVG(data_quality_score)`
- **Taxa de Aprovação**: `(data_quality_passed count / total) * 100%`
- **Taxa de Problemas Críticos**: `(critical_issues_count / total_issues) * 100%`
- **Score por Dimensão**:
  - Completeness: `AVG(completeness_score)`
  - Accuracy: `AVG(accuracy_score)`
  - Consistency: `AVG(consistency_score)`
  - Timeliness: `AVG(timeliness_score)`

### Metas
- Score Médio Geral > 0.85
- Taxa de Aprovação > 90%
- Taxa de Problemas Críticos < 5%

## Dependências
- `DataQualityService`: Serviço de validação de qualidade
- Regras de validação por data_type
- Tabelas de referência para integridade

## Versionamento
- **v1.0.0**: Implementação inicial
- **v2.0.0**: Adicionada validação em lote e timeliness_score

## Referências
- ISO/IEC 25012: Data Quality Model
- RN-CalculateKPIs: Documentação de cálculo de KPIs
- RN-CompletenessCheck: Documentação de verificação de completude
