# Regras de Negócio: AnalyticsService

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/service/AnalyticsService.java`
> **Categoria:** ANALYTICS (Análise de Dados e KPIs)
> **Total de Regras:** 10

## 📋 Sumário Executivo

O AnalyticsService é uma interface crítica para cálculo de KPIs em tempo real, previsões com machine learning, e análise de qualidade de dados no ciclo de receita. Este serviço fornece insights actionable para otimização de receita, detecção de anomalias, e análise de tendências.

O serviço suporta tanto operações em tempo real quanto processamento em batch, permitindo análise histórica e monitoramento contínuo. Integração com Kafka permite streaming de métricas para dashboards em tempo real.

## 📜 Catálogo de Regras

### RN-ANALYTICS-001: Cálculo de Métricas em Tempo Real

**Descrição:** Calcula métricas de KPI em tempo real baseado no tipo de métrica e parâmetros fornecidos.

**Lógica:**
```
ENTRADA:
  - metricType: Tipo de métrica a calcular
  - parameters: Parâmetros específicos para cálculo

PROCESSAR:
  - Identificar tipo de métrica solicitada
  - Extrair parâmetros de configuração
  - Executar cálculo específico
  - Aplicar regras de negócio por tipo

RETORNAR MetricsData:
  - metricName: Nome da métrica
  - value: Valor calculado
  - timestamp: Timestamp do cálculo
  - metadata: Metadados adicionais
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| metricType | String | Obrigatório | "claim_approval_rate", "days_to_payment" |
| parameters | Map<String,Object> | Obrigatório | {period: "30d", payer: "UNIMED"} |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: calculateRealTimeMetrics
- Linhas: 18-24

---

### RN-ANALYTICS-002: Cálculo de Métricas em Batch

**Descrição:** Executa cálculo de múltiplas métricas para período histórico específico.

**Lógica:**
```
ENTRADA:
  - periodStart: Data inicial do período
  - periodEnd: Data final do período
  - metricTypes: Lista de métricas a calcular

PROCESSAR para cada métrica:
  - Extrair dados do período especificado
  - Calcular valores agregados
  - Aplicar fórmulas de negócio
  - Validar consistência dos resultados

RETORNAR List<MetricsData>:
  - Uma entrada por métrica calculada
  - Timestamp e metadados por cálculo
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| periodStart | LocalDateTime | Obrigatório | 2025-01-01T00:00:00 |
| periodEnd | LocalDateTime | Obrigatório, >= periodStart | 2025-01-31T23:59:59 |
| metricTypes | List&lt;String&gt; | Obrigatório, não-vazio | ["revenue", "denials", "dso"] |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: calculateBatchMetrics
- Linhas: 26-38

---

### RN-ANALYTICS-003: Geração de Previsão com ML

**Descrição:** Gera previsão usando modelo de machine learning treinado.

**Lógica:**
```
ENTRADA:
  - modelName: Nome do modelo ML a usar
  - inputFeatures: Features de entrada para previsão

PROCESSAR:
  - Carregar modelo ML especificado
  - Validar features de entrada
  - Executar inferência do modelo
  - Calcular confidence score

RETORNAR MLPrediction:
  - predictedValue: Valor previsto
  - confidence: Confiança da previsão (0-1)
  - features: Features usadas
  - modelVersion: Versão do modelo
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| modelName | String | Obrigatório | "denial_prediction", "revenue_forecast" |
| inputFeatures | Map<String,Object> | Obrigatório | {payer:"UNIMED", amount:5000, procedure:"93000"} |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: generatePrediction
- Linhas: 40-47

---

### RN-ANALYTICS-004: Treinamento de Modelo ML

**Descrição:** Treina ou re-treina modelo de machine learning com dados históricos.

**Lógica:**
```
ENTRADA:
  - modelName: Identificador do modelo
  - trainingData: Dados históricos para treinamento

PROCESSAR:
  - Validar qualidade dos dados de treinamento
  - Split train/test/validation
  - Treinar modelo com algoritmo específico
  - Avaliar performance (accuracy, F1-score, etc.)
  - Validar métricas contra thresholds

RETORNAR:
  - true: Treinamento bem-sucedido e modelo deployado
  - false: Falha no treinamento ou métricas insuficientes
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| modelName | String | Obrigatório | "glosa_predictor" |
| trainingData | List&lt;Map&gt; | Obrigatório, mínimo 1000 samples | [{features..., label...}, ...] |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: trainModel
- Linhas: 49-56

---

### RN-ANALYTICS-005: Geração de Relatório de Qualidade de Dados

**Descrição:** Analisa qualidade dos dados em fonte específica, identificando problemas de completude, acurácia e consistência.

**Lógica:**
```
ENTRADA:
  - dataSource: Sistema fonte a analisar
  - periodStart: Início do período de análise
  - periodEnd: Fim do período de análise

PROCESSAR:
  - Analisar completude (campos obrigatórios preenchidos)
  - Analisar acurácia (valores dentro de ranges esperados)
  - Analisar consistência (relações entre campos)
  - Identificar outliers e anomalias
  - Calcular scores de qualidade

RETORNAR DataQualityReport:
  - completenessScore: Score de completude (0-100)
  - accuracyScore: Score de acurácia (0-100)
  - consistencyScore: Score de consistência (0-100)
  - issues: Lista de problemas identificados
  - recommendations: Recomendações de correção
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| dataSource | String | Obrigatório | "TASY_CLAIMS", "INSURANCE_RESPONSES" |
| periodStart | LocalDateTime | Obrigatório | 2025-01-01T00:00:00 |
| periodEnd | LocalDateTime | Obrigatório | 2025-01-31T23:59:59 |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: generateDataQualityReport
- Linhas: 58-70

---

### RN-ANALYTICS-006: Streaming de Métricas em Tempo Real

**Descrição:** Inicia streaming contínuo de métricas para Kafka topic.

**Lógica:**
```
ENTRADA:
  - metricType: Tipo de métrica a streamer
  - intervalSeconds: Intervalo de atualização

PROCESSAR:
  - Criar producer Kafka para métrica
  - Configurar intervalo de atualização
  - Iniciar loop de cálculo e publicação
  - Registrar subscription ativa

EFEITO:
  - Métricas publicadas em Kafka topic
  - Dashboard atualizado em tempo real
  - Alertas disparados se thresholds ultrapassados
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| metricType | String | Obrigatório | "realtime_revenue" |
| intervalSeconds | int | Obrigatório, mínimo 1, máximo 3600 | 60 |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: startMetricsStreaming
- Linhas: 72-78

---

### RN-ANALYTICS-007: Parada de Streaming de Métricas

**Descrição:** Para streaming contínuo de métricas específica.

**Lógica:**
```
ENTRADA:
  - metricType: Tipo de métrica a parar

PROCESSAR:
  - Localizar subscription ativa
  - Finalizar loop de publicação
  - Fechar producer Kafka
  - Remover subscription do registro

EFEITO:
  - Streaming parado
  - Recursos liberados
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| metricType | String | Obrigatório | "realtime_revenue" |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: stopMetricsStreaming
- Linhas: 80-85

---

### RN-ANALYTICS-008: Análise de Tendência

**Descrição:** Analisa tendência histórica de métrica específica.

**Lógica:**
```
ENTRADA:
  - metricType: Métrica a analisar
  - lookbackDays: Dias de histórico a considerar

PROCESSAR:
  - Extrair valores históricos
  - Calcular médias móveis
  - Identificar tendência (crescente/decrescente/estável)
  - Calcular taxa de mudança
  - Projetar valores futuros

RETORNAR Map<String, Object>:
  - trend: "increasing"/"decreasing"/"stable"
  - changeRate: Taxa de mudança (%)
  - forecast: Projeção para próximo período
  - confidence: Confiança da análise
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| metricType | String | Obrigatório | "approval_rate" |
| lookbackDays | int | Obrigatório, mínimo 7, máximo 365 | 90 |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: analyzeTrend
- Linhas: 87-94

---

### RN-ANALYTICS-009: Detecção de Anomalias

**Descrição:** Detecta valores anômalos em métrica usando análise estatística.

**Lógica:**
```
ENTRADA:
  - metricType: Métrica a monitorar
  - threshold: Threshold de desvio padrão

PROCESSAR:
  - Calcular média e desvio padrão históricos
  - Identificar valores fora do threshold
  - Classificar severidade da anomalia
  - Gerar alertas se necessário

RETORNAR List<MetricsData>:
  - Lista de pontos anômalos detectados
  - Cada entrada com severity e deviation
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| metricType | String | Obrigatório | "claim_processing_time" |
| threshold | double | Obrigatório, típico 2.0-3.0 | 2.5 |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: detectAnomalies
- Linhas: 96-103

---

### RN-ANALYTICS-010: Comparação de Performance

**Descrição:** Compara métricas entre dois períodos de tempo.

**Lógica:**
```
ENTRADA:
  - metricType: Métrica a comparar
  - currentPeriodStart: Início do período atual
  - currentPeriodEnd: Fim do período atual
  - comparisonPeriodStart: Início do período de comparação
  - comparisonPeriodEnd: Fim do período de comparação

PROCESSAR:
  - Calcular métrica para período atual
  - Calcular métrica para período de comparação
  - Calcular diferença absoluta e percentual
  - Determinar se mudança é significativa
  - Identificar fatores contribuintes

RETORNAR Map<String, Object>:
  - currentValue: Valor do período atual
  - comparisonValue: Valor do período de comparação
  - absoluteDifference: Diferença absoluta
  - percentageChange: Mudança percentual
  - isSignificant: Se mudança é estatisticamente significativa
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| metricType | String | Obrigatório | "net_revenue" |
| currentPeriodStart | LocalDateTime | Obrigatório | 2025-02-01T00:00:00 |
| currentPeriodEnd | LocalDateTime | Obrigatório | 2025-02-28T23:59:59 |
| comparisonPeriodStart | LocalDateTime | Obrigatório | 2025-01-01T00:00:00 |
| comparisonPeriodEnd | LocalDateTime | Obrigatório | 2025-01-31T23:59:59 |

**Rastreabilidade:**
- Arquivo: AnalyticsService.java
- Método: comparePerformance
- Linhas: 105-121

---

## 📊 Métricas e Monitoramento

**Operação:** analytics_operations
**Interface:** Service Interface (implementação em concrete classes)
**Padrão:** Strategy Pattern para diferentes tipos de analytics
**Streaming:** Kafka integration para real-time metrics

## 🔗 Integrações

- **Machine Learning Service:** Treinamento e inferência de modelos
- **Data Warehouse:** Extração de dados históricos
- **Kafka:** Streaming de métricas em tempo real
- **TimeSeries Database:** Armazenamento de séries temporais
- **Dashboard Service:** Visualização de KPIs

## 📝 Observações Técnicas

1. **Interface Design:** Definição de contrato claro para implementações variadas
2. **Real-Time vs Batch:** Suporte para ambos os modos de operação
3. **ML Integration:** Abstração para diferentes frameworks de ML
4. **Data Quality:** Análise abrangente de qualidade de dados
5. **Streaming:** Publicação contínua de métricas via Kafka
6. **Trend Analysis:** Análise estatística de tendências históricas
7. **Anomaly Detection:** Detecção baseada em desvio padrão
8. **Performance Comparison:** Análise comparativa entre períodos

---

## X. Conformidade Regulatória

### Análise de Dados e KPIs
- **SOX Section 404**: Controles sobre métricas financeiras e KPIs de receita
- **HIPAA Security Rule**: Proteção de PHI em análises agregadas
- **LGPD Art. 7**: Minimização de dados em analytics (apenas dados necessários)

### Machine Learning e AI
- **LGPD Art. 20**: Direito de revisão de decisões automatizadas por ML
- **AI Act (EU)**: Transparência e explicabilidade de modelos de ML
- **FDA 21 CFR Part 11**: Validação de modelos usados em decisões clínicas

### Qualidade de Dados
- **ISO 8000**: Padrões de qualidade de dados
- **ANS RN 395/2016**: Qualidade de dados de faturamento enviados à ANS

---

## XI. Notas de Migração

### Avaliação de Complexidade
- **Rating**: ⭐⭐⭐⭐ (ALTA) - 4/5
- **Justificativa**: Interface complexa com 10 operações diversas, integração ML, streaming, análise estatística

### Mudanças Não-Retrocompatíveis (Breaking Changes)
1. **ML Model Format**: Mudanças no formato de modelos requerem re-treinamento
2. **Metrics Schema**: Alterações em MetricsData quebram consumers existentes
3. **Kafka Topic Structure**: Mudanças em topic structure afetam streaming

### Recomendações para Implementação
**Implementations sugeridas:**
- `DefaultAnalyticsService`: Implementação padrão com PostgreSQL/TimescaleDB
- `MLAnalyticsService`: Implementação focada em ML com TensorFlow
- `StreamAnalyticsService`: Implementação otimizada para Kafka Streams

### Fases de Migração Sugeridas
**Fase 1 - Core Metrics (4 semanas)**
- Implementar calculateRealTimeMetrics
- Implementar calculateBatchMetrics
- Setup TimeSeries database

**Fase 2 - ML Integration (3 semanas)**
- Implementar generatePrediction
- Implementar trainModel
- Setup ML infrastructure

**Fase 3 - Streaming & Advanced (3 semanas)**
- Implementar metrics streaming
- Implementar trend analysis
- Implementar anomaly detection

**Fase 4 - Quality & Comparison (2 semanas)**
- Implementar data quality reports
- Implementar performance comparison
- Setup dashboards

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Context**: Analytics & Business Intelligence
**Subdomínio**: Revenue Cycle Optimization & Predictive Analytics

### Aggregates

#### 1. MetricsData (Root)
```yaml
MetricsData:
  identity: metricId
  properties:
    - metricName: String
    - metricType: MetricType [KPI|PREDICTION|QUALITY|TREND]
    - value: BigDecimal
    - timestamp: Instant
    - period: DateRange
    - dimensions: Map<String, String>
    - metadata: Map<String, Object>

  value_objects:
    - Dimension:
        name: String
        value: String
        type: DimensionType [PAYER|DEPARTMENT|PROCEDURE|PROVIDER]

    - MetricMetadata:
        calculationMethod: String
        dataSource: String
        confidence: BigDecimal
        sampleSize: Integer

  behaviors:
    - calculate()
    - validate()
    - enrich()
    - publish()
```

#### 2. MLPrediction (Root)
```yaml
MLPrediction:
  identity: predictionId
  properties:
    - modelName: String
    - modelVersion: String
    - predictedValue: BigDecimal
    - confidence: BigDecimal
    - inputFeatures: Map<String, Object>
    - predictionTimestamp: Instant

  value_objects:
    - ModelMetadata:
        algorithm: String
        trainingDate: LocalDate
        accuracy: BigDecimal
        f1Score: BigDecimal

    - FeatureImportance:
        featureName: String
        importance: BigDecimal

  behaviors:
    - predict()
    - explain()
    - validate()
```

### Domain Events

#### 1. MetricCalculated
```json
{
  "eventType": "MetricCalculated",
  "eventId": "evt-metric-001",
  "timestamp": "2025-01-12T10:30:00Z",
  "payload": {
    "metricId": "METRIC-001",
    "metricName": "net_revenue",
    "value": 1500000.00,
    "period": "2025-01",
    "dimensions": {"department": "cardiology"}
  }
}
```

#### 2. AnomalyDetected
```json
{
  "eventType": "AnomalyDetected",
  "eventId": "evt-anomaly-001",
  "timestamp": "2025-01-12T10:31:00Z",
  "payload": {
    "metricName": "claim_processing_time",
    "currentValue": 45.2,
    "expectedValue": 15.5,
    "deviation": 2.8,
    "severity": "HIGH",
    "alertRequired": true
  }
}
```

### Contexto de Microsserviços
**Serviço Recomendado**: `Analytics-Service`
**Justificativa**:
- Operações computacionalmente intensivas (ML, agregações)
- Escalabilidade independente para cargas analíticas
- Isolamento de data warehouse e ML infrastructure

**Dependências de Domínio**:
- Revenue-Cycle-Service (dados operacionais)
- ML-Model-Service (inferência de modelos)
- Dashboard-Service (visualização)

---

## XIII. Metadados Técnicos

### Métricas de Complexidade
```yaml
complexity_metrics:
  interface_methods: 10
  complexity_rating: HIGH
  maintainability_index: N/A (interface)

  implementation_complexity:
    estimated_loc: 2000-3000
    estimated_classes: 8-12
    ml_models_required: 3-5
```

### Cobertura de Testes
```yaml
test_coverage:
  test_status: NOT_IMPLEMENTED
  priority: CRITICAL
  estimated_tests_required: 50+

  suggested_test_types:
    - unit_tests: "Cálculos de métricas, validações"
    - integration_tests: "ML integration, Kafka streaming"
    - performance_tests: "Batch processing, real-time streaming"
```

### Métricas de Desempenho
```yaml
performance_metrics:
  real_time_metrics: "<100ms"
  batch_metrics: "depends on period (seconds to minutes)"
  ml_prediction: "50-200ms"
  streaming_latency: "<500ms"

  optimization_opportunities:
    - "Caching de métricas frequentes"
    - "Pre-aggregação de dados históricos"
    - "GPU para ML inference"
    - "Kafka Streams para real-time"
```

### Dependências e Integrações
```yaml
dependencies:
  internal_services:
    - service: MLModelService
      purpose: "Treinamento e inferência"
      criticality: HIGH

  databases:
    - name: "Analytics DB"
      type: "TimescaleDB"
      purpose: "Séries temporais"

    - name: "Data Warehouse"
      type: "PostgreSQL"
      purpose: "Dados históricos"

  messaging:
    - platform: "Apache Kafka"
      purpose: "Streaming de métricas"
      topics: ["metrics.realtime", "metrics.alerts"]

  ml_infrastructure:
    - framework: "TensorFlow/Scikit-learn"
      purpose: "ML training and inference"
```

---
