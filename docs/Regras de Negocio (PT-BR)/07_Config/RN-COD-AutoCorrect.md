# Regras de Negócio: AutoCorrectDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/coding/AutoCorrectDelegate.java`
> **Categoria:** CODING (Codificação Médica - Correção Automática)
> **Total de Regras:** 7

## 📋 Sumário Executivo

O delegate AutoCorrectDelegate utiliza machine learning para corrigir automaticamente erros comuns de codificação identificados durante a auditoria. Esta automação reduz significativamente o trabalho manual de codificadores e acelera o ciclo de submissão de contas, mantendo alto padrão de qualidade e conformidade.

O motor de ML foi treinado com milhares de correções históricas e pode corrigir automaticamente erros de formato, melhorar especificidade de códigos (.9 não específicos), adicionar modificadores ausentes e sugerir alternativas compatíveis. O sistema calcula scores de confiança para cada correção e determina quando revisão humana é necessária.

## 📜 Catálogo de Regras

### RN-COD-COR-001: Correção Automática com ML

**Descrição:** Aplica motor de machine learning para corrigir automaticamente violações de codificação identificadas pela auditoria.

**Lógica:**
```
ENTRADA:
  - violations: Lista de violações da auditoria
  - autoApprove: Flag de aprovação automática

PROCESSAR via CodingService.autoCorrectCodes():
  - Analisar tipo de cada violação
  - Aplicar modelo ML treinado para correção
  - Gerar mapeamento: código original -> código corrigido
  - Calcular confidence score para cada correção

TIPOS DE CORREÇÃO:
  1. FORMAT_ERROR: Correção de formato
  2. UNSPECIFIED_CODE: .9 -> código específico
  3. MISSING_MODIFIER: Adicionar modificador
  4. INCOMPATIBLE_CODE: Sugerir alternativa compatível

RETORNAR Map<String, String>: códigos corrigidos
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| claimId | String | Obrigatório | "CLM-2025-001" |
| violations | List&lt;Map&gt; | Obrigatório, da auditoria | [{type:"FORMAT_ERROR", code:"J189"}] |
| autoApprove | Boolean | Opcional, padrão false | true |
| correctedCodes | Map&lt;String,String&gt; | Saída: original->corrigido | {"J189":"J18.9"} |

**Rastreabilidade:**
- Arquivo: AutoCorrectDelegate.java
- Método: executeBusinessLogic
- Linhas: 68-69

---

### RN-COD-COR-002: Determinação de Necessidade de Revisão

**Descrição:** Avalia se as correções automáticas requerem validação por codificador humano baseado em complexidade e quantidade.

**Lógica:**
```
REQUER REVISÃO MANUAL SE:

1. autoApprove = false
   SEMPRE requer revisão

2. Número de correções > 5
   Muitas correções indicam problema sistêmico

3. Violações críticas não corrigidas
   SE existe violação com:
     - severity = "CRITICAL"
     - código NÃO está em correctedCodes
   ENTÃO requer revisão

4. Confiança baixa
   SE alguma correção tem confidence < 0.8
   ENTÃO requer revisão

SENÃO: Aprovação automática permitida
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| requiresReview | Boolean | Escopo: Process | true |
| autoApprove | Boolean | Input | false |
| correctionCount | Integer | Calculado | 3 |
| criticalUncorrected | Long | Calculado | 0 |

**Rastreabilidade:**
- Arquivo: AutoCorrectDelegate.java
- Método: determineReviewRequirement
- Linhas: 103-128

---

### RN-COD-COR-003: Cálculo de Métricas de Correção

**Descrição:** Calcula métricas de qualidade das correções para tracking de performance do motor de ML.

**Lógica:**
```
MÉTRICAS CALCULADAS:

1. totalViolations: Total de violações recebidas

2. correctedCount: Número de correções aplicadas

3. correctionRate: Taxa de correção automática
   FÓRMULA: correctedCount / totalViolations
   (0.0 se sem violações)

4. correctionsByType: Contagem por tipo
   PARA CADA violação corrigida:
     - Incrementar contador do tipo
   TIPOS: FORMAT_ERROR, MEDICAL_NECESSITY, etc.

ARMAZENAR em correctionMetrics para analytics
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| correctionMetrics | Map&lt;String,Object&gt; | Escopo: Process | {...} |
| totalViolations | Integer | Métrica | 8 |
| correctedCount | Integer | Métrica | 6 |
| correctionRate | Double | 0.0-1.0 | 0.75 |
| correctionsByType | Map&lt;String,Integer&gt; | Por tipo | {"FORMAT_ERROR":4} |

**Fórmula:**
```
correctionRate = correctedCount / totalViolations

Exemplo:
  6 correções / 8 violações = 0.75 (75% de taxa de correção)
```

**Rastreabilidade:**
- Arquivo: AutoCorrectDelegate.java
- Método: calculateCorrectionMetrics
- Linhas: 137-157

---

### RN-COD-COR-004: Armazenamento de Correções Realizadas

**Descrição:** Persiste todas as correções aplicadas em formato rastreável para auditoria e aprendizado contínuo do ML.

**Lógica:**
```
ARMAZENAR em escopo PROCESS:
  - correctionsMade: Quantidade total
  - correctedCodes: Map original -> corrigido
  - requiresReview: Flag de revisão necessária
  - correctionDate: Timestamp da correção
  - correctionMetrics: Métricas de qualidade
  - uncorrectedViolations: Violações não corrigíveis

FORMATO de correctedCodes:
  Map<String, String>:
    "J189" -> "J18.9" (correção de formato)
    "E119" -> "E11.9" (adição de ponto)
    "40101010" -> "40101010-1" (adição de dígito verificador)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| correctionsMade | Integer | Escopo: Process | 6 |
| correctedCodes | Map&lt;String,String&gt; | Escopo: Process | {"J189":"J18.9"} |
| requiresReview | Boolean | Escopo: Process | false |
| correctionDate | LocalDateTime | Escopo: Process | 2025-01-11T11:15:00 |
| correctionMetrics | Map | Escopo: Process | {...} |
| uncorrectedViolations | Integer | Escopo: Process | 2 |

**Rastreabilidade:**
- Arquivo: AutoCorrectDelegate.java
- Método: executeBusinessLogic
- Linhas: 78-83

---

### RN-COD-COR-005: Threshold de Múltiplas Correções

**Descrição:** Define limite de 5 correções automáticas por conta; acima disso, sempre requer revisão humana para evitar propagação de erros sistemáticos.

**Lógica:**
```
SE correctionCount > 5
ENTÃO:
  - requiresReview = true
  - Motivo: Possível problema sistemático de codificação
  - Sugestão: Revisar processo de codificação inicial
  - Trigger: Notificação para supervisor de codificação

THRESHOLD_VALUE: 5 (configurado)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| CORRECTION_THRESHOLD | Integer | Fixo: 5 | 5 |
| correctionCount | Integer | Calculado | 6 |
| requiresReview | Boolean | Derivado | true |

**Rastreabilidade:**
- Arquivo: AutoCorrectDelegate.java
- Método: determineReviewRequirement
- Linhas: 112-114

---

### RN-COD-COR-006: Logging de Revisão Manual

**Descrição:** Registra logs específicos para contas que requerem revisão manual após correção automática, priorizando casos com muitas correções.

**Lógica:**
```
SE requiresReview = true E correctionsMade > 10
ENTÃO emitir log WARNING:
  - "MANUAL REVIEW REQUIRED"
  - Incluir claimId
  - Incluir correctionsMade (quantidade)
  - Incluir uncorrectedViolations (pendentes)
  - Trigger para workflow de revisão manual
  - Prioridade: ALTA (muitas correções)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| requiresReview | Boolean | Trigger de log | true |
| correctionsMade | Integer | > 10 para warning | 12 |
| uncorrectedViolations | Integer | Incluído no log | 3 |
| claimId | String | ID da conta | "CLM-2025-001" |

**Rastreabilidade:**
- Arquivo: AutoCorrectDelegate.java
- Método: executeBusinessLogic
- Linhas: 89-92

---

### RN-COD-COR-007: Tratamento de Violações Críticas Não Corrigidas

**Descrição:** Identifica violações de severidade crítica que não puderam ser corrigidas automaticamente e requer intervenção imediata.

**Lógica:**
```
PARA CADA violação em violations:
  - SE violation.severity = "CRITICAL"
    E violation.code NÃO está em correctedCodes
    ENTÃO incrementar criticalUncorrected

SE criticalUncorrected > 0
ENTÃO:
  - requiresReview = true (obrigatório)
  - Prioridade: CRÍTICA
  - Bloqueio: Submissão suspensa até correção manual
  - Notificação: Codificador certificado + Supervisor

CRÍTICAS não corrigíveis incluem:
  - Incompatibilidades complexas de códigos
  - Violações de necessidade médica
  - Códigos não existentes na tabela
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| criticalUncorrected | Long | Calculado via stream | 1 |
| severity | String | "CRITICAL" para contagem | "CRITICAL" |
| requiresReview | Boolean | Forçado true se > 0 | true |

**Rastreabilidade:**
- Arquivo: AutoCorrectDelegate.java
- Método: determineReviewRequirement
- Linhas: 117-124

---

## 📊 Métricas e Monitoramento

**Operação:** auto_correct
**Idempotência:** Sim (via BaseDelegate)
**Escopo de Variáveis:** PROCESS (compartilhadas com audit e billing)
**Motor de ML:** CodingService.autoCorrectCodes()

## 🔗 Integrações

- **CodingService:** Motor de ML para correção automática
- **AuditRulesDelegate:** Recebe violations para correção
- **ValidateCodesDelegate:** Re-validação após correção
- **BPMN Process:** Sinaliza necessidade de revisão manual

## 📝 Observações Técnicas

1. **Threshold de Correções:** Máximo 5 correções automáticas sem revisão
2. **Confidence Score:** ML calcula confiança para cada correção
3. **Auto-Approve:** Flag permite ou bloqueia aplicação automática
4. **Tipos de Correção:**
   - FORMAT_ERROR: Ajuste de formato (pontos, dígitos)
   - UNSPECIFIED_CODE: Melhoria de especificidade (.9 -> código específico)
   - MISSING_MODIFIER: Adição de modificadores obrigatórios
   - INCOMPATIBLE_CODE: Substituição por código compatível
5. **Métricas de Qualidade:**
   - correctionRate: Taxa de sucesso de correção
   - correctionsByType: Distribuição por tipo de erro
   - uncorrectedViolations: Erros não corrigíveis
6. **Aprendizado Contínuo:** Todas as correções alimentam re-treinamento do ML
7. **Revisão Obrigatória:** Violações críticas não corrigidas sempre requerem codificador humano
8. **Rastreabilidade:** Timestamp e mapeamento completo de todas as correções

---

## X. Conformidade Regulatória

### Normativas ANS
- **RN 305/2012:** Diretrizes para codificação de procedimentos (Arts. 15-17)
- **RN 443/2019:** Padronização TISS para intercâmbio de informações (Anexo II)
- **RN 465/2021:** Atualização de tabelas de terminologia médica

### Padrão TISS (Versão 4.02.02)
- **Componente:** Guia de Serviço Profissional / SADT
- **Campo 37:** Tabela de código do procedimento
- **Campo 38:** Código do procedimento (TUSS, SIMPRO, CBHPM)
- **Validação:** Formato e especificidade de códigos

### ICD-10-CM (CMS Guidelines)
- **Chapter-Specific Coding:** Regras por capítulo (00-99)
- **7th Character Extensions:** Lateralidade e encontro
- **Unspecified Codes (.9):** Minimização conforme Coding Clinic

### LGPD (Lei 13.709/2018)
- **Art. 6º, VI:** Qualidade dos dados - exatidão de códigos
- **Art. 18, III:** Correção de dados incompletos ou inexatos
- **Art. 37:** Responsabilidade de agentes por dados de saúde

### SOX (Sarbanes-Oxley)
- **Section 302:** Controles internos para precisão de reembolsos
- **Section 404:** Auditoria de processos de codificação
- **ITGC:** Rastreabilidade de correções automáticas

### CMS-1500 Compliance
- **Box 21:** ICD Indicator e especificidade de diagnósticos
- **Modifier Usage:** Aplicação correta de modificadores (-50, -LT, -RT)

---

## XI. Notas de Migração

### Complexidade de Migração
**Rating:** 🟡 MÉDIO-ALTO (7/10)

**Justificativa:**
- Machine Learning integrado requer pipeline de dados
- Validação cruzada CPT-ICD-10 complexa
- Threshold adaptativo e confidence scoring

### Mudanças Incompatíveis (Breaking Changes)
1. **ML Dependency:** Requer TensorFlow/PyTorch para modelo de correção
2. **Tabelas de Referência:** Necessita TUSS, CBHPM, CID-10 atualizadas
3. **Confidence Threshold:** Novas variáveis de processo para scoring
4. **Logging Detalhado:** Campos adicionais para rastreabilidade

### Migração para DMN
**Candidato:** ⚠️ PARCIAL

```yaml
dmn_migration:
  candidate_decisions:
    - decision_id: "auto-correct-threshold"
      decision_name: "Limite de Correções Automáticas"
      inputs:
        - violationCount
        - confidenceScore
        - criticality
      outputs:
        - requiresReview
        - autoApprove

    - decision_id: "correction-type-strategy"
      decision_name: "Estratégia por Tipo de Erro"
      inputs:
        - violationType
        - codeFormat
        - contextData
      outputs:
        - correctionType
        - replacementCode

  non_migratable:
    - ml_confidence_calculation  # Requer ML model inference
    - code_similarity_matching   # Algoritmos complexos
    - learning_feedback_loop     # Integração com pipeline ML
```

### Fases de Implementação
**Fase 1 - Foundation (Sprint 7):**
- Implementar validação de formato básica
- Setup tabelas de referência (TUSS, CID-10)
- Logging e rastreabilidade

**Fase 2 - ML Integration (Sprint 8):**
- Integrar modelo ML para confidence scoring
- Pipeline de correção automática
- Threshold adaptativo

**Fase 3 - Production Hardening (Sprint 9):**
- Monitoramento de taxa de sucesso
- Ajuste fino de thresholds
- Feedback loop para re-treinamento

### Dependências Críticas
```yaml
dependencies:
  services:
    - MLModelService          # Inference de correções
    - CodeMappingService      # TUSS/CBHPM/CID-10
    - ValidationService       # Re-validação pós-correção

  databases:
    - code_reference_tables   # TUSS, CBHPM, ICD-10
    - correction_history      # Auditoria de correções
    - ml_training_data        # Feedback loop

  external_apis:
    - cms_icd10_api          # Validação oficial CMS
    - aans_tuss_updates      # Atualizações ANS
```

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Contexto:** Medical Coding & Billing Compliance

**Subdomínio:** Automatic Code Correction (Core Domain)

**Responsabilidades:**
- Detecção e correção automática de erros de codificação
- Cálculo de confiança via ML para sugestões
- Rastreabilidade de correções para auditoria

### Aggregates e Entidades

```yaml
aggregate: CodeCorrection
  root_entity: CodeCorrection
    properties:
      - correctionId: UUID
      - originalCode: String
      - suggestedCode: String
      - violationType: ViolationType
      - confidenceScore: Float (0.0-1.0)
      - autoApproved: Boolean
      - correctionTimestamp: Instant
      - correctedBy: String (SYSTEM/USER)

  value_objects:
    - CorrectionMetadata:
        - mlModelVersion: String
        - thresholdApplied: Float
        - reviewRequired: Boolean

    - ValidationContext:
        - patientAge: Integer
        - patientGender: Gender
        - serviceDate: LocalDate
        - medicalNecessity: Boolean

  entities:
    - CorrectionHistory:
        - historyId: UUID
        - correctionId: UUID (FK)
        - action: CorrectionAction
        - performedBy: String
        - timestamp: Instant
```

### Domain Events

```json
{
  "domain_events": [
    {
      "event": "CodeAutoCorrected",
      "triggers": ["Correção aplicada automaticamente"],
      "payload": {
        "correctionId": "uuid",
        "originalCode": "string",
        "correctedCode": "string",
        "confidenceScore": "float",
        "violationType": "enum"
      },
      "subscribers": [
        "BillingService",
        "AuditService",
        "MLTrainingPipeline"
      ]
    },
    {
      "event": "ManualReviewRequired",
      "triggers": ["Confidence abaixo do threshold"],
      "payload": {
        "correctionId": "uuid",
        "violationDetails": "object",
        "suggestedCorrection": "string",
        "confidenceScore": "float"
      },
      "subscribers": [
        "CodingTeamQueue",
        "NotificationService"
      ]
    },
    {
      "event": "CorrectionRejected",
      "triggers": ["Validação falhou após correção"],
      "payload": {
        "correctionId": "uuid",
        "rejectionReason": "string",
        "fallbackAction": "enum"
      },
      "subscribers": [
        "ErrorHandlingService",
        "MLFeedbackService"
      ]
    }
  ]
}
```

### Invariantes do Domínio
1. **Confidence Threshold:** Score ≥ 0.80 para auto-apply
2. **Max Auto-Corrections:** ≤ 5 correções sem revisão humana
3. **Critical Violations:** Sempre requerem revisão manual
4. **Immutable History:** Histórico de correções é append-only

### Viabilidade para Microserviço
**Candidato:** ✅ SIM

**Justificativa:**
- Responsabilidade bem definida: correção de códigos
- Comunicação assíncrona via eventos (CodeAutoCorrected)
- Estado isolado (CorrectionHistory)
- Pode escalar independentemente (ML inference pesado)

**Integração:**
```yaml
microservice: code-correction-service
  api:
    - POST /corrections/auto-correct
    - GET /corrections/{id}/history
    - POST /corrections/{id}/approve

  events_published:
    - CodeAutoCorrected
    - ManualReviewRequired

  events_subscribed:
    - CodeValidationFailed (from ValidationService)
    - MLModelUpdated (from MLPipeline)
```

---

## XIII. Metadados Técnicos

### Complexidade e Esforço

```yaml
complexity_metrics:
  cyclomatic_complexity: 15  # Médio-Alto
  cognitive_complexity: 22   # Alto (ML + validações)
  lines_of_code: ~450

  time_estimates:
    implementation: 5 dias
    testing: 3 dias
    ml_integration: 4 dias
    documentation: 1 dia
    total: 13 dias (~2.5 sprints)
```

### Cobertura de Testes

```yaml
test_coverage_targets:
  unit_tests: 85%
  integration_tests: 75%

  critical_test_scenarios:
    - format_error_correction
    - unspecified_code_upgrade
    - modifier_addition
    - confidence_threshold_boundary
    - max_corrections_limit
    - manual_review_trigger
    - validation_after_correction
    - ml_model_fallback
```

### Performance e SLA

```yaml
performance_requirements:
  auto_correction_latency: <500ms (p95)
  ml_inference_timeout: 200ms
  batch_correction_throughput: >100 códigos/seg

  availability: 99.5%

  resource_limits:
    cpu: 2 cores
    memory: 4 GB
    ml_model_size: <100 MB
```

### Dependências e Integrações

```yaml
dependencies:
  internal_services:
    - ValidateCodesDelegate (re-validação)
    - MedicalCodingService (tabelas de referência)
    - AuditService (logging)

  external_services:
    - MLModelService (TensorFlow/PyTorch)
    - CMS ICD-10 API (validação oficial)
    - ANS TUSS Updates (atualizações)

  databases:
    - code_corrections (PostgreSQL)
    - ml_training_data (TimescaleDB)
    - audit_log (Elasticsearch)

  message_queues:
    - correction_requests (Kafka)
    - ml_feedback (Kafka)
```

### Monitoramento e Observabilidade

```yaml
metrics:
  business:
    - correction_rate_by_type
    - auto_approval_percentage
    - manual_review_queue_size
    - ml_confidence_distribution

  technical:
    - correction_latency_p50_p95_p99
    - ml_inference_time
    - validation_failure_rate
    - error_rate_by_violation_type

  alerts:
    - correction_rate < 60% (24h window)
    - manual_review_queue > 100
    - ml_inference_timeout > 300ms (p95)
    - validation_failure_rate > 10%
```

---

**Última Atualização:** 2025-01-12
**Versão do Documento:** 2.0
**Status de Conformidade:** ✅ Completo (X-XIII)
