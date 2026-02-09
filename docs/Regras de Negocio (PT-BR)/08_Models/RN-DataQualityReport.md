# RN-DataQualityReport - Relatório de Qualidade de Dados

**Categoria:** Modelo de Domínio - Analytics
**Arquivo:** `com.hospital.revenuecycle.domain.analytics.DataQualityReport`
**Tipo:** Domain Model

---

## Descrição
Modelo de domínio que representa relatórios de qualidade de dados para o ciclo de receita. Rastreia métricas de completude, precisão, consistência e pontualidade dos dados, identificando problemas e recomendando remediações.

## Estrutura Principal

```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DataQualityReport {
    @JsonProperty("report_id")
    private String reportId;

    @JsonProperty("data_source")
    private String dataSource;

    @JsonProperty("generation_timestamp")
    private LocalDateTime generationTimestamp;

    @JsonProperty("period_start")
    private LocalDateTime periodStart;

    @JsonProperty("period_end")
    private LocalDateTime periodEnd;

    @JsonProperty("overall_quality_score")
    private Double overallQualityScore;

    @JsonProperty("completeness_score")
    private Double completenessScore;

    @JsonProperty("accuracy_score")
    private Double accuracyScore;

    @JsonProperty("consistency_score")
    private Double consistencyScore;

    @JsonProperty("timeliness_score")
    private Double timelinessScore;

    @JsonProperty("quality_issues")
    private List<QualityIssue> qualityIssues;

    @JsonProperty("data_volume_metrics")
    private DataVolumeMetrics volumeMetrics;

    @JsonProperty("remediation_recommendations")
    private List<String> remediationRecommendations;

    @JsonProperty("trend_analysis")
    private Map<String, Object> trendAnalysis;

    @JsonProperty("metadata")
    private Map<String, Object> metadata;
}
```

## Atributos Principais

### Identificação
- **reportId:** Identificador único do relatório
- **dataSource:** Fonte dos dados analisados (EHR, billing, claims)
- **generationTimestamp:** Momento de geração do relatório
- **periodStart/periodEnd:** Período de análise

### Scores de Qualidade (0.0 - 1.0)

#### overallQualityScore
- **Tipo:** Double (0.0 - 1.0)
- **Descrição:** Score agregado de qualidade geral
- **Cálculo:** Média ponderada dos scores individuais
- **Thresholds:**
  - >= 0.95: Excelente
  - >= 0.85: Bom
  - >= 0.70: Aceitável
  - < 0.70: Requer atenção

#### completenessScore
- **Descrição:** Medida de campos preenchidos vs vazios
- **Fórmula:** `campos_preenchidos / total_campos`

#### accuracyScore
- **Descrição:** Precisão dos dados (validações contra regras)
- **Validações:** Formato, range, consistência

#### consistencyScore
- **Descrição:** Consistência entre sistemas/tabelas relacionadas
- **Exemplo:** Paciente_ID consistente entre billing e clinical

#### timelinessScore
- **Descrição:** Pontualidade da entrada/atualização de dados
- **Critério:** Dados atualizados dentro do SLA

## Estruturas Aninhadas

### QualityIssue
```java
@Data
@Builder
public static class QualityIssue {
    private String issueType;          // "MISSING", "INVALID", "INCONSISTENT"
    private String severity;            // "LOW", "MEDIUM", "HIGH", "CRITICAL"
    private String description;         // Descrição do problema
    private Long affectedRecords;       // Quantidade de registros afetados
    private String fieldName;           // Campo com problema
    private List<String> exampleValues; // Valores de exemplo
    private String suggestedFix;        // Recomendação de correção
}
```

**Tipos de Issues:**
- **MISSING:** Campos obrigatórios vazios
- **INVALID:** Formato ou valor inválido
- **INCONSISTENT:** Inconsistência entre sistemas
- **DUPLICATE:** Registros duplicados
- **OUTDATED:** Dados desatualizados

**Severidades:**
- **CRITICAL:** Impede processamento (ex: falta patient_id)
- **HIGH:** Impacta faturamento significativamente
- **MEDIUM:** Reduz eficiência do processo
- **LOW:** Problema cosmético ou menor

### DataVolumeMetrics
```java
@Data
@Builder
public static class DataVolumeMetrics {
    private Long totalRecords;      // Total de registros analisados
    private Long validRecords;      // Registros válidos
    private Long invalidRecords;    // Registros inválidos
    private Long missingRecords;    // Registros com dados faltantes
    private Long duplicateRecords;  // Registros duplicados
}
```

## Métodos

### meetsQualityThreshold
```java
public boolean meetsQualityThreshold(Double minScore)
```

**Descrição:** Verifica se qualidade atinge threshold mínimo

**Exemplo:**
```java
if (report.meetsQualityThreshold(0.85)) {
    // Qualidade aceitável, pode processar
} else {
    // Qualidade baixa, requer remediação
}
```

### countCriticalIssues
```java
public long countCriticalIssues()
```

**Descrição:** Conta issues com severidade CRITICAL

**Uso:**
```java
long criticalCount = report.countCriticalIssues();
if (criticalCount > 0) {
    log.error("Encontrados {} issues críticos", criticalCount);
    // Bloquear processamento
}
```

## Regras de Negócio

### RN-DQR-001: Threshold Mínimo de Qualidade
**Descrição:** Dados devem atingir score mínimo para processamento
**Threshold Padrão:** 0.70 (70%)
**Ação se Abaixo:** Bloquear faturamento, exigir remediação

### RN-DQR-002: Issues Críticos Bloqueantes
**Descrição:** Qualquer issue CRITICAL bloqueia processamento
**Exemplos Críticos:**
- Falta de patient_id
- Falta de authorization_number (quando obrigatório)
- Códigos de procedimento inválidos

### RN-DQR-003: Cálculo de Score Geral
**Descrição:** Score geral é média ponderada dos scores individuais
**Fórmula:**
```
overallScore = (completeness * 0.30) +
               (accuracy * 0.30) +
               (consistency * 0.25) +
               (timeliness * 0.15)
```

### RN-DQR-004: Recomendações Automáticas
**Descrição:** Sistema gera recomendações baseadas nos issues encontrados
**Exemplos:**
- "Implementar validação obrigatória de campo X"
- "Sincronizar dados entre sistema A e B"
- "Revisar processo de entrada de dados"

### RN-DQR-005: Análise de Tendência
**Descrição:** Comparar qualidade ao longo do tempo
**Métricas:**
- Melhoria/piora percentual
- Issues recorrentes
- Efetividade de remediações

## Casos de Uso

### 1. Validação Pré-Faturamento
```java
DataQualityReport report = analyticsService.generateDataQualityReport(
    "billing_data", periodStart, periodEnd);

if (!report.meetsQualityThreshold(0.85)) {
    log.warn("Qualidade de dados abaixo do threshold");
    // Notificar equipe de qualidade
    // Bloquear envio de lote
}

if (report.countCriticalIssues() > 0) {
    throw new CriticalDataQualityException(
        "Issues críticos encontrados: " + report.countCriticalIssues());
}
```

### 2. Monitoramento Contínuo
```java
// Gerar relatório diário
ScheduledTask dailyQualityCheck() {
    DataQualityReport report = analyticsService.generateDataQualityReport(
        "all_sources",
        LocalDateTime.now().minusDays(1),
        LocalDateTime.now());

    // Enviar alerta se qualidade cair
    if (report.getOverallQualityScore() < 0.75) {
        alertService.sendQualityAlert(report);
    }

    // Persistir para análise de tendência
    reportRepository.save(report);
}
```

### 3. Auditoria de Dados
```java
// Relatório detalhado para auditoria
DataQualityReport report = analyticsService.generateDataQualityReport(
    "clinical_data", auditPeriodStart, auditPeriodEnd);

// Gerar relatório PDF
PdfReport pdfReport = reportGenerator.generatePDF(report);

// Incluir todas issues
List<QualityIssue> allIssues = report.getQualityIssues();
for (QualityIssue issue : allIssues) {
    auditLog.logIssue(issue);
}
```

## Integração com Analytics Service

### Geração de Relatório
```java
@Service
public class AnalyticsService {
    public DataQualityReport generateDataQualityReport(
        String dataSource,
        LocalDateTime periodStart,
        LocalDateTime periodEnd) {

        // 1. Coletar dados do período
        List<DataRecord> records = dataRepository.findByPeriod(
            dataSource, periodStart, periodEnd);

        // 2. Calcular scores
        Double completeness = calculateCompletenessScore(records);
        Double accuracy = calculateAccuracyScore(records);
        Double consistency = calculateConsistencyScore(records);
        Double timeliness = calculateTimelinessScore(records);

        // 3. Identificar issues
        List<QualityIssue> issues = identifyQualityIssues(records);

        // 4. Gerar recomendações
        List<String> recommendations = generateRecommendations(issues);

        // 5. Construir relatório
        return DataQualityReport.builder()
            .reportId(UUID.randomUUID().toString())
            .dataSource(dataSource)
            .generationTimestamp(LocalDateTime.now())
            .periodStart(periodStart)
            .periodEnd(periodEnd)
            .completenessScore(completeness)
            .accuracyScore(accuracy)
            .consistencyScore(consistency)
            .timelinessScore(timeliness)
            .overallQualityScore(calculateOverallScore(...))
            .qualityIssues(issues)
            .volumeMetrics(calculateVolumeMetrics(records))
            .remediationRecommendations(recommendations)
            .build();
    }
}
```

## Exemplo Completo

```json
{
  "report_id": "DQR-2024-001",
  "data_source": "billing_system",
  "generation_timestamp": "2024-01-12T14:30:00",
  "period_start": "2024-01-01T00:00:00",
  "period_end": "2024-01-11T23:59:59",
  "overall_quality_score": 0.82,
  "completeness_score": 0.88,
  "accuracy_score": 0.85,
  "consistency_score": 0.75,
  "timeliness_score": 0.80,
  "quality_issues": [
    {
      "issueType": "MISSING",
      "severity": "CRITICAL",
      "description": "Campo authorization_number vazio",
      "affectedRecords": 15,
      "fieldName": "authorization_number",
      "exampleValues": [],
      "suggestedFix": "Implementar validação obrigatória"
    },
    {
      "issueType": "INVALID",
      "severity": "HIGH",
      "description": "CPF com formato inválido",
      "affectedRecords": 8,
      "fieldName": "patient_cpf",
      "exampleValues": ["123.456", "000.000.000-00"],
      "suggestedFix": "Adicionar validação de dígito verificador"
    }
  ],
  "data_volume_metrics": {
    "totalRecords": 1000,
    "validRecords": 977,
    "invalidRecords": 23,
    "missingRecords": 15,
    "duplicateRecords": 0
  },
  "remediation_recommendations": [
    "Implementar validação obrigatória de authorization_number",
    "Adicionar validação de CPF no ponto de entrada",
    "Treinar equipe sobre importância de dados completos"
  ],
  "trend_analysis": {
    "score_change_pct": -2.5,
    "recurring_issues": ["authorization_number"],
    "improvement_areas": ["accuracy"]
  }
}
```

## Performance

- **Geração:** O(n) onde n = número de registros
- **Cálculo de Scores:** Otimizado com queries agregadas
- **Armazenamento:** JSON compacto (~5KB por relatório)

## Conformidade

- **LGPD:** Não expõe dados sensíveis, apenas agregações
- **ANS:** Suporta requisitos de qualidade de dados TISS
- **ISO 8000:** Padrão de qualidade de dados

## Referências
- `AnalyticsService.java` - Gerador de relatórios
- `MetricsData.java` - Métricas relacionadas
- `MLPrediction.java` - Predições de qualidade
