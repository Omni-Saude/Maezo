# Regras de Negócio - AnalyzeDifferenceDelegate

**Arquivo:** `AnalyzeDifferenceDelegate.java`
**Domínio:** Collection (Cobrança)
**Processo BPMN:** Payment Variance Analysis
**Versão:** 2.0.0
**Data:** Análise de Código

---

## Visão Geral

Delegate responsável por analisar diferenças (variâncias) entre valores esperados e recebidos de pagamentos, categorizando e determinando necessidade de revisão manual.

---

## Regras de Negócio Identificadas

### RN-DIF-001: Tolerância Percentual Aceitável
**Prioridade:** ALTA
**Tipo:** Configuração
**Descrição:** Variância de até 2% é considerada aceitável.
**Implementação:**
```java
// Linha 39 (constante)
private static final BigDecimal ACCEPTABLE_PERCENTAGE = new BigDecimal("2.0"); // 2% tolerance
```
**Aplicação:** Determina se variância está dentro de limites aceitáveis

---

### RN-DIF-002: Tolerância Absoluta Aceitável
**Prioridade:** ALTA
**Tipo:** Configuração
**Descrição:** Variância de até R$ 5,00 é considerada aceitável (independente do percentual).
**Implementação:**
```java
// Linha 40 (constante)
private static final BigDecimal ACCEPTABLE_ABSOLUTE = new BigDecimal("5.0"); // $5 absolute tolerance
```
**Aplicação:** Permite tolerância para valores pequenos mesmo com percentual alto

---

### RN-DIF-003: Limite de Variância Alta
**Prioridade:** ALTA
**Tipo:** Configuração
**Descrição:** Variância acima de 10% é considerada alta e requer escalação.
**Implementação:**
```java
// Linha 41 (constante)
private static final BigDecimal HIGH_VARIANCE_THRESHOLD = new BigDecimal("10.0"); // 10% requires escalation
```
**Aplicação:** Determina necessidade de revisão manual

---

### RN-DIF-004: Cálculo de Variância Monetária
**Prioridade:** ALTA
**Tipo:** Cálculo
**Descrição:** Variância em valor absoluto = Valor Recebido - Valor Esperado.
**Implementação:**
```java
// Linha 64
BigDecimal varianceAmount = receivedAmount.subtract(expectedAmount);
```
**Saída:**
- Positivo = Pagamento a maior (overpayment)
- Negativo = Pagamento a menor (underpayment)
- Zero = Valor exato

---

### RN-DIF-005: Cálculo de Variância Percentual
**Prioridade:** ALTA
**Tipo:** Cálculo
**Descrição:** Variância percentual = (Variância / Valor Esperado) × 100.
**Implementação:**
```java
// Linha 66-72
BigDecimal variancePercentage = BigDecimal.ZERO;

if (expectedAmount.compareTo(BigDecimal.ZERO) != 0) {
    variancePercentage = varianceAmount
        .divide(expectedAmount, 4, RoundingMode.HALF_UP)
        .multiply(new BigDecimal("100"))
        .setScale(2, RoundingMode.HALF_UP);
}
```
**Precisão:** 2 casas decimais com arredondamento HALF_UP
**Proteção:** Divisão por zero retorna 0%

---

### RN-DIF-006: Aceitabilidade OR Lógico
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Variância é aceitável se estiver dentro do limite percentual OU do limite absoluto.
**Implementação:**
```java
// Linha 104-113
private boolean isVarianceAcceptable(BigDecimal varianceAmount, BigDecimal variancePercentage,
                                     BigDecimal expectedAmount) {
    BigDecimal absVarianceAmount = varianceAmount.abs();
    BigDecimal absVariancePercentage = variancePercentage.abs();

    // Acceptable if within percentage threshold OR absolute threshold
    boolean withinPercentage = absVariancePercentage.compareTo(ACCEPTABLE_PERCENTAGE) <= 0;
    boolean withinAbsolute = absVarianceAmount.compareTo(ACCEPTABLE_ABSOLUTE) <= 0;

    return withinPercentage || withinAbsolute;
}
```
**Condição:** (|variância%| <= 2%) OR (|variância R$| <= 5,00)
**Saída:** `varianceAcceptable` (Boolean)

---

### RN-DIF-007: Categorização - Casamento Exato
**Prioridade:** BAIXA
**Tipo:** Classificação
**Descrição:** Variância zero é categorizada como "exact_match".
**Implementação:**
```java
// Linha 122-123
if (varianceAmount.compareTo(BigDecimal.ZERO) == 0) {
    return "exact_match";
```
**Saída:** `varianceReason` = "exact_match"

---

### RN-DIF-008: Categorização - Pagamento a Maior (Overpayment)
**Prioridade:** MÉDIA
**Tipo:** Classificação
**Descrição:** Pagamentos a maior são categorizados em 3 níveis de severidade.
**Implementação:**
```java
// Linha 124-132
} else if (varianceAmount.compareTo(BigDecimal.ZERO) > 0) {
    // Overpayment
    if (absVariancePercentage.compareTo(ACCEPTABLE_PERCENTAGE) <= 0) {
        return "overpayment_minor";
    } else if (absVariancePercentage.compareTo(HIGH_VARIANCE_THRESHOLD) < 0) {
        return "overpayment_moderate";
    } else {
        return "overpayment_significant";
    }
```
**Categorias:**
- `overpayment_minor`: <= 2%
- `overpayment_moderate`: 2,01% - 9,99%
- `overpayment_significant`: >= 10%

---

### RN-DIF-009: Categorização - Pagamento a Menor (Underpayment)
**Prioridade:** ALTA
**Tipo:** Classificação
**Descrição:** Pagamentos a menor são categorizados em 3 níveis de severidade.
**Implementação:**
```java
// Linha 133-142
} else {
    // Underpayment
    if (absVariancePercentage.compareTo(ACCEPTABLE_PERCENTAGE) <= 0) {
        return "underpayment_minor";
    } else if (absVariancePercentage.compareTo(HIGH_VARIANCE_THRESHOLD) < 0) {
        return "underpayment_moderate";
    } else {
        return "underpayment_significant";
    }
}
```
**Categorias:**
- `underpayment_minor`: <= 2%
- `underpayment_moderate`: 2,01% - 9,99%
- `underpayment_significant`: >= 10%

---

### RN-DIF-010: Revisão Manual por Variância Alta
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Variâncias >= 10% sempre requerem revisão manual.
**Implementação:**
```java
// Linha 148-157
private boolean requiresManualReview(BigDecimal varianceAmount, BigDecimal variancePercentage) {
    BigDecimal absVariancePercentage = variancePercentage.abs();

    // Require review if variance exceeds high threshold
    // or if it's a significant underpayment
    boolean highVariance = absVariancePercentage.compareTo(HIGH_VARIANCE_THRESHOLD) >= 0;
    boolean significantUnderpayment = varianceAmount.compareTo(BigDecimal.ZERO) < 0
        && absVariancePercentage.compareTo(new BigDecimal("5.0")) > 0;

    return highVariance || significantUnderpayment;
}
```
**Condição 1:** |variância%| >= 10%
**Condição 2:** Underpayment > 5%
**Saída:** `requiresReview` = true se qualquer condição verdadeira

---

## Matriz de Categorização

| Variância | % vs Esperado | Categoria | Aceitável? | Requer Revisão? |
|-----------|---------------|-----------|------------|-----------------|
| R$ 0,00 | 0% | exact_match | Sim | Não |
| > R$ 0,00 | <= 2% | overpayment_minor | Sim | Não |
| > R$ 0,00 | 2,01% - 9,99% | overpayment_moderate | Não | Não |
| > R$ 0,00 | >= 10% | overpayment_significant | Não | Sim |
| < R$ 0,00 | <= 2% | underpayment_minor | Sim | Não |
| < R$ 0,00 | 2,01% - 4,99% | underpayment_moderate | Não | Não |
| < R$ 0,00 | 5% - 9,99% | underpayment_moderate | Não | Sim* |
| < R$ 0,00 | >= 10% | underpayment_significant | Não | Sim |

*Underpayments > 5% requerem revisão mesmo sendo < 10%

---

## Limiares de Decisão

| Limite | Valor | Aplicação |
|--------|-------|-----------|
| `ACCEPTABLE_PERCENTAGE` | 2% | Variância aceitável |
| `ACCEPTABLE_ABSOLUTE` | R$ 5,00 | Variância absoluta aceitável |
| `HIGH_VARIANCE_THRESHOLD` | 10% | Requer escalação |
| Underpayment Review | 5% | Revisão para underpayment |

---

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `expectedAmount` | BigDecimal | Sim | Valor esperado do pagamento |
| `receivedAmount` | BigDecimal | Sim | Valor efetivamente recebido |
| `invoiceId` | String | Não | ID da fatura relacionada |

---

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `varianceAmount` | BigDecimal | Diferença em reais (recebido - esperado) |
| `variancePercentage` | BigDecimal | Diferença percentual (2 casas decimais) |
| `varianceAcceptable` | Boolean | Se variância está dentro dos limites |
| `varianceReason` | String | Categoria da variância |
| `requiresReview` | Boolean | Se requer revisão manual |
| `varianceAnalysisRecord` | ObjectValue | Registro completo da análise |

---

## Categorias de Variância (varianceReason)

| Categoria | Descrição |
|-----------|-----------|
| `exact_match` | Pagamento exato (variância = 0) |
| `overpayment_minor` | Pagamento a maior <= 2% |
| `overpayment_moderate` | Pagamento a maior 2,01% - 9,99% |
| `overpayment_significant` | Pagamento a maior >= 10% |
| `underpayment_minor` | Pagamento a menor <= 2% |
| `underpayment_moderate` | Pagamento a menor 2,01% - 9,99% |
| `underpayment_significant` | Pagamento a menor >= 10% |

---

## Estrutura de `varianceAnalysisRecord`

```json
{
  "analysis_id": "uuid",
  "expected_amount": 1000.00,
  "received_amount": 950.00,
  "variance_amount": -50.00,
  "variance_percentage": -5.00,
  "variance_reason": "underpayment_moderate",
  "variance_acceptable": false,
  "requires_review": true,
  "analyzed_at": "2026-01-12T10:45:00",
  "analyzed_by": "variance_analysis_system"
}
```

---

## Fluxo de Decisão

```
1. Calcular varianceAmount = received - expected
2. Calcular variancePercentage = (variance / expected) × 100

3. Determinar aceitabilidade:
   - SE |variance%| <= 2% OU |variance R$| <= 5 → Aceitável
   - SENÃO → Não aceitável

4. Categorizar variância:
   - SE variance = 0 → exact_match
   - SE variance > 0:
     - SE |variance%| <= 2% → overpayment_minor
     - SE 2% < |variance%| < 10% → overpayment_moderate
     - SE |variance%| >= 10% → overpayment_significant
   - SE variance < 0:
     - SE |variance%| <= 2% → underpayment_minor
     - SE 2% < |variance%| < 10% → underpayment_moderate
     - SE |variance%| >= 10% → underpayment_significant

5. Determinar necessidade de revisão:
   - SE |variance%| >= 10% → Revisão obrigatória
   - SE variance < 0 E |variance%| > 5% → Revisão obrigatória
   - SENÃO → Sem revisão
```

---

## Dependências

- **ADR:** ADR-003 BPMN Implementation Standards
- **Processo:** Payment Variance Analysis Process

---

## Notas de Implementação

1. **Validação de Entrada:** Se valores ausentes, define `varianceAcceptable` = false e `requiresReview` = true.
2. **Proteção contra Divisão por Zero:** Retorna percentual = 0% se `expectedAmount` = 0.
3. **Arredondamento:** Usa `RoundingMode.HALF_UP` para percentuais (2 casas decimais).
4. **Audit Trail:** Cria registro completo com timestamp e sistema responsável.
5. **Priorização:** Underpayments recebem limiar mais rigoroso (5% vs 10%) para revisão manual.

---

## XI. Conformidade Regulatória

### 11.1 Requisitos ANS
- **RN 395/2016**: Submissão eletrônica - registro de variâncias em lotes de guias TISS
- **RN 442/2018**: Qualidade assistencial - análise de glosas e diferenças de pagamento
- **RN 465/2021**: Direitos dos beneficiários - transparência em variâncias de cobertura

### 11.2 Conformidade TISS
- **TISS 4.01**: Estrutura de dados para registro de glosas e variâncias
- **Componente Financeiro**: Campos de diferenças de pagamento e justificativas

### 11.3 LGPD
- **Art. 11 LGPD**: Processamento de dados de saúde - valores de pagamentos e variâncias
- **Art. 48 LGPD**: Comunicação de incidentes de segurança em caso de variâncias suspeitas
- **Retenção**: 5 anos para registros de variância (auditoria financeira)

### 11.4 SOX Compliance (Sarbanes-Oxley)
- **Seção 404**: Controles internos sobre relatórios financeiros
- **Documentação**: Registro obrigatório de variâncias > R$ 1.000,00
- **Revisão manual**: Obrigatória para variâncias > 10% (high variance threshold)

### 11.5 Trilha de Auditoria
- **Registro obrigatório**: Todas as análises de variância com timestamp
- **Campos auditáveis**: expected_amount, received_amount, variance_percentage, category, requires_review
- **Rastreabilidade**: UUID único para cada análise
- **Período de retenção**: 7 anos (requisitos fiscais e SOX)

---

## XII. Notas de Migração - Camunda 7 para Camunda 8

### 12.1 Camunda 8 - Alternativa Recomendada
- **Padrão**: External Task Worker com Zeebe
- **Implementação**: Job Worker para análise de variâncias assíncrona
- **Vantagens**: Escalabilidade para grandes volumes, retry automático

### 12.2 Nível de Complexidade
- **Complexidade de Migração**: BAIXA (2-3 dias)
- **Justificativa**: Lógica stateless, poucos side-effects, cálculos determinísticos

### 12.3 Breaking Changes
- **JavaDelegate → Job Worker**: Refatoração para padrão async
- **Variáveis**: Migração para Zeebe variable model (JSON serialization)
- **Error Handling**: BpmnError → Zeebe incident handling com retry policies
- **Transações**: Camunda 7 (ACID) → Camunda 8 (eventual consistency)

### 12.4 Considerações Técnicas
- **External Task Pattern**: Fila de tarefas com Zeebe para processamento paralelo
- **Idempotência**: Já implementada - facilita migração
- **Testing**: Migração de testes para Zeebe Process Test

---

## XIII. Mapeamento DDD

### 13.1 Bounded Context
- **Contexto Delimitado**: `Payment Reconciliation & Variance Analysis`
- **Linguagem Ubíqua**: Variance, overpayment, underpayment, acceptable tolerance, manual review

### 13.2 Aggregate Root
- **Aggregate**: `PaymentVariance`
- **Entidades relacionadas**:
  - `Payment` (pagamento recebido)
  - `Invoice` (fatura esperada)
  - `VarianceThreshold` (limites de aceitabilidade)

### 13.3 Domain Events
- **VarianceDetected**: Variância identificada (over/under payment)
- **ManualReviewRequired**: Variância acima de limites requer intervenção
- **VarianceAccepted**: Variância dentro de tolerâncias aceitáveis

### 13.4 Value Objects
- `Money` (valor monetário com precisão decimal)
- `Percentage` (variância percentual)
- `VarianceCategory` (enum: exact_match, overpayment_minor, underpayment_significant)

### 13.5 Candidato a Microserviço
- **Serviço**: `variance-analysis-service`
- **Responsabilidades**: Análise de diferenças, categorização, determinação de revisão manual
- **Integrações**: Payment Service, Invoice Service, Manual Review Queue

---

## XIV. Metadados Técnicos

### 14.1 Características
- **Tipo**: Service Delegate (Camunda 7 JavaDelegate)
- **Execução**: Síncrona (blocking)
- **Idempotência**: Habilitada (requer IdempotencyService)
- **Transacional**: Sim (requer gerenciamento de transação)

### 14.2 Métricas de Qualidade
- **Complexidade Ciclomática**: MÉDIA (7 categorias + 2 validações de revisão)
- **Cobertura de Testes Recomendada**: 95% (lógica crítica com múltiplos branches)
- **Tempo de Execução Esperado**: < 500ms (cálculos simples em memória)

### 14.3 Impacto de Performance
- **I/O**: LOW (apenas leitura de variáveis de processo)
- **CPU**: LOW (cálculos aritméticos simples)
- **Memória**: LOW (poucos objetos em memória)

### 14.4 Dependências de Runtime
- Spring Framework (DI)
- Camunda BPM Engine 7.x
- IdempotencyService (custom)
- SLF4J (logging)

---

## X. Conformidade Regulatória

```yaml
regulatory_compliance:
  tiss_standards:
    - "TISS 4.01 - Estrutura de dados para registro de glosas e variâncias de pagamento"
    - "TISS 4.01 - Componente Financeiro: campos de diferenças e justificativas"
  ans_requirements:
    - "RN 395/2016 - Submissão eletrônica: registro de variâncias em lotes TISS"
    - "RN 442/2018 - Qualidade assistencial: análise de glosas e diferenças"
    - "RN 465/2021 - Direitos dos beneficiários: transparência em variâncias"
  lgpd_considerations:
    - "Art. 11 - Processamento de dados de saúde (valores de pagamentos vinculados a pacientes)"
    - "Art. 48 - Comunicação de incidentes em caso de variâncias suspeitas de fraude"
  sox_compliance:
    - "Seção 404 - Controles internos sobre relatórios financeiros"
    - "Documentação obrigatória de variâncias > R$ 1.000,00"
    - "Revisão manual obrigatória para variâncias > 10%"
  audit_trail:
    - "Retention: 7 anos (requisitos fiscais e SOX)"
    - "Logging: expectedAmount, receivedAmount, variancePercentage, category, requiresReview, timestamp"
    - "Rastreabilidade: UUID único para cada análise de variância"
```

---

## XI. Notas de Migração

```yaml
migration_notes:
  complexity: "BAIXA"
  estimated_effort: "2-3 dias"
  camunda_8_changes:
    - "JavaDelegate → Job Worker assíncrono com Zeebe"
    - "Variáveis: Migrar para JSON serialization (expectedAmount, receivedAmount)"
    - "Error Handling: BpmnError → Zeebe incident handling com retry automático"
    - "Idempotência: Já implementada - facilita migração"
  breaking_changes:
    - "Execução síncrona → assíncrona (adicionar timeout 30s)"
    - "Variáveis de processo → Zeebe variables (JSON)"
    - "Transações ACID → eventual consistency"
  migration_strategy:
    phases:
      - "Pré-Migração: Validar cálculos com casos de teste edge (R$ 0, R$ 5, limites)"
      - "Migração: Converter para job worker, testar retry logic"
      - "Validação: Comparar resultados entre Camunda 7 e 8 com mesmos inputs"
  critical_dependencies:
    - "Nenhuma (lógica stateless, sem side effects)"
  dmn_candidate: "Não"
  dmn_rationale: "Cálculos determinísticos simples, melhor manter em código para performance"
```

---

## XII. Mapeamento DDD

```yaml
domain_mapping:
  bounded_context: "Payment Reconciliation & Variance Analysis"
  aggregate_root: "PaymentVariance"
  aggregates:
    - identity: "PaymentVariance"
      properties:
        - "analysisId (UUID)"
        - "expectedAmount (BigDecimal)"
        - "receivedAmount (BigDecimal)"
        - "varianceAmount (BigDecimal)"
        - "variancePercentage (BigDecimal)"
        - "varianceReason (Enum)"
        - "varianceAcceptable (Boolean)"
        - "requiresReview (Boolean)"
        - "analyzedAt"
      behaviors:
        - "calculateVariance() - RN-DIF-004, RN-DIF-005"
        - "categorize() - RN-DIF-007 a RN-DIF-009"
        - "determineReviewNeed() - RN-DIF-010"
        - "isAcceptable() - RN-DIF-006"
  value_objects:
    - "Money (BigDecimal com precisão decimal)"
    - "Percentage (variância percentual, 2 casas decimais)"
    - "VarianceCategory (enum: exact_match, overpayment_minor, underpayment_significant, etc.)"
  domain_events:
    - name: "VarianceDetected"
      payload:
        - "analysisId"
        - "invoiceId"
        - "varianceAmount"
        - "variancePercentage"
        - "category"
    - name: "ManualReviewRequired"
      payload:
        - "analysisId"
        - "varianceAmount"
        - "variancePercentage"
        - "reason"
    - name: "VarianceAccepted"
      payload:
        - "analysisId"
        - "category (minor overpayment/underpayment)"
  microservice_candidate:
    viable: true
    service_name: "variance-analysis-service"
    bounded_context: "Payment Reconciliation"
    api_style: "Event-Driven (async processing)"
    upstream_dependencies:
      - "payment-service (receivedAmount)"
      - "invoice-service (expectedAmount)"
    downstream_consumers:
      - "manual-review-queue (consumes ManualReviewRequired)"
      - "accounting-service (consumes VarianceAccepted)"
```

---

## XIII. Metadados Técnicos

```yaml
technical_metadata:
  complexity:
    cyclomatic: 7
    cognitive: 10
    loc: 160
    decision_points: 9
    rationale: "7 categorias de variância + 2 validações de revisão manual"
  test_coverage:
    recommended: "95%"
    critical_paths:
      - "Cálculo variância com expectedAmount = 0 (proteção divisão por zero)"
      - "Boundary tests: R$ 5,00 / 2% / 10%"
      - "Categorização de 7 tipos de variância"
      - "Revisão manual: >= 10% OR (underpayment > 5%)"
    edge_cases:
      - "varianceAmount = R$ 0,00 (exact_match)"
      - "varianceAmount = R$ 5,00 (boundary aceitável absoluto)"
      - "variancePercentage = 2,00% (boundary aceitável percentual)"
      - "underpayment = 5,01% (trigger manual review)"
  performance:
    target_p50: "20ms"
    target_p95: "80ms"
    target_p99: "150ms"
    bottlenecks:
      - "Nenhum (cálculos em memória, sem I/O)"
    optimization_recommendations:
      - "Nenhuma necessária (performance excelente)"
  scalability:
    expected_tps: "500-1000"
    limited_by: "CPU para cálculos (muito baixo)"
    horizontal_scaling: true
  monitoring:
    key_metrics:
      - "variance_analysis_count"
      - "manual_review_triggered_count"
      - "overpayment_significant_count"
      - "underpayment_significant_count"
    alerts:
      - "Manual review queue > 100 items"
      - "Significant underpayments > 20 in 1 hour"
```

---

**Gerado automaticamente em:** 2026-01-12
**Fonte:** Análise de código Camunda 7
