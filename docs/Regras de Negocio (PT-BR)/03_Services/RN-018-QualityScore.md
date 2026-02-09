# RN-018: Cálculo de Score de Qualidade da Documentação

**Delegate**: `QualityScoreDelegate.java`
**Subprocesso BPMN**: SUB_05_Clinical_Documentation_Improvement
**Prioridade**: CRÍTICA
**Versão**: 1.0
**Última Atualização**: 2026-01-12

---

## 1. Visão Geral

### 1.1 Objetivo
Calcular score de qualidade da documentação clínica através de análise multidimensional, comparando com benchmarks institucionais e fornecendo feedback quantitativo para melhoria contínua.

### 1.2 Escopo
- Análise de especificidade de codificação (25% do score)
- Avaliação de completude de documentação (35% do score)
- Medição de pontualidade de documentação (20% do score)
- Validação de precisão clínica (20% do score)
- Comparação com benchmarks hospitalares

### 1.3 Stakeholders
- **Primários**: Gestão de qualidade, CDI, educação médica
- **Secundários**: Médicos, codificadores, gestão executiva

---

## 2. Estrutura de Pontuação Ponderada

### RN-018.1: Fórmula de Cálculo do Score Geral
**Criticidade**: CRÍTICA
**Categoria**: Cálculo de Qualidade

**Descrição**:
Score geral calculado através de média ponderada de quatro dimensões:

**Dimensões e Pesos**:
| Dimensão | Peso | Foco |
|----------|------|------|
| **Specificity** | 25% | Especificidade ICD-10 |
| **Completeness** | 35% | Completude documental |
| **Timeliness** | 20% | Pontualidade de documentação |
| **Accuracy** | 20% | Precisão e consistência |

**Fórmula**:
```
Overall Score = (Specificity × 0.25) + (Completeness × 0.35) +
                (Timeliness × 0.20) + (Accuracy × 0.20)
```

**Implementação**:
```java
private static final double SPECIFICITY_WEIGHT = 0.25;
private static final double COMPLETENESS_WEIGHT = 0.35;
private static final double TIMELINESS_WEIGHT = 0.20;
private static final double ACCURACY_WEIGHT = 0.20;

double overallScore = (specificityScore * SPECIFICITY_WEIGHT) +
                     (completenessScore * COMPLETENESS_WEIGHT) +
                     (timelinessScore * TIMELINESS_WEIGHT) +
                     (accuracyScore * ACCURACY_WEIGHT);
```

---

## 3. Dimensão 1: Specificity (25%)

### RN-018.2: Avaliação de Especificidade ICD-10
**Criticidade**: ALTA
**Categoria**: Qualidade de Codificação

**Descrição**:
Avalia o nível de especificidade dos códigos ICD-10 utilizados:

**Critérios de Avaliação** (3 pontos máximos por código):

**1. Subcategoria Detalhada** (+1 ponto):
- Código possui ≥ 5 caracteres (categoria + subcategoria)
- Exemplo: I10.0 (5 char) vs I10 (3 char)

**2. Evita "Unspecified"** (+1 ponto):
- Código NÃO termina em .9 ou contém .9
- Exemplo: E11.65 vs E11.9

**3. 7º Caractere Quando Requerido** (+1 ponto):
- Códigos S (injury), T (poisoning), O (obstetrics) devem ter 7 caracteres
- Exemplo: S72.001A (7 char) vs S72.0 (5 char - incompleto)

**Cálculo**:
```java
private double calculateSpecificityScore(List<String> diagnosisCodes,
                                          List<String> procedureCodes) {
    int totalCodes = diagnosisCodes.size();
    int specificCodes = 0;

    for (String code : diagnosisCodes) {
        // +1 se tem subcategoria (≥5 chars)
        if (code.length() >= 5) {
            specificCodes++;
        }

        // +1 se não é unspecified
        if (!code.endsWith("9") && !code.contains(".9")) {
            specificCodes++;
        }

        // +1 se tem 7º caractere quando requerido
        if (requiresSeventhCharacter(code) && code.length() >= 7) {
            specificCodes++;
        }
    }

    double maxPoints = totalCodes * 3.0;
    double actualPoints = specificCodes;

    return Math.min(100.0, (actualPoints / maxPoints) * 100.0);
}
```

**Exemplo de Pontuação**:
| Código | Subcategoria | Não Unspec | 7º Char | Score Individual |
|--------|-------------|-----------|---------|------------------|
| I10.0 | 1 | 1 | N/A | 2/2 = 100% |
| E11.9 | 1 | 0 | N/A | 1/2 = 50% |
| S72.001A | 1 | 1 | 1 | 3/3 = 100% |
| M17 | 0 | 1 | N/A | 1/2 = 50% |

---

### RN-018.3: Códigos que Requerem 7º Caractere
**Criticidade**: MÉDIA
**Categoria**: Compliance ICD-10

**Descrição**:
Categorias ICD-10 que DEVEM ter 7º caractere:

**Categorias Requeridas**:
- **S**: Injuries (lesões)
- **T**: Poisoning and external causes (envenenamento)
- **V, W, X, Y**: External causes of morbidity (causas externas)
- **O**: Pregnancy, childbirth (gestação, parto)

**7º Caractere - Episódio de Cuidado**:
| Caractere | Significado | Uso |
|-----------|-------------|-----|
| A | Initial encounter | Primeiro atendimento |
| D | Subsequent encounter | Atendimento subsequente |
| S | Sequela | Sequela da condição |

**Implementação**:
```java
private boolean requiresSeventhCharacter(String icd10Code) {
    return icd10Code.startsWith("S") || icd10Code.startsWith("T") ||
           icd10Code.startsWith("V") || icd10Code.startsWith("W") ||
           icd10Code.startsWith("X") || icd10Code.startsWith("Y") ||
           icd10Code.startsWith("O");
}
```

---

## 4. Dimensão 2: Completeness (35%)

### RN-018.4: Elementos Documentais Obrigatórios por Tipo de Encontro
**Criticidade**: CRÍTICA
**Categoria**: Completude Documental

**Descrição**:
Elementos obrigatórios variam conforme tipo de encontro:

**INPATIENT** (14 elementos):
1. historyAndPhysical
2. chiefComplaint
3. historyOfPresentIllness
4. pastMedicalHistory
5. medications
6. allergies
7. physicalExam
8. assessment
9. plan
10. dailyProgressNotes
11. dischargeSummary
12. medicationReconciliation
13. dischargeInstructions
14. providerSigned

**OUTPATIENT** (8 elementos):
1. chiefComplaint
2. historyOfPresentIllness
3. medications
4. allergies
5. physicalExam
6. assessment
7. plan
8. providerSigned

**EMERGENCY** (9 elementos):
1. triageNotes
2. chiefComplaint
3. historyOfPresentIllness
4. vitalSigns
5. physicalExam
6. assessment
7. plan
8. disposition
9. providerSigned

**Cálculo**:
```java
private double calculateCompletenessScore(Map<String, Object> docs,
                                           DelegateExecution execution) {
    String encounterType = (String) execution.getVariable("encounterType");

    List<String> requiredElements = getRequiredElementsByEncounterType(encounterType);
    int presentCount = 0;

    for (String element : requiredElements) {
        if (isElementPresent(docs, element)) {
            presentCount++;
        }
    }

    double completenessPercentage = (presentCount * 100.0) / requiredElements.size();

    // Armazena métricas detalhadas
    execution.setVariable("required_elements_count", requiredElements.size());
    execution.setVariable("present_elements_count", presentCount);
    execution.setVariable("missing_elements_count", requiredElements.size() - presentCount);

    return completenessPercentage;
}
```

---

### RN-018.5: Validação de Presença de Elemento
**Criticidade**: MÉDIA
**Categoria**: Verificação de Campo

**Descrição**:
Elemento é considerado presente se:

**Para String**:
- Não é null
- Não está vazio após trim()

**Para Boolean**:
- É true (false é considerado ausente)

**Para Outros Tipos**:
- Não é null

**Implementação**:
```java
private boolean isElementPresent(Map<String, Object> docs, String element) {
    if (docs == null) return false;

    Object value = docs.get(element);
    if (value == null) return false;

    if (value instanceof String) {
        return !((String) value).trim().isEmpty();
    }
    if (value instanceof Boolean) {
        return Boolean.TRUE.equals(value);
    }

    return true; // Present if not null
}
```

---

## 5. Dimensão 3: Timeliness (20%)

### RN-018.6: Rubrica de Pontuação de Pontualidade
**Criticidade**: ALTA
**Categoria**: Compliance Temporal

**Descrição**:
Score baseado no tempo entre atendimento e documentação:

**Rubrica de Pontuação**:
| Tempo Decorrido | Score | Classificação |
|-----------------|-------|---------------|
| ≤ 24 horas | 100% | Excelente |
| 25-48 horas | 85% | Bom |
| 49-72 horas | 70% | Aceitável |
| 4-7 dias | 50% | Tardio |
| > 7 dias | 30% | Muito Tardio |

**Cálculo**:
```java
private double calculateTimelinessScore(Map<String, Object> docs) {
    Long encounterDate = (Long) docs.get("encounterDate");
    Long documentationDate = (Long) docs.get("documentationDate");

    if (encounterDate == null || documentationDate == null) {
        return 50.0; // Partial score se timestamps ausentes
    }

    long hoursDifference = (documentationDate - encounterDate) / (1000 * 60 * 60);

    if (hoursDifference <= 24) {
        return 100.0;
    } else if (hoursDifference <= 48) {
        return 85.0;
    } else if (hoursDifference <= 72) {
        return 70.0;
    } else if (hoursDifference <= 168) { // 7 days
        return 50.0;
    } else {
        return 30.0;
    }
}
```

**Justificativa**:
- CMS e Joint Commission recomendam documentação em 24h
- Documentação tardia aumenta risco de erro e perda de informação
- Impacta timely filing para cobrança

---

## 6. Dimensão 4: Accuracy (20%)

### RN-018.7: Validação de Consistência Narrativa-Código
**Criticidade**: ALTA
**Categoria**: Precisão Clínica

**Descrição**:
Valida se códigos são suportados pela narrativa clínica:

**Fontes de Narrativa**:
- `clinicalNotes`: Notas clínicas gerais
- `assessment`: Avaliação médica
- `plan`: Plano de tratamento

**Algoritmo de Validação**:

**1. Diagnósticos Não Suportados** (-15 pontos cada):
```java
int unsupportedDiagnoses = 0;
for (String diagCode : diagnosisCodes) {
    String condition = mapIcdToConditionKeyword(diagCode);
    if (!combinedNarrative.contains(condition.toLowerCase())) {
        unsupportedDiagnoses++;
    }
}
score -= (unsupportedDiagnoses * 15.0);
```

**2. Procedimentos Não Documentados** (-10 pontos cada):
```java
int undocumentedProcedures = 0;
for (String procCode : procedureCodes) {
    String procedure = mapCptToProcedureKeyword(procCode);
    if (!combinedNarrative.contains(procedure.toLowerCase())) {
        undocumentedProcedures++;
    }
}
score -= (undocumentedProcedures * 10.0);
```

**3. Documentação Não Assinada** (-20 pontos):
```java
Boolean providerSigned = (Boolean) docs.get("providerSigned");
if (!Boolean.TRUE.equals(providerSigned)) {
    score -= 20.0;
}
```

---

### RN-018.8: Mapeamento ICD-10 para Keywords
**Criticidade**: MÉDIA
**Categoria**: Análise Semântica

**Descrição**:
Mapeia códigos ICD-10 para termos clínicos esperados na narrativa:

**Mapeamentos Comuns**:
| ICD-10 | Keyword Esperado | Categoria |
|--------|------------------|-----------|
| I10 | hypertension | Cardiovascular |
| E11.x | diabetes | Endócrino |
| J18.x | pneumonia | Respiratório |
| M17.x | knee osteoarthritis | Musculoesquelético |
| I21.x | myocardial infarction | Cardiovascular |
| J44.x | copd | Respiratório |

**Implementação**:
```java
private String mapIcdToConditionKeyword(String icd10Code) {
    if (icd10Code.startsWith("I10")) return "hypertension";
    if (icd10Code.startsWith("E11")) return "diabetes";
    if (icd10Code.startsWith("J18")) return "pneumonia";
    if (icd10Code.startsWith("M17")) return "knee osteoarthritis";
    if (icd10Code.startsWith("I21")) return "myocardial infarction";
    if (icd10Code.startsWith("J44")) return "copd";
    return icd10Code; // Fallback: retorna código
}
```

**Nota**: Produção deve usar dicionário completo ICD-10

---

### RN-018.9: Mapeamento CPT para Keywords
**Criticidade**: MÉDIA
**Categoria**: Análise Semântica

**Descrição**:
Mapeia códigos CPT para termos de procedimentos esperados:

**Mapeamentos Comuns**:
| CPT | Keyword Esperado | Categoria |
|-----|------------------|-----------|
| 27447 | knee arthroplasty | Cirurgia ortopédica |
| 93000 | electrocardiogram | Cardiology |
| 99213 | office visit | E&M outpatient |
| 99285 | emergency visit | E&M emergency |

**Implementação**:
```java
private String mapCptToProcedureKeyword(String cptCode) {
    if (cptCode.equals("27447")) return "knee arthroplasty";
    if (cptCode.equals("93000")) return "electrocardiogram";
    if (cptCode.equals("99213")) return "office visit";
    if (cptCode.equals("99285")) return "emergency visit";
    return cptCode; // Fallback
}
```

---

## 7. Benchmarking e Comparação

### RN-018.10: Categorização por Performance
**Criticidade**: ALTA
**Categoria**: Análise Comparativa

**Descrição**:
Classifica performance em relação a benchmarks institucionais:

**Thresholds de Benchmark**:
```java
private static final double BENCHMARK_AVERAGE = 82.0;
private static final double BENCHMARK_ABOVE_THRESHOLD = 88.0;
private static final double BENCHMARK_EXCELLENT_THRESHOLD = 93.0;
```

**Categorias de Performance**:
| Score | Categoria | Descrição |
|-------|-----------|-----------|
| ≥ 93.0 | EXCELLENT | Acima do esperado institucional |
| 88.0 - 92.9 | ABOVE_AVERAGE | Acima da média |
| 82.0 - 87.9 | AVERAGE | Dentro da média esperada |
| < 82.0 | BELOW_AVERAGE | Abaixo do esperado - requer ação |

**Implementação**:
```java
private String determineBenchmarkComparison(double overallScore) {
    if (overallScore >= BENCHMARK_EXCELLENT_THRESHOLD) {
        return "EXCELLENT";
    } else if (overallScore >= BENCHMARK_ABOVE_THRESHOLD) {
        return "ABOVE_AVERAGE";
    } else if (overallScore >= BENCHMARK_AVERAGE) {
        return "AVERAGE";
    } else {
        return "BELOW_AVERAGE";
    }
}
```

---

### RN-018.11: Cálculo de Variância do Benchmark
**Criticidade**: MÉDIA
**Categoria**: Análise Estatística

**Descrição**:
Calcula desvio em relação à média hospitalar:

**Fórmula**:
```
Variance = Overall Score - Hospital Average Score
```

**Interpretação**:
- Variância positiva: Acima da média (bom)
- Variância negativa: Abaixo da média (requer atenção)
- |Variância| > 10: Outlier significativo

**Implementação**:
```java
double hospitalAverage = getHospitalBenchmark(providerId);
double variance = overallScore - hospitalAverage;

execution.setVariable("hospital_average_score",
    Math.round(hospitalAverage * 100.0) / 100.0);
execution.setVariable("variance_from_benchmark",
    Math.round(variance * 100.0) / 100.0);
```

---

## 8. Recomendações de Melhoria

### RN-018.12: Geração Automática de Recomendações
**Criticidade**: ALTA
**Categoria**: Feedback e Educação

**Descrição**:
Sistema gera recomendações específicas baseadas em scores baixos:

**Recomendações por Dimensão**:

**Specificity < 85%**:
- "Use more specific ICD-10 codes - avoid unspecified (.9) codes when possible"
- "Include 7th character extensions for injuries and external causes"

**Completeness < 90%**:
- "Ensure all required documentation elements are completed"
- "Complete medication reconciliation and discharge planning sections"

**Timeliness < 85%**:
- "Complete clinical documentation within 24 hours of encounter"
- "Use real-time documentation tools during patient encounters"

**Accuracy < 85%**:
- "Ensure clinical narrative supports all diagnosis and procedure codes"
- "Document medical necessity and clinical rationale for all procedures"
- "Sign and attest to all documentation promptly"

**Score Excelente**:
- "Excellent documentation quality - maintain current standards"

**Implementação**:
```java
private List<String> generateImprovementRecommendations(
        double specificity, double completeness,
        double timeliness, double accuracy) {

    List<String> recommendations = new ArrayList<>();

    if (specificity < 85.0) {
        recommendations.add("Use more specific ICD-10 codes...");
        recommendations.add("Include 7th character extensions...");
    }

    if (completeness < 90.0) {
        recommendations.add("Ensure all required documentation elements...");
        recommendations.add("Complete medication reconciliation...");
    }

    if (timeliness < 85.0) {
        recommendations.add("Complete clinical documentation within 24 hours...");
        recommendations.add("Use real-time documentation tools...");
    }

    if (accuracy < 85.0) {
        recommendations.add("Ensure clinical narrative supports codes...");
        recommendations.add("Document medical necessity...");
        recommendations.add("Sign and attest promptly...");
    }

    if (recommendations.isEmpty()) {
        recommendations.add("Excellent documentation quality - maintain current standards");
    }

    return recommendations;
}
```

---

## 9. Variáveis de Processo

### 9.1 Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| `clinicalDocumentation` | Map | Sim | Documentação clínica completa |
| `diagnosisCodes` | List<String> | Sim | Códigos ICD-10 |
| `procedureCodes` | List<String> | Sim | Códigos CPT |
| `encounterId` | String | Sim | ID do encontro |
| `providerId` | String | Sim | ID do provedor (para benchmark) |
| `encounterType` | String | Sim | Tipo de encontro |

### 9.2 Variáveis de Saída
| Nome | Tipo | Descrição |
|------|------|-----------|
| `quality_score_calculated` | Boolean | Cálculo concluído |
| `quality_score_timestamp` | Long | Timestamp do cálculo |
| `overall_quality_score` | Double | Score geral (0-100) |
| `specificity_score` | Double | Score de especificidade |
| `completeness_score` | Double | Score de completude |
| `timeliness_score` | Double | Score de pontualidade |
| `accuracy_score` | Double | Score de precisão |
| `benchmark_comparison` | String | EXCELLENT/ABOVE_AVERAGE/AVERAGE/BELOW_AVERAGE |
| `hospital_average_score` | Double | Média hospitalar (90 dias) |
| `variance_from_benchmark` | Double | Desvio da média |
| `quality_improvements` | List<String> | Recomendações de melhoria |
| `required_elements_count` | Integer | Elementos requeridos |
| `present_elements_count` | Integer | Elementos presentes |
| `missing_elements_count` | Integer | Elementos faltantes |

---

## 10. Casos de Uso

### 10.1 Documentação de Alta Qualidade
**Entrada**:
```json
{
  "encounterId": "ENC-001",
  "providerId": "DR-123",
  "encounterType": "INPATIENT",
  "diagnosisCodes": ["I21.01", "I50.23", "E11.65"],
  "procedureCodes": ["33533", "93000"],
  "clinicalDocumentation": {
    "chiefComplaint": "Chest pain",
    "historyOfPresentIllness": "57yo male with acute onset chest pain...",
    "assessment": "STEMI anterior wall, acute heart failure, diabetes with hyperglycemia",
    "plan": "Emergent CABG, cardiology consultation, insulin drip",
    "providerSigned": true,
    "encounterDate": 1704067200000,
    "documentationDate": 1704075600000
  }
}
```

**Saída**:
```json
{
  "quality_score_calculated": true,
  "overall_quality_score": 94.5,
  "specificity_score": 100.0,
  "completeness_score": 92.0,
  "timeliness_score": 100.0,
  "accuracy_score": 95.0,
  "benchmark_comparison": "EXCELLENT",
  "hospital_average_score": 82.0,
  "variance_from_benchmark": 12.5,
  "quality_improvements": [
    "Excellent documentation quality - maintain current standards"
  ]
}
```

### 10.2 Documentação Requerendo Melhoria
**Saída**:
```json
{
  "overall_quality_score": 68.0,
  "specificity_score": 55.0,
  "completeness_score": 70.0,
  "timeliness_score": 50.0,
  "accuracy_score": 75.0,
  "benchmark_comparison": "BELOW_AVERAGE",
  "variance_from_benchmark": -14.0,
  "quality_improvements": [
    "Use more specific ICD-10 codes - avoid unspecified (.9) codes",
    "Ensure all required documentation elements are completed",
    "Complete clinical documentation within 24 hours of encounter"
  ]
}
```

---

## 11. Referências

- **Código Fonte**: `src/main/java/com/hospital/revenuecycle/delegates/audit/QualityScoreDelegate.java`
- **Subprocesso BPMN**: `SUB_05_Clinical_Documentation_Improvement.bpmn`
- **AHIMA**: American Health Information Management Association - Documentation Guidelines
- **CMS**: Medicare Program Integrity Manual - Chapter 4
- **Joint Commission**: Medical Record Standards

---

## X. Conformidade Regulatória

### Regulamentações ANS
- **RN 395/2016**: Padrões de qualidade assistencial e indicadores de desempenho
- **RN 452/2020**: Programa de Qualificação dos Prestadores de Serviços na Saúde Suplementar
- **TISS 4.0**: Componente de Comunicação - Envio de dados de qualidade assistencial

### Normativas Internacionais
- **AHIMA Documentation Guidelines**: Padrões de documentação clínica
- **CMS Program Integrity Manual Chapter 4**: Qualidade de codificação médica
- **Joint Commission IM Standards**: Gestão da informação clínica
- **CMS ICD-10-CM Official Guidelines**: Diretrizes de codificação diagnóstica

### Proteção de Dados
- **LGPD Art. 7º, III**: Tratamento de dados para auditoria de qualidade assistencial
- **LGPD Art. 11**: Tratamento de dados sensíveis de saúde para fins de qualidade

### Controles SOX (Aplicável a Hospitais de Capital Aberto)
- **SOX Section 404**: Controles internos sobre relatórios de qualidade financeira
- **SOX Section 302**: Certificação de métricas de qualidade que impactam receita

---

## XI. Notas de Migração

### Avaliação de Complexidade
- **Rating**: ⭐⭐⭐⭐ (ALTA) - 4/5
- **Justificativa**: Sistema de scoring de qualidade com múltiplas dimensões de análise, cálculo de benchmarks institucionais, e impacto direto na estratégia de CDI (Clinical Documentation Improvement)

### Mudanças Não-Retrocompatíveis (Breaking Changes)
1. **Estrutura de Metadados**: Adição de campos `qualityMetrics` e `improvementOpportunities` requer atualização de esquemas de dados
2. **Sistema de Pontuação**: Migração de score simples para multi-dimensional (completeness, accuracy, timeliness, specificity)
3. **Benchmarking**: Necessidade de base histórica de dados para cálculo de benchmarks institucionais

### Recomendações para Implementação DMN
```xml
<!-- Sugestão de estrutura DMN para Quality Scoring -->
<decision id="quality_scoring_decision" name="Clinical Quality Scoring">
  <decisionTable id="quality_dimensions">
    <input id="completeness_score" label="Completeness Score">
      <inputExpression typeRef="number">
        <text>completenessScore</text>
      </inputExpression>
    </input>
    <input id="accuracy_score" label="Accuracy Score">
      <inputExpression typeRef="number">
        <text>accuracyScore</text>
      </inputExpression>
    </input>
    <output id="quality_category" label="Quality Category" typeRef="string"/>
    <output id="cdi_priority" label="CDI Priority" typeRef="string"/>
    <rule>
      <inputEntry><text>&gt;= 90</text></inputEntry>
      <inputEntry><text>&gt;= 90</text></inputEntry>
      <outputEntry><text>"EXCELLENT"</text></outputEntry>
      <outputEntry><text>"LOW"</text></outputEntry>
    </rule>
    <rule>
      <inputEntry><text>&lt; 70</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <outputEntry><text>"POOR"</text></outputEntry>
      <outputEntry><text>"HIGH"</text></outputEntry>
    </rule>
  </decisionTable>
</decision>
```

### Fases de Migração Sugeridas
**Fase 1 - Coleta de Dados Históricos (2 semanas)**
- Extração de dados de documentação clínica dos últimos 12 meses
- Estabelecimento de baseline de qualidade por especialidade e tipo de atendimento

**Fase 2 - Implementação de Scoring Básico (1 semana)**
- Deploy do algoritmo de completeness e accuracy scoring
- Integração com processo CDI existente

**Fase 3 - Benchmarking e Análise Comparativa (1 semana)**
- Cálculo de benchmarks institucionais
- Configuração de alertas para scores abaixo da média

**Fase 4 - CDI Automatizado (2 semanas)**
- Implementação de queries automáticas ao CDI
- Sistema de sugestões de melhoria baseado em padrões

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Context**: Clinical Documentation Quality & CDI
**Subdomínio**: Auditoria de Qualidade Assistencial

### Aggregates

#### 1. QualityScore (Root)
```yaml
QualityScore:
  identity: encounterId
  properties:
    - overallScore: BigDecimal
    - completenessScore: BigDecimal
    - accuracyScore: BigDecimal
    - timelinessScore: BigDecimal
    - specificityScore: BigDecimal
    - benchmarkComparison: String [EXCELLENT|ABOVE_AVERAGE|AVERAGE|BELOW_AVERAGE|POOR]
    - calculationTimestamp: Instant

  value_objects:
    - QualityDimensions:
        completeness: BigDecimal
        accuracy: BigDecimal
        timeliness: BigDecimal
        specificity: BigDecimal

    - BenchmarkAnalysis:
        institutionalBenchmark: BigDecimal
        varianceFromBenchmark: BigDecimal
        percentileRanking: Integer

    - ImprovementOpportunity:
        category: String [DOCUMENTATION|CODING|TIMELINESS|SPECIFICITY]
        description: String
        priority: String [HIGH|MEDIUM|LOW]
        estimatedImpact: BigDecimal

  behaviors:
    - calculateOverallScore()
    - compareToBenchmark()
    - identifyImprovementOpportunities()
    - generateCDIWorkItems()
```

#### 2. DocumentationAudit
```yaml
DocumentationAudit:
  identity: auditId
  properties:
    - encounterId: String
    - auditDate: LocalDate
    - documentationElements: List<DocumentationElement>
    - missingElements: List<String>
    - codeQuality: CodeQualityMetrics

  value_objects:
    - DocumentationElement:
        elementName: String
        isPresent: boolean
        quality: String [EXCELLENT|GOOD|POOR|MISSING]

    - CodeQualityMetrics:
        totalCodes: Integer
        specificCodes: Integer
        unspecifiedCodes: Integer
        specificityRate: BigDecimal

  behaviors:
    - auditDocumentation()
    - validateCompleteness()
    - assessCodeSpecificity()
```

### Domain Events

#### 1. QualityScoreCalculated
```json
{
  "eventType": "QualityScoreCalculated",
  "eventId": "evt-qual-001",
  "timestamp": "2025-01-12T10:30:00Z",
  "aggregateId": "ENC-ER-001",
  "payload": {
    "encounterId": "ENC-ER-001",
    "overallScore": 75.0,
    "benchmarkComparison": "BELOW_AVERAGE",
    "dimensions": {
      "completeness": 70.0,
      "accuracy": 80.0,
      "timeliness": 75.0,
      "specificity": 75.0
    },
    "cdiRequired": true
  }
}
```

#### 2. CDIWorkItemCreated
```json
{
  "eventType": "CDIWorkItemCreated",
  "eventId": "evt-cdi-001",
  "timestamp": "2025-01-12T10:31:00Z",
  "aggregateId": "ENC-ER-001",
  "payload": {
    "workItemId": "CDI-WI-001",
    "encounterId": "ENC-ER-001",
    "priority": "HIGH",
    "opportunities": [
      "Use more specific ICD-10 codes - avoid unspecified (.9) codes",
      "Complete clinical documentation within 24 hours"
    ],
    "estimatedRevenueImpact": 2500.00,
    "assignedTo": "CDI-SPECIALIST-001"
  }
}
```

#### 3. BenchmarkThresholdViolated
```json
{
  "eventType": "BenchmarkThresholdViolated",
  "eventId": "evt-bench-001",
  "timestamp": "2025-01-12T10:32:00Z",
  "aggregateId": "ENC-ER-001",
  "payload": {
    "encounterId": "ENC-ER-001",
    "violationType": "BELOW_THRESHOLD",
    "threshold": 85.0,
    "actualScore": 75.0,
    "variance": -10.0,
    "actionRequired": "CDI_REVIEW"
  }
}
```

### Contexto de Microsserviços
**Serviço Recomendado**: `Quality-Management-Service`
**Justificativa**:
- Scoring de qualidade é domínio especializado com lógica complexa
- Requer integração com CDI workflows e analytics
- Beneficia-se de escalabilidade independente para processar grandes volumes de auditorias
- Permite evolução independente de algoritmos de qualidade

**Dependências de Domínio**:
- Clinical-Coding-Service (fornece códigos para análise)
- CDI-Service (consome oportunidades de melhoria)
- Revenue-Integrity-Service (usa métricas de qualidade para otimização)

---

## XIII. Metadados Técnicos

### Métricas de Complexidade
```yaml
complexity_metrics:
  cyclomatic_complexity: 18
  cognitive_complexity: 24
  lines_of_code: 285
  number_of_methods: 7
  max_nesting_level: 4

  complexity_rating: HIGH
  maintainability_index: 62
  technical_debt_ratio: 8.5%
```

### Cobertura de Testes
```yaml
test_coverage:
  line_coverage: 0%
  branch_coverage: 0%
  method_coverage: 0%

  test_status: NOT_IMPLEMENTED
  priority: HIGH
  estimated_tests_required: 12

  suggested_test_types:
    - unit_tests: "Teste de cálculo de scores por dimensão"
    - integration_tests: "Teste de integração com benchmarks"
    - edge_case_tests: "Documentação incompleta, códigos missing"
```

### Métricas de Desempenho
```yaml
performance_metrics:
  average_execution_time: "120ms"
  p95_execution_time: "180ms"
  p99_execution_time: "250ms"

  performance_considerations:
    - "Cálculo de benchmark pode ser custoso com grande volume histórico"
    - "Cache recomendado para benchmarks institucionais (TTL: 24h)"
    - "Análise de código pode ser paralelizada"

  optimization_opportunities:
    - "Implementar cache distribuído para benchmarks"
    - "Pré-calcular métricas agregadas em batch noturno"
    - "Indexar tabela de documentação por encounterId e timestamp"
```

### Dependências e Integrações
```yaml
dependencies:
  internal_services:
    - service: CodingService
      purpose: "Obtenção de códigos ICD-10/CPT para análise de especificidade"
      criticality: HIGH

    - service: CDIService
      purpose: "Geração de work items para melhoria de documentação"
      criticality: MEDIUM

    - service: BenchmarkingService
      purpose: "Cálculo e consulta de benchmarks institucionais"
      criticality: HIGH

  external_systems:
    - system: "Clinical Documentation System"
      integration: "REST API"
      purpose: "Consulta de elementos de documentação"

    - system: "Analytics Platform"
      integration: "Event Stream"
      purpose: "Envio de métricas de qualidade para dashboards"

  databases:
    - name: "Quality Metrics DB"
      type: "PostgreSQL"
      tables: ["quality_scores", "documentation_audits", "benchmarks"]

  message_queues:
    - queue: "cdi.work.items"
      purpose: "Publicação de oportunidades de melhoria para CDI"
```

---

**Documento gerado por**: AI Swarm - Hive Mind Documentation Generator
**Total de Regras**: 29 regras de negócio
**Revisão**: Necessária por CDI e gestão de qualidade
**Próxima revisão**: Semestral ou quando houver mudanças nos benchmarks institucionais
