# Regras de Negócio: AIDRGCodingDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/coding/AIDRGCodingDelegate.java`
> **Categoria:** CODING (Codificação Médica)
> **Total de Regras:** 6

## 📋 Sumário Executivo

O delegate AIDRGCodingDelegate utiliza inteligência artificial e machine learning para sugerir códigos DRG (Diagnosis Related Groups) otimizados. Esta funcionalidade é crucial para maximizar o reembolso hospitalar enquanto mantém a precisão da codificação e conformidade regulatória.

O sistema analisa diagnósticos clínicos, procedimentos realizados, comorbidades do paciente e idade para calcular o grupo DRG mais apropriado. A IA também identifica oportunidades de upgrade (MCC/CC) que podem aumentar significativamente o valor do reembolso sem comprometer a integridade da codificação.

## 📜 Catálogo de Regras

### RN-COD-DRG-001: Cálculo de DRG com IA

**Descrição:** Utiliza motor de IA/ML (CodingService) para calcular o DRG mais apropriado baseado em dados clínicos completos do atendimento.

**Lógica:**
```
ENTRADA:
  - diagnoses: Lista de diagnósticos clínicos
  - procedures: Lista de procedimentos realizados
  - comorbidities: Comorbidades do paciente
  - patientAge: Idade do paciente

PROCESSAR via CodingService.calculateDRG():
  - Analisar combinação de diagnósticos
  - Avaliar procedimentos realizados
  - Considerar comorbidades relevantes
  - Aplicar fatores de idade

RETORNAR DRGSuggestion:
  - suggestedDRG: Código DRG recomendado
  - confidence: Score de confiança (0-1)
  - estimatedReimbursement: Valor estimado de reembolso
  - hasMCC: Flag de complicações maiores
  - hasCC: Flag de comorbidades
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| encounterId | String | Obrigatório | "ENC-2025-001" |
| diagnoses | List&lt;String&gt; | Obrigatório, não-vazio | ["J18.9", "I10"] |
| procedures | List&lt;String&gt; | Obrigatório, não-vazio | ["31.1", "93.90"] |
| comorbidities | List&lt;String&gt; | Opcional, padrão vazio | ["E11.9"] |
| patientAge | Integer | Opcional, padrão 50 | 65 |

**Rastreabilidade:**
- Arquivo: AIDRGCodingDelegate.java
- Método: executeBusinessLogic
- Linhas: 64-66

---

### RN-COD-DRG-002: Armazenamento de Códigos ICD Sugeridos

**Descrição:** Persiste a lista de códigos ICD-10/ICD-11 selecionados pela IA para o DRG calculado.

**Lógica:**
```
APÓS cálculo de DRG bem-sucedido:
  - Armazenar icdCodes retornados pela IA
  - Códigos são ordenados por relevância (principal primeiro)
  - Códigos secundários incluem comorbidades significativas
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| icdCodes | List&lt;String&gt; | Escopo: Process | ["J18.9", "I10", "E11.9"] |

**Rastreabilidade:**
- Arquivo: AIDRGCodingDelegate.java
- Método: executeBusinessLogic
- Linha: 70

---

### RN-COD-DRG-003: Cálculo de Confiança da Codificação

**Descrição:** Calcula score de confiança (0-1) para a sugestão de DRG, indicando a probabilidade de aceitação pelo auditor.

**Lógica:**
```
CONFIANÇA calculada pela IA baseada em:
  - Qualidade dos dados de entrada
  - Completude da documentação clínica
  - Histórico de aceitação de casos similares
  - Complexidade da combinação de códigos

SE confidence < 0.7
ENTÃO emitir log de alerta:
  - "LOW DRG CONFIDENCE"
  - Recomendar revisão manual por codificador certificado
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| confidence | Double | 0.0 a 1.0, Escopo: Process | 0.85 |
| confidenceThreshold | Double | Fixo: 0.7 | 0.7 |

**Rastreabilidade:**
- Arquivo: AIDRGCodingDelegate.java
- Método: executeBusinessLogic
- Linhas: 91-94

---

### RN-COD-DRG-004: Identificação de Oportunidades de Upgrade

**Descrição:** Detecta quando DRG pode ser upgradado para versão com MCC (Major Complications/Comorbidities) ou CC (Complications/Comorbidities), aumentando reembolso.

**Lógica:**
```
AVALIAR comorbidades e complicações:
  - hasMCC: Complicações maiores presentes
  - hasCC: Comorbidades presentes

SE hasMCC = true OU hasCC = true
ENTÃO:
  - Registrar log de otimização de reembolso
  - DRG é automaticamente upgradado para versão com maior peso
  - Estimativa de reembolso reflete o upgrade
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| hasMCC | Boolean | Escopo: Process | true |
| hasCC | Boolean | Escopo: Process | false |

**Fórmula:**
```
DRG_WEIGHT = BASE_WEIGHT * (1 + MCC_FACTOR + CC_FACTOR)
onde:
  MCC_FACTOR = 0.25 (25% de aumento)
  CC_FACTOR = 0.10 (10% de aumento)
```

**Rastreabilidade:**
- Arquivo: AIDRGCodingDelegate.java
- Método: executeBusinessLogic
- Linhas: 74-75, 85-88

---

### RN-COD-DRG-005: Cálculo de Reembolso Estimado

**Descrição:** Estima o valor de reembolso baseado no DRG calculado, considerando pesos relativos e tabelas de pagamento.

**Lógica:**
```
CALCULAR estimatedReimbursement:
  - Buscar peso relativo do DRG na tabela
  - Aplicar valor base de reembolso do convênio
  - Ajustar por fatores geográficos
  - Incluir impacto de MCC/CC

FÓRMULA:
  estimatedReimbursement = BASE_RATE * DRG_WEIGHT * GEOGRAPHIC_FACTOR
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| estimatedReimbursement | BigDecimal | Escopo: Process, em R$ | 12500.00 |
| suggestedDRG | String | Código do DRG | "470" |

**Rastreabilidade:**
- Arquivo: AIDRGCodingDelegate.java
- Método: executeBusinessLogic
- Linha: 73

---

### RN-COD-DRG-006: Armazenamento de DRGs Alternativos

**Descrição:** Persiste lista de DRGs alternativos sugeridos pela IA para uso em caso de rejeição ou recurso de glosa.

**Lógica:**
```
ARMAZENAR alternativeDRGs:
  - Lista ordenada por similaridade clínica
  - Cada alternativa inclui estimativa de reembolso
  - Útil para recursos de glosa
  - Facilita discussão com auditores

TAMBÉM armazenar metadata:
  - codingDate: Data/hora da codificação
  - drgMethod: "AI_ML_GROUPER" (rastreabilidade)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| alternativeDRGs | List&lt;String&gt; | Escopo: Process | ["469", "471", "472"] |
| codingDate | LocalDateTime | Escopo: Process | 2025-01-11T10:30:00 |
| drgMethod | String | Fixo: "AI_ML_GROUPER" | "AI_ML_GROUPER" |

**Rastreabilidade:**
- Arquivo: AIDRGCodingDelegate.java
- Método: executeBusinessLogic
- Linhas: 72, 76-77

---

## 📊 Métricas e Monitoramento

**Operação:** ai_drg_coding
**Idempotência:** Sim (via BaseDelegate)
**Escopo de Variáveis:** PROCESS (compartilhadas com billing e audit)
**Motor de IA:** CodingService.calculateDRG()

## 🔗 Integrações

- **CodingService:** Serviço de ML para cálculo de DRG
- **DRG Grouper:** Motor de agrupamento de diagnósticos
- **Reimbursement Tables:** Tabelas de reembolso por convênio
- **Clinical Documentation:** Documentação clínica do atendimento

## 📝 Observações Técnicas

1. **Threshold de Confiança:** Codificações com confiança < 0.7 geram alerta para revisão manual
2. **Upgrade Automático:** Sistema detecta automaticamente oportunidades de MCC/CC
3. **Rastreabilidade:** Método de codificação é sempre registrado como "AI_ML_GROUPER"
4. **Alternativas:** Sistema sempre fornece DRGs alternativos para casos de recurso
5. **Otimização de Receita:** Logs específicos registram oportunidades de aumento de reembolso
6. **Compliance:** IA é treinada para manter conformidade com regulamentações de codificação

---

## X. Conformidade Regulatória

### Regulamentações de Codificação
- **CMS MS-DRG Grouper**: Lógica oficial de agrupamento de diagnósticos relacionados
- **ICD-10-CM Official Guidelines**: Diretrizes de codificação diagnóstica
- **ICD-10-PCS Guidelines**: Diretrizes de codificação de procedimentos
- **CMS Medicare Program Integrity Manual Chapter 4**: Precisão de codificação

### Auditoria e Compliance
- **OIG Work Plan**: Áreas de foco para auditoria de codificação e faturamento
- **False Claims Act (31 USC §3729)**: Penalidades por codificação fraudulenta ou incorreta
- **PEPPER Reports**: Program for Evaluating Payment Patterns Electronic Report

### Proteção de Dados e IA
- **LGPD Art. 20**: Direito de revisão de decisões automatizadas (codificação por IA)
- **HIPAA Privacy Rule**: Proteção de informações de saúde usadas no treinamento de IA
- **AI Act (EU)**: Requisitos de transparência e explicabilidade para IA em saúde

### Controles SOX
- **SOX Section 404**: Controles internos sobre reconhecimento de receita baseado em DRG
- **SOX Section 302**: Certificação da precisão de codificação que impacta receita

---

## XI. Notas de Migração

### Avaliação de Complexidade
- **Rating**: ⭐⭐⭐⭐⭐ (MUITO ALTA) - 5/5
- **Justificativa**: Sistema de IA/ML complexo para agrupamento DRG, otimização de reembolso via MCC/CC, múltiplas alternativas de codificação, e impacto crítico na receita

### Mudanças Não-Retrocompatíveis (Breaking Changes)
1. **Modelo de IA**: Requer treinamento de modelo ML com histórico de codificações validadas
2. **Estrutura de Resposta**: Campos `aiConfidence`, `alternativeDRGs`, `mccCcUpgrade` são novos e obrigatórios
3. **Método de Codificação**: Migração de codificação manual para híbrida (AI + revisão humana)

### Recomendações para Implementação DMN
```xml
<!-- Sugestão de estrutura DMN para DRG Validation -->
<decision id="drg_validation_decision" name="DRG Coding Validation">
  <decisionTable id="ai_confidence_review">
    <input id="ai_confidence" label="Confiança IA">
      <inputExpression typeRef="number">
        <text>aiConfidence</text>
      </inputExpression>
    </input>
    <input id="has_mcc_cc" label="Tem MCC/CC">
      <inputExpression typeRef="boolean">
        <text>hasMccCc</text>
      </inputExpression>
    </input>
    <input id="reimbursement_impact" label="Impacto Financeiro">
      <inputExpression typeRef="number">
        <text>reimbursementAmount</text>
      </inputExpression>
    </input>
    <output id="requires_review" label="Requer Revisão" typeRef="boolean"/>
    <output id="auto_approve" label="Aprovação Automática" typeRef="boolean"/>
    <rule>
      <inputEntry><text>&lt; 0.7</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <outputEntry><text>true</text></outputEntry>
      <outputEntry><text>false</text></outputEntry>
    </rule>
    <rule>
      <inputEntry><text>&gt;= 0.9</text></inputEntry>
      <inputEntry><text>false</text></inputEntry>
      <inputEntry><text>&lt; 50000</text></inputEntry>
      <outputEntry><text>false</text></outputEntry>
      <outputEntry><text>true</text></outputEntry>
    </rule>
  </decisionTable>
</decision>
```

### Fases de Migração Sugeridas
**Fase 1 - Preparação de Dados (3 semanas)**
- Coleta de histórico de codificações validadas (mínimo 10.000 casos)
- Limpeza e normalização de dados de treinamento
- Validação de qualidade de dados com codificadores certificados

**Fase 2 - Treinamento de Modelo ML (2 semanas)**
- Treinamento de modelo de agrupamento DRG
- Validação de acurácia (target: >95% concordância com codificadores humanos)
- Otimização de hiperparâmetros

**Fase 3 - Implementação Híbrida (2 semanas)**
- Deploy de modelo em ambiente de produção
- Configuração de thresholds de confiança
- Implementação de workflow de revisão humana

**Fase 4 - Monitoramento e Refinamento (Contínuo)**
- Monitoramento de precisão e falsos positivos
- Re-treinamento periódico com novos casos validados
- Ajuste de thresholds baseado em performance

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Context**: Clinical Coding & DRG Assignment
**Subdomínio**: Revenue Optimization & Compliance

### Aggregates

#### 1. DRGAssignment (Root)
```yaml
DRGAssignment:
  identity: assignmentId
  properties:
    - encounterId: String
    - drgCode: String
    - drgWeight: BigDecimal
    - reimbursementAmount: BigDecimal
    - assignmentMethod: CodingMethod [AI_ML_GROUPER|MANUAL|HYBRID]
    - assignmentTimestamp: Instant

  value_objects:
    - AIConfidence:
        confidenceScore: BigDecimal
        modelVersion: String
        trainingDataDate: LocalDate

    - MCCCCAnalysis:
        hasMCC: boolean
        hasCC: boolean
        upgradeOpportunity: boolean
        potentialUpgradeDRG: String
        reimbursementIncrease: BigDecimal

    - AlternativeDRG:
        alternativeDRGCode: String
        alternativeWeight: BigDecimal
        alternativeReimbursement: BigDecimal
        confidenceScore: BigDecimal
        justification: String

  behaviors:
    - calculateDRG()
    - analyzeMCCCCOpportunities()
    - suggestAlternativeDRGs()
    - validateCodingAccuracy()
```

#### 2. CodingReview
```yaml
CodingReview:
  identity: reviewId
  properties:
    - assignmentId: String
    - reviewerId: String
    - reviewType: ReviewType [QUALITY|COMPLIANCE|REVENUE_OPTIMIZATION]
    - reviewStatus: ReviewStatus [PENDING|APPROVED|REJECTED|MODIFIED]
    - reviewTimestamp: Instant

  value_objects:
    - ReviewFindings:
        originalDRG: String
        reviewedDRG: String
        changeReason: String
        revenueImpact: BigDecimal

    - ComplianceCheck:
        compliantWithGuidelines: boolean
        violations: List<String>
        correctiveActions: List<String>

  behaviors:
    - performQualityReview()
    - validateCompliance()
    - calculateRevenueImpact()
    - approveOrReject()
```

### Domain Events

#### 1. DRGCalculated
```json
{
  "eventType": "DRGCalculated",
  "eventId": "evt-drg-001",
  "timestamp": "2025-01-12T10:30:00Z",
  "aggregateId": "DRG-ASSIGN-001",
  "payload": {
    "assignmentId": "DRG-ASSIGN-001",
    "encounterId": "ENC-001",
    "drgCode": "470",
    "drgWeight": 1.2345,
    "reimbursementAmount": 15000.00,
    "aiConfidence": 0.92,
    "method": "AI_ML_GROUPER",
    "modelVersion": "v2.3.1"
  }
}
```

#### 2. MCCCCUpgradeDetected
```json
{
  "eventType": "MCCCCUpgradeDetected",
  "eventId": "evt-upgrade-001",
  "timestamp": "2025-01-12T10:31:00Z",
  "aggregateId": "DRG-ASSIGN-001",
  "payload": {
    "assignmentId": "DRG-ASSIGN-001",
    "currentDRG": "470",
    "upgradeDRG": "469",
    "upgradeType": "ADD_MCC",
    "reimbursementIncrease": 3500.00,
    "confidenceScore": 0.88,
    "actionRequired": "CLINICAL_DOCUMENTATION_QUERY"
  }
}
```

#### 3. LowConfidenceCodingDetected
```json
{
  "eventType": "LowConfidenceCodingDetected",
  "eventId": "evt-review-001",
  "timestamp": "2025-01-12T10:32:00Z",
  "aggregateId": "DRG-ASSIGN-001",
  "payload": {
    "assignmentId": "DRG-ASSIGN-001",
    "drgCode": "470",
    "aiConfidence": 0.65,
    "threshold": 0.70,
    "actionRequired": "MANUAL_CODER_REVIEW",
    "priority": "HIGH",
    "assignedTo": "CODER-001"
  }
}
```

### Contexto de Microsserviços
**Serviço Recomendado**: `AI-Coding-Service`
**Justificativa**:
- IA/ML requer infraestrutura especializada (GPU, modelos treinados)
- Isolamento permite evolução independente de algoritmos
- Escalabilidade horizontal para processar grandes volumes
- Facilita A/B testing de novos modelos sem impactar sistema principal

**Dependências de Domínio**:
- Clinical-Documentation-Service (dados clínicos para codificação)
- Revenue-Integrity-Service (otimização de reembolso)
- Coding-Audit-Service (validação e compliance)

---

## XIII. Metadados Técnicos

### Métricas de Complexidade
```yaml
complexity_metrics:
  cyclomatic_complexity: 14
  cognitive_complexity: 19
  lines_of_code: 175
  number_of_methods: 4
  max_nesting_level: 3

  complexity_rating: HIGH
  maintainability_index: 68
  technical_debt_ratio: 6.5%

  ml_model_complexity:
    model_type: "Gradient Boosting Classifier"
    features_count: 87
    training_samples: 50000
    accuracy: 0.96
    f1_score: 0.94
```

### Cobertura de Testes
```yaml
test_coverage:
  line_coverage: 0%
  branch_coverage: 0%
  method_coverage: 0%

  test_status: NOT_IMPLEMENTED
  priority: CRITICAL
  estimated_tests_required: 20

  suggested_test_types:
    - unit_tests: "Cálculo DRG, MCC/CC detection, confidence scoring"
    - integration_tests: "Integração com CodingService ML, validação de output"
    - ml_tests: "Validação de acurácia do modelo, detecção de drift"
    - edge_case_tests: "Baixa confiança, casos raros de DRG, múltiplos MCC/CC"
```

### Métricas de Desempenho
```yaml
performance_metrics:
  average_execution_time: "250ms"
  p95_execution_time: "400ms"
  p99_execution_time: "600ms"

  ml_inference_time: "180ms"

  performance_considerations:
    - "Inferência ML é operação mais custosa (70% do tempo total)"
    - "Batch processing recomendado para codificações retrospectivas"
    - "Cache de resultados para re-consultas de mesmo encounter"

  optimization_opportunities:
    - "Implementar GPU inference para reduzir latência em 60%"
    - "Batch prediction para múltiplos encounters simultâneos"
    - "Cache de features extraídas de documentação clínica"
    - "Quantização de modelo para reduzir tamanho e aumentar velocidade"
```

### Dependências e Integrações
```yaml
dependencies:
  internal_services:
    - service: CodingService
      purpose: "Motor ML para cálculo de DRG e otimização"
      criticality: HIGH

    - service: ClinicalDocumentationService
      purpose: "Fonte de dados clínicos para features do ML"
      criticality: HIGH

  ml_infrastructure:
    - framework: "TensorFlow/Scikit-learn"
      version: "2.x"
      purpose: "Treinamento e inferência de modelos"

    - model_registry: "MLflow"
      purpose: "Versionamento e deploy de modelos"

  external_systems:
    - system: "CMS DRG Grouper"
      integration: "REST API"
      purpose: "Validação de cálculos DRG oficiais"

  databases:
    - name: "Coding DB"
      type: "PostgreSQL"
      tables: ["drg_assignments", "coding_reviews", "alternative_drgs"]

    - name: "ML Feature Store"
      type: "Redis"
      purpose: "Cache de features extraídas para inferência rápida"

  message_queues:
    - queue: "coding.drg.calculated"
      purpose: "Publicação de DRGs calculados para billing"
    - queue: "coding.review.required"
      purpose: "Fila de codificações com baixa confiança para revisão"
```

---
