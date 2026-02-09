# RN-015: Detecção de Anomalias com Machine Learning

**Delegate**: `MLAnomalyDelegate.java`
**Subprocesso BPMN**: SUB_09_Analytics_Reporting
**Prioridade**: CRÍTICA
**Versão**: 1.0
**Última Atualização**: 2026-01-12

---

## 1. Visão Geral

### 1.1 Objetivo
Detectar anomalias em transações do ciclo de receita usando algoritmos de Machine Learning, identificando padrões suspeitos, fraudes e inconsistências que requerem investigação.

### 1.2 Escopo
- Análise de valores de sinistros anômalos
- Detecção de padrões de pagamento suspeitos
- Identificação de upcoding e unbundling
- Análise de padrões temporais (horários/finais de semana)

### 1.3 Stakeholders
- **Primários**: Auditoria interna, compliance, controles internos
- **Secundários**: Gestores financeiros, segurança da informação

---

## 2. Regras de Negócio

### RN-015.1: Validação de Tipo de Transação
**Criticidade**: ALTA
**Categoria**: Validação de Entrada

**Descrição**:
O tipo de transação deve ser um dos quatro tipos suportados pelo sistema:
- `claim`: Análise de valores de sinistros
- `payment`: Análise de padrões de pagamento
- `coding`: Análise de codificação médica
- `timing`: Análise de padrões temporais

**Implementação**:
```java
private void validateTransactionType(String transactionType) {
    String normalizedType = transactionType.toLowerCase();
    if (!normalizedType.equals("claim") &&
        !normalizedType.equals("payment") &&
        !normalizedType.equals("coding") &&
        !normalizedType.equals("timing")) {
        throw new IllegalArgumentException(
            "Invalid transaction type: " + transactionType);
    }
}
```

**Erro**: `IllegalArgumentException` com mensagem descritiva

---

### RN-015.2: Níveis de Sensibilidade
**Criticidade**: ALTA
**Categoria**: Configuração de Detecção

**Descrição**:
O sistema oferece três níveis de sensibilidade para controlar a taxa de falsos positivos:

| Nível | Threshold | Uso Recomendado |
|-------|-----------|-----------------|
| **Low** | 0.8 | Apenas anomalias críticas (investigação obrigatória) |
| **Medium** | 0.65 | Balanceamento (padrão do sistema) |
| **High** | 0.5 | Detecção ampla (mais alertas para revisão) |

**Implementação**:
```java
private double getSensitivityThreshold(String level) {
    switch (level.toLowerCase()) {
        case "low": return 0.8;
        case "high": return 0.5;
        case "medium":
        default: return 0.65;
    }
}
```

**Default**: Medium (0.65)

---

### RN-015.3: Detecção de Anomalias em Sinistros (Claim)
**Criticidade**: CRÍTICA
**Categoria**: Análise de Valores

**Descrição**:
Detecta sinistros com valores anormalmente altos ou baixos usando **Isolation Forest**:
- Compara com histórico de procedimentos similares
- Identifica outliers estatísticos (Z-score > 3)
- Considera especialidade médica e complexidade

**Indicadores de Anomalia**:
- Valor 3x acima da média para o procedimento
- Valor 50% abaixo do custo esperado
- Combinação de procedimentos inconsistente

**Implementação**:
```java
AnomalyResult result = anomalyService.detectAnomaly(
    "claim", transactionId, transactionData, threshold);
```

**Ações Recomendadas**:
- Score 0.8-1.0: `investigate` (investigar imediatamente)
- Score 0.65-0.8: `review` (revisão prioritária)
- Score 0.5-0.65: `flag` (marcar para auditoria posterior)
- Score < 0.5: `approve` (aprovar normalmente)

---

### RN-015.4: Detecção de Anomalias em Pagamentos (Payment)
**Criticidade**: CRÍTICA
**Categoria**: Análise de Padrões

**Descrição**:
Identifica padrões suspeitos em pagamentos usando **Pattern Matching**:
- Pagamentos duplicados (mesmo valor, mesmo beneficiário)
- Valores redondos suspeitos (ex: exatamente R$ 10.000,00)
- Pagamentos fora do horário comercial
- Múltiplos pagamentos em sequência rápida

**Indicadores de Anomalia**:
```java
// Pagamento duplicado
if (existsPayment(amount, beneficiary, within24Hours)) {
    anomalyScore += 0.4;
}

// Valor redondo suspeito
if (amount % 1000 == 0 && amount > 5000) {
    anomalyScore += 0.2;
}
```

**Implementação**:
```java
AnomalyResult result = anomalyService.detectAnomaly(
    "payment", transactionId, transactionData, threshold);
```

---

### RN-015.5: Detecção de Upcoding e Unbundling (Coding)
**Criticidade**: CRÍTICA
**Categoria**: Análise de Codificação

**Descrição**:
Detecta práticas abusivas de codificação médica:

**Upcoding**: Uso de código DRG mais caro sem justificativa clínica
- DRG 470 (major joint replacement with MCC) vs DRG 471 (without MCC)
- Verificação de alinhamento com diagnósticos secundários

**Unbundling**: Separação de procedimentos que deveriam ser cobrados em conjunto
- CPT 80053 (comprehensive metabolic panel) vs componentes individuais
- Verificação de códigos mutualmente exclusivos

**Implementação**:
```java
// Detecção de unbundling
if (hasBundledCode("80053") && hasComponentCodes("80048", "80061")) {
    anomalyScore = 0.9; // CRITICAL
    anomalyType = "UNBUNDLING";
}

// Detecção de upcoding
if (isDRGUpcodedWithoutJustification(drgCode, diagnoses)) {
    anomalyScore = 0.85;
    anomalyType = "UPCODING";
}
```

---

### RN-015.6: Detecção de Anomalias Temporais (Timing)
**Criticidade**: MÉDIA
**Categoria**: Análise de Padrões Temporais

**Descrição**:
Identifica padrões temporais suspeitos:
- Faturamento em finais de semana (exceto emergência)
- Cobranças após horário comercial (22h-6h)
- Pico de procedimentos eletivos em feriados
- Documentação retroativa (>7 dias após atendimento)

**Implementação**:
```java
// Faturamento em final de semana
if (isWeekend(billingDate) && !isEmergency(encounterType)) {
    anomalyScore += 0.3;
}

// Cobrança após horário
if (isAfterHours(billingTime) && !is24HourService(department)) {
    anomalyScore += 0.4;
}
```

---

### RN-015.7: Idempotência de Detecção
**Criticidade**: ALTA
**Categoria**: Controle de Execução

**Descrição**:
A detecção de anomalias **DEVE ser idempotente** para evitar:
- Alertas duplicados para a mesma transação
- Múltiplas notificações para o mesmo caso
- Contagem incorreta de anomalias

**Implementação**:
```java
@Override
public boolean requiresIdempotency() {
    return true; // SEMPRE ATIVADO
}
```

**Comportamento**:
- Primeira execução: cria alerta e registra resultado
- Execuções subsequentes: retorna resultado já calculado
- Chave de idempotência: `processInstanceId + activityId + transactionId`

---

## 3. Variáveis de Processo

### 3.1 Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| `transactionType` | String | Sim | Tipo: claim, payment, coding, timing |
| `transactionId` | String | Sim | ID único da transação |
| `transactionData` | Map<String, Object> | Sim | Dados detalhados da transação |
| `sensitivityLevel` | String | Não | Nível: low, medium (default), high |

### 3.2 Variáveis de Saída
| Nome | Tipo | Descrição |
|------|------|-----------|
| `anomaly_detected` | Boolean | Se anomalia foi detectada |
| `anomaly_score` | Double | Score 0.0-1.0 (maior = mais anômalo) |
| `anomaly_type` | String | Categoria da anomalia |
| `anomaly_details` | Map | Detalhes dos achados |
| `recommended_action` | String | Ação: review, investigate, flag, approve |

### 3.3 Estrutura de `anomaly_details`
```json
{
  "detection_method": "isolation_forest",
  "confidence": 0.87,
  "indicators": [
    {
      "indicator": "unusually_high_charge",
      "expected_value": 5000.00,
      "actual_value": 15000.00,
      "deviation_percentage": 200
    }
  ],
  "similar_cases": 3,
  "historical_average": 5200.00
}
```

---

## 4. Algoritmos de Machine Learning

### 4.1 Isolation Forest (Sinistros e Pagamentos)
**Conceito**: Isola anomalias em árvores de decisão
**Vantagens**:
- Não requer treinamento supervisionado
- Eficiente para grandes volumes
- Detecta outliers multidimensionais

**Aplicação**:
```
Score = Profundidade Média de Isolamento / Profundidade Máxima
Score alto = anomalia (poucas divisões necessárias para isolar)
```

### 4.2 DBSCAN (Clustering de Padrões)
**Conceito**: Agrupa transações similares e identifica outliers
**Parâmetros**:
- ε (epsilon): 5% do valor médio
- MinPoints: 5 transações

**Aplicação**:
```
Clusters densos = padrão normal
Pontos isolados = anomalias
```

### 4.3 Statistical Outlier Detection
**Conceito**: Z-score e IQR (Interquartile Range)
**Thresholds**:
- Z-score > 3: outlier severo
- IQR: Q1 - 1.5×IQR ou Q3 + 1.5×IQR

---

## 5. Códigos de Erro e Alertas

### 5.1 Tipos de Anomalia
| Tipo | Severidade | Descrição |
|------|------------|-----------|
| `UNUSUALLY_HIGH_CHARGE` | HIGH | Valor 3x acima da média |
| `DUPLICATE_PAYMENT` | CRITICAL | Pagamento duplicado detectado |
| `UNBUNDLING` | CRITICAL | Separação indevida de procedimentos |
| `UPCODING` | HIGH | DRG inflacionado sem justificativa |
| `AFTER_HOURS_BILLING` | MEDIUM | Faturamento fora do horário |
| `WEEKEND_ELECTIVE` | MEDIUM | Procedimento eletivo em final de semana |

### 5.2 Ações Recomendadas
| Ação | Threshold | Descrição |
|------|-----------|-----------|
| `investigate` | Score ≥ 0.8 | Investigação imediata obrigatória |
| `review` | Score 0.65-0.79 | Revisão prioritária por auditor |
| `flag` | Score 0.5-0.64 | Marcar para auditoria posterior |
| `approve` | Score < 0.5 | Aprovar normalmente (baixo risco) |

---

## 6. Casos de Uso

### 6.1 Detecção de Valor Anômalo em Sinistro
**Entrada**:
```json
{
  "transactionType": "claim",
  "transactionId": "CLM-2026-001234",
  "transactionData": {
    "procedureCode": "27447",
    "chargeAmount": 45000.00,
    "diagnosis": "M17.11",
    "encounterType": "INPATIENT"
  },
  "sensitivityLevel": "medium"
}
```

**Saída**:
```json
{
  "anomaly_detected": true,
  "anomaly_score": 0.92,
  "anomaly_type": "UNUSUALLY_HIGH_CHARGE",
  "anomaly_details": {
    "expected_value": 15000.00,
    "actual_value": 45000.00,
    "deviation_percentage": 200
  },
  "recommended_action": "investigate"
}
```

### 6.2 Detecção de Unbundling
**Entrada**:
```json
{
  "transactionType": "coding",
  "transactionId": "CLM-2026-005678",
  "transactionData": {
    "procedureCodes": ["80053", "80048", "80061"],
    "encounterType": "OUTPATIENT"
  }
}
```

**Saída**:
```json
{
  "anomaly_detected": true,
  "anomaly_score": 0.90,
  "anomaly_type": "UNBUNDLING",
  "anomaly_details": {
    "bundled_code": "80053",
    "component_codes": ["80048", "80061"],
    "potential_overcharge": 120.00
  },
  "recommended_action": "investigate"
}
```

---

## 7. Conformidade e Auditoria

### 7.1 Regulamentações
- **Federal False Claims Act**: Prevenção de fraude em faturamento
- **CMS**: Compliance com Medicare/Medicaid
- **ANS**: Detecção de fraudes em saúde suplementar

### 7.2 Requisitos de Auditoria
- Todos os alertas devem ser registrados com timestamp
- Investigações devem ter rastreabilidade completa
- Falsos positivos devem ser documentados

---

## 8. Notas de Implementação

### 8.1 Performance
- Algoritmos ML são computacionalmente intensivos
- Considerar execução assíncrona para grandes volumes
- Cache de padrões históricos recomendado

### 8.2 Logging
```
INFO: Starting ML anomaly detection: transactionId=CLM-001234, type=claim, sensitivity=medium
WARN: ANOMALY DETECTED: transactionId=CLM-001234, score=0.92, type=UNUSUALLY_HIGH_CHARGE, action=investigate
INFO: No anomaly detected: transactionId=CLM-001235, score=0.45
```

### 8.3 Dependência de Serviços
```java
@Autowired
private AnomalyDetectionService anomalyService;

AnomalyResult detectAnomaly(
    String transactionType,
    String transactionId,
    Map<String, Object> transactionData,
    double threshold
);
```

---

## 9. Referências

- **Código Fonte**: `src/main/java/com/hospital/revenuecycle/delegates/analytics/MLAnomalyDelegate.java`
- **Service**: `AnomalyDetectionService.java`
- **Subprocesso BPMN**: `SUB_09_Analytics_Reporting.bpmn`
- **Algoritmos**: Isolation Forest, DBSCAN, Statistical Outlier Detection
- **Federal False Claims Act**: 31 U.S.C. §§ 3729–3733

---

## X. Conformidade Regulatória

### 10.1 Regulamentações Federais (EUA)
- **Federal False Claims Act (31 U.S.C. §§ 3729–3733)**: Prevenção de fraudes em healthcare billing
- **CMS Compliance Program Guidance**: Detecção proativa de fraudes e abusos
- **OIG Work Plan**: Auditorias de upcoding, unbundling e padrões suspeitos

### 10.2 Requisitos ANS (Brasil)
- **RN 443/2019**: Prevenção de fraudes em saúde suplementar
- **RN 388/2015**: Qualidade assistencial - detecção de inconsistências
- **RN 465/2021**: Transparência em procedimentos e cobranças

### 10.3 LGPD
- **Art. 20 LGPD**: Direito de revisão de decisões automatizadas (explicabilidade de ML)
- **Art. 11 LGPD**: Processamento de dados sensíveis para prevenção de fraudes (base legal)
- **Art. 48 LGPD**: Comunicação de incidentes de segurança detectados por ML
- **Retenção**: 5 anos para alertas de anomalias (auditoria de compliance)

### 10.4 Explicabilidade e Fairness
- **GDPR Article 22**: Right to explanation - anomaly_details deve ter indicadores interpretáveis
- **Bias Mitigation**: Algoritmos não devem discriminar por demographic factors
- **Human Review**: Scores > 0.8 SEMPRE requerem validação humana

### 10.5 Trilha de Auditoria
- **Registro obrigatório**: Todos os alertas com timestamp, score, indicadores
- **Campos auditáveis**: Algoritmo usado, confidence level, similar cases
- **False Positive Tracking**: Documentação de falsos positivos para fine-tuning
- **Período de retenção**: 7 anos (Federal False Claims Act)

---

## XI. Notas de Migração - Camunda 7 para Camunda 8

### 11.1 Camunda 8 - Alternativa Recomendada
- **Padrão**: Microserviço ML Standalone com API REST
- **Implementação**: Anomaly Detection Service desacoplado do workflow
- **Vantagens**: Escalabilidade de ML models, GPU acceleration, A/B testing de modelos

### 11.2 Nível de Complexidade
- **Complexidade de Migração**: ALTA (7-15 dias)
- **Justificativa**: ML models complexos, feature engineering, múltiplos algoritmos

### 11.3 Breaking Changes
- **Delegate → ML API**: Mudança de padrão sync para API HTTP com latência variável
- **Model Versioning**: Necessidade de versionamento de modelos (MLflow)
- **Feature Store**: Requer infraestrutura de features (Feast ou similar)
- **Batch vs Real-time**: Split entre detecção real-time e batch retraining

### 11.4 Arquitetura Camunda 8
```
Zeebe Process → HTTP Service Task → ML API Gateway
                                      ↓
                            [Model Serving Layer]
                                      ↓
                 [Isolation Forest] [DBSCAN] [Statistical]
                                      ↓
                          [Feature Store] ← [Training Pipeline]
```

### 11.5 Considerações Técnicas
- **Latência**: API pode ter latency > 2s para cálculos complexos
- **Fallback**: Regras heurísticas simples se ML API indisponível
- **Monitoring**: Prometheus metrics para model drift detection
- **Retraining**: Pipeline automático mensal com novos padrões

---

## XII. Mapeamento DDD

### 12.1 Bounded Context
- **Contexto Delimitado**: `Fraud Detection & Anomaly Analysis`
- **Linguagem Ubíqua**: Anomaly, outlier, fraud detection, upcoding, unbundling, isolation forest

### 12.2 Aggregate Root
- **Aggregate**: `AnomalyAlert`
- **Entidades relacionadas**:
  - `Transaction` (claim, payment, coding, timing)
  - `AnomalyIndicator` (indicadores detectados)
  - `InvestigationCase` (caso de investigação criado)

### 12.3 Domain Events
- **AnomalyDetected**: Anomalia detectada acima do threshold
- **CriticalAnomalyDetected**: Score >= 0.8 - requer investigação imediata
- **FalsePositiveReported**: Usuário marcou como falso positivo (feedback para ML)
- **InvestigationStarted**: Caso de investigação criado para a anomalia

### 12.4 Value Objects
- `AnomalyScore` (0.0-1.0, com confidence level)
- `DetectionMethod` (isolation_forest, dbscan, statistical)
- `AnomalyType` (upcoding, unbundling, duplicate_payment, etc)

### 12.5 Candidato a Microserviço
- **Serviço**: `anomaly-detection-service`
- **Responsabilidades**: Detecção de fraudes, análise de padrões, alertas
- **Integrações**: Claims Service, Payment Service, Investigation Queue, BI Analytics

---

## XIII. Metadados Técnicos

### 13.1 Características
- **Tipo**: Service Delegate (Camunda 7 JavaDelegate)
- **Execução**: Síncrona (blocking) - pode ser lenta para ML inference
- **Idempotência**: CRÍTICA (SEMPRE habilitada para evitar alertas duplicados)
- **Transacional**: Não (read-only com side-effect de criar alerta)

### 13.2 Métricas de Qualidade
- **Complexidade Ciclomática**: ALTA (4 tipos de análise + múltiplos indicadores)
- **Cobertura de Testes Recomendada**: 85% (lógica complexa com ML)
- **Tempo de Execução Esperado**: 1-5s (ML inference + feature extraction)

### 13.3 Impacto de Performance
- **I/O**: HIGH (queries para similaridade histórica)
- **CPU**: HIGH (algoritmos de ML: Isolation Forest, DBSCAN)
- **Memória**: HIGH (feature vectors e modelos carregados em memória)

### 13.4 Dependências de Runtime
- Spring Framework (DI)
- Camunda BPM Engine 7.x
- AnomalyDetectionService (custom, com ML libraries)
- Scikit-learn / Apache Mahout (ML algorithms)
- SLF4J (logging)

### 13.5 ML Model Performance
- **False Positive Rate**: Target < 10% (sensibilidade medium)
- **True Positive Rate**: Target > 80% (detecção de fraudes reais)
- **Model Retraining**: Mensal com feedback de investigações
- **Feature Drift Detection**: Monitoramento contínuo de feature distributions

---

**Documento gerado por**: AI Swarm - Hive Mind Documentation Generator
**Revisão**: Necessária por compliance e auditoria interna
**Próxima revisão**: Semestral ou quando houver mudanças nos algoritmos
