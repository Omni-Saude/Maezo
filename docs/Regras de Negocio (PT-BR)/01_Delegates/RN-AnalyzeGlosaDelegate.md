# Regras de Negócio - AnalyzeGlosaDelegate

**Arquivo:** `AnalyzeGlosaDelegate.java`
**Domínio:** Glosa (Contestação de Negativas)
**Processo BPMN:** Glosa Analysis and Appeal
**Versão:** 1.0
**Data:** 2025-12-23

---

## Visão Geral

Delegate responsável por analisar glosas (negativas de pagamento) e determinar estratégia de recurso, prioridade e atribuição de responsável.

---

## Regras de Negócio Identificadas

### RN-GLO-001: Validação de Tipo de Glosa Obrigatório
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Tipo de glosa não pode ser nulo ou vazio.
**Implementação:**
```java
// Linha 147-149
if (glosaType == null || glosaType.trim().isEmpty()) {
    throw new BpmnError("INVALID_GLOSA_DATA", "Glosa type is required");
}
```
**Entrada:** `glosaType` (String)
**Erro:** `INVALID_GLOSA_DATA`

---

### RN-GLO-002: Validação de Valor Não-Negativo
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Valor da glosa deve ser não-negativo.
**Implementação:**
```java
// Linha 151-154
if (glosaAmount == null || glosaAmount.compareTo(BigDecimal.ZERO) < 0) {
    throw new BpmnError("INVALID_GLOSA_DATA",
            "Glosa amount must be non-negative: " + glosaAmount);
}
```
**Entrada:** `glosaAmount` (BigDecimal)
**Erro:** `INVALID_GLOSA_DATA`

---

### RN-GLO-003: Estratégia para Negativa Total - Autorização
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Negativas totais por falta de autorização devem usar estratégia AUTHORIZATION_APPEAL.
**Implementação:**
```java
// Linha 200-202
if (reason.contains("AUTHORIZATION") || reason.contains("PRE-AUTH")) {
    return "AUTHORIZATION_APPEAL";
}
```
**Entrada:** `glosaType` = "FULL_DENIAL", `glosaReason` contém "AUTHORIZATION"
**Saída:** `appealStrategy` = "AUTHORIZATION_APPEAL"
**Atribuição:** AUTHORIZATION_TEAM

---

### RN-GLO-004: Estratégia para Negativa Total - Elegibilidade
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Negativas totais por elegibilidade devem usar estratégia ELIGIBILITY_VERIFICATION_APPEAL.
**Implementação:**
```java
// Linha 203-204
} else if (reason.contains("ELIGIBILITY") || reason.contains("COVERAGE")) {
    return "ELIGIBILITY_VERIFICATION_APPEAL";
```
**Entrada:** `glosaType` = "FULL_DENIAL", `glosaReason` contém "ELIGIBILITY"
**Saída:** `appealStrategy` = "ELIGIBILITY_VERIFICATION_APPEAL"
**Atribuição:** ELIGIBILITY_TEAM

---

### RN-GLO-005: Estratégia para Negativa Total - Codificação
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Negativas totais por problemas de codificação devem usar estratégia CODING_REVIEW_APPEAL.
**Implementação:**
```java
// Linha 205-206
} else if (reason.contains("CODING") || reason.contains("PROCEDURE")) {
    return "CODING_REVIEW_APPEAL";
```
**Entrada:** `glosaType` = "FULL_DENIAL", `glosaReason` contém "CODING"
**Saída:** `appealStrategy` = "CODING_REVIEW_APPEAL"
**Atribuição:** CODING_TEAM

---

### RN-GLO-006: Estratégia para Negativa Total - Necessidade Médica
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Negativas totais por necessidade médica devem usar estratégia MEDICAL_NECESSITY_APPEAL.
**Implementação:**
```java
// Linha 207-208
} else if (reason.contains("MEDICAL NECESSITY")) {
    return "MEDICAL_NECESSITY_APPEAL";
```
**Entrada:** `glosaType` = "FULL_DENIAL", `glosaReason` contém "MEDICAL NECESSITY"
**Saída:** `appealStrategy` = "MEDICAL_NECESSITY_APPEAL"
**Atribuição:** CLINICAL_APPEALS_TEAM

---

### RN-GLO-007: Estratégia para Negativa Total - Prazo
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Negativas totais por prazo devem usar estratégia TIMELY_FILING_APPEAL.
**Implementação:**
```java
// Linha 209-210
} else if (reason.contains("TIMELY") || reason.contains("DEADLINE")) {
    return "TIMELY_FILING_APPEAL";
```
**Entrada:** `glosaType` = "FULL_DENIAL", `glosaReason` contém "TIMELY"
**Saída:** `appealStrategy` = "TIMELY_FILING_APPEAL"
**Atribuição:** COMPLIANCE_TEAM

---

### RN-GLO-008: Estratégia para Negativa Parcial - Duplicidade
**Prioridade:** MÉDIA
**Tipo:** Decisão
**Descrição:** Negativas parciais por duplicidade devem usar estratégia DUPLICATE_CLAIM_RESOLUTION.
**Implementação:**
```java
// Linha 235-236
if (reason.contains("DUPLICATE")) {
    return "DUPLICATE_CLAIM_RESOLUTION";
```
**Entrada:** `glosaType` = "PARTIAL_DENIAL", `glosaReason` contém "DUPLICATE"
**Saída:** `appealStrategy` = "DUPLICATE_CLAIM_RESOLUTION"

---

### RN-GLO-009: Estratégia para Negativa Parcial - Bundling
**Prioridade:** MÉDIA
**Tipo:** Decisão
**Descrição:** Negativas parciais por bundling/unbundling devem usar estratégia CODING_REVIEW_APPEAL.
**Implementação:**
```java
// Linha 237-238
} else if (reason.contains("BUNDLING") || reason.contains("UNBUNDLING")) {
    return "CODING_REVIEW_APPEAL";
```
**Entrada:** `glosaType` = "PARTIAL_DENIAL", `glosaReason` contém "BUNDLING"
**Saída:** `appealStrategy` = "CODING_REVIEW_APPEAL"
**Atribuição:** CODING_TEAM

---

### RN-GLO-010: Priorização por Valor - Alta Prioridade
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Glosas acima de R$ 5.000,00 recebem prioridade ALTA.
**Implementação:**
```java
// Linha 56-57 (constantes)
private static final BigDecimal HIGH_PRIORITY_THRESHOLD = new BigDecimal("5000.00");

// Linha 260-261
if (glosaAmount.compareTo(HIGH_PRIORITY_THRESHOLD) >= 0) {
    return "HIGH";
```
**Entrada:** `glosaAmount` >= R$ 5.000,00
**Saída:** `priority` = "HIGH"

---

### RN-GLO-011: Priorização por Valor - Média Prioridade
**Prioridade:** MÉDIA
**Tipo:** Decisão
**Descrição:** Glosas entre R$ 1.000,00 e R$ 4.999,99 recebem prioridade MÉDIA.
**Implementação:**
```java
// Linha 57 (constantes)
private static final BigDecimal MEDIUM_PRIORITY_THRESHOLD = new BigDecimal("1000.00");

// Linha 262-263
} else if (glosaAmount.compareTo(MEDIUM_PRIORITY_THRESHOLD) >= 0) {
    return "MEDIUM";
```
**Entrada:** R$ 1.000,00 <= `glosaAmount` < R$ 5.000,00
**Saída:** `priority` = "MEDIUM"

---

### RN-GLO-012: Atribuição para Valores Altos
**Prioridade:** ALTA
**Tipo:** Decisão
**Descrição:** Glosas acima de R$ 5.000,00 são atribuídas ao time sênior.
**Implementação:**
```java
// Linha 279-281
if (glosaAmount.compareTo(HIGH_PRIORITY_THRESHOLD) >= 0) {
    return "SENIOR_APPEALS_TEAM";
}
```
**Entrada:** `glosaAmount` >= R$ 5.000,00
**Saída:** `assignedTo` = "SENIOR_APPEALS_TEAM"

---

## Limiares de Valor

| Limite | Valor | Aplicação |
|--------|-------|-----------|
| `HIGH_PRIORITY_THRESHOLD` | R$ 5.000,00 | Prioridade ALTA |
| `MEDIUM_PRIORITY_THRESHOLD` | R$ 1.000,00 | Prioridade MÉDIA |

---

## Tipos de Glosa

| Tipo | Descrição | Estratégia Padrão |
|------|-----------|-------------------|
| `FULL_DENIAL` | Negativa total | Baseada em motivo |
| `PARTIAL_DENIAL` | Negativa parcial | STANDARD_APPEAL ou baseada em motivo |
| `UNDERPAYMENT` | Pagamento a menor | QUICK_REVIEW_AND_RESUBMIT |
| `OVERPAYMENT` | Pagamento a maior | REFUND_PROCESSING |
| `NO_GLOSA` | Sem glosa | NO_ACTION_REQUIRED |

---

## Estratégias de Recurso

| Estratégia | Descrição | Time Responsável |
|-----------|-----------|------------------|
| `AUTHORIZATION_APPEAL` | Recurso de autorização | AUTHORIZATION_TEAM |
| `ELIGIBILITY_VERIFICATION_APPEAL` | Verificação de elegibilidade | ELIGIBILITY_TEAM |
| `CODING_REVIEW_APPEAL` | Revisão de codificação | CODING_TEAM |
| `MEDICAL_NECESSITY_APPEAL` | Necessidade médica | CLINICAL_APPEALS_TEAM |
| `TIMELY_FILING_APPEAL` | Prazo de envio | COMPLIANCE_TEAM |
| `COMPREHENSIVE_APPEAL` | Recurso abrangente | GENERAL_APPEALS_TEAM |
| `STANDARD_APPEAL` | Recurso padrão | GENERAL_APPEALS_TEAM |
| `QUICK_REVIEW_AND_RESUBMIT` | Revisão rápida | BILLING_TEAM |
| `REFUND_PROCESSING` | Processamento de estorno | ACCOUNTING_TEAM |
| `DUPLICATE_CLAIM_RESOLUTION` | Resolução de duplicidade | GENERAL_APPEALS_TEAM |
| `MODIFIER_CORRECTION_APPEAL` | Correção de modificadores | CODING_TEAM |

---

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `glosaType` | String | Sim | Tipo de glosa (FULL_DENIAL, PARTIAL_DENIAL, etc.) |
| `glosaReason` | String | Não | Motivo da negativa |
| `glosaAmount` | BigDecimal/Double | Sim | Valor negado |

---

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `appealStrategy` | String | Estratégia de recurso recomendada |
| `priority` | String | Prioridade: HIGH, MEDIUM, LOW |
| `assignedTo` | String | Time/pessoa atribuído para tratar |

---

## Erros BPMN

| Código | Descrição |
|--------|-----------|
| `INVALID_GLOSA_DATA` | Dados de glosa inválidos ou incompletos |
| `ANALYSIS_FAILED` | Análise da glosa falhou |

---

## Integração DMN

**DMN Table:** `glosa-classification.dmn` (comentado, não implementado)
**Propósito:** Permitir que regras de negócio sejam mantidas externamente via DMN
**Entradas DMN Previstas:**
- `glosaType` (String)
- `glosaReason` (String)
- `glosaAmount` (BigDecimal)
- `payerType` (String)
- `serviceType` (String)

**Saídas DMN Previstas:**
- `appealStrategy` (String)
- `priority` (String)
- `assignedTo` (String)

---

## Dependências

- **ADR:** ADR-003 BPMN Implementation Standards
- **Processo:** Glosa Analysis and Appeal Process

---

## Notas de Implementação

1. **Idempotência:** Análise é determinística e naturalmente idempotente (não requer controle especial).
2. **DMN Integration:** Código preparado para integração com DMN mas atualmente usa lógica programática.
3. **Scope de Variáveis:** Variáveis de saída em escopo PROCESS para roteamento e atribuição pelo orquestrador.
4. **Extração de Valor:** Suporta múltiplos tipos numéricos (BigDecimal, Double, Integer, Long, String) para flexibilidade.

---

## Conformidade Regulatória

### Normativas Aplicáveis

| Norma | Artigo/Seção | Descrição | Impacto nas Regras |
|-------|--------------|-----------|-------------------|
| **RN 395/2016 ANS** | Art. 5º | Procedimentos para recursos de glosas | RN-GLO-003 a RN-GLO-007 (estratégias de recurso baseadas em motivo) |
| **RN 388/2015 ANS** | Art. 12 | Prazos para apresentação de recursos | RN-GLO-007 (timely filing appeals) |
| **RN 259/2011 ANS** | Art. 30 | Glosas técnicas e administrativas | RN-GLO-010, RN-GLO-011 (priorização por valor) |
| **Lei 9.656/1998** | Art. 32 | Justificativa de negativas de cobertura | RN-GLO-001, RN-GLO-002 (validação de dados da glosa) |

### Mapeamento de Conformidade

**RN-GLO-007**: Implementa estratégia específica para timely filing conforme RN 388/2015 que estabelece prazos de 10-15 dias para recursos administrativos. Sistema identifica glosas por prazo e escala para equipe de compliance.

**RN-GLO-010, RN-GLO-011, RN-GLO-012**: Priorização por valor alinha-se com práticas de gestão de risco financeiro. Valores ≥ R$ 5.000 recebem atenção de time sênior conforme impacto financeiro significativo.

### Requisitos de Auditoria

- **Rastreamento de Decisões**: Sistema deve registrar motivo, estratégia e time atribuído para cada glosa analisada
- **Evidências de Priorização**: Manter histórico de critérios usados (valor, tipo, motivo) para justificar priorização
- **SLA de Recurso**: Glosas high priority devem ser processadas em até 72h, medium em 7 dias (auditável)

---

## Notas para Migração

### Considerações Tecnológicas

**Do Camunda 7 (Java Delegates) para Camunda 8 (Workers)**:

1. **Lógica de Decisão**:
   - Camunda 7: Switch-case programático em Java
   - Camunda 8: Migrar para DMN tables (`glosa-classification.dmn`)
   - Benefício: Regras de negócio externalizadas, atualizáveis sem redeploy

2. **Gestão de Variáveis**:
   - Tipos numéricos flexíveis devem ser normalizados para BigDecimal em JSON
   - Enum `glosaType` deve ser validado na entrada do worker

3. **Integração DMN**:
   - Código já preparado (linhas comentadas)
   - Ativar DMN decision service em Camunda 8 com decision key `glosa-classification`

### Mudanças Funcionais Necessárias

**Recomendadas**:
- Externalizar limiares (`HIGH_PRIORITY_THRESHOLD`, `MEDIUM_PRIORITY_THRESHOLD`) para configuração
- Adicionar regra de priorização por payer type (públicos vs privados podem ter tratamento diferente)

### Esforço Estimado

- **Complexidade**: MÉDIA (externalização para DMN)
- **Tempo**: 4-5 dias (incluindo criação de DMN tables e testes)
- **Dependências**: DMN engine, validação de business rules com stakeholders

---

## Mapeamento de Domínio

### Conceitos de Negócio

| Conceito | Descrição | Regras Relacionadas |
|----------|-----------|-------------------|
| **Glosa** | Negativa total ou parcial de pagamento por operadora | RN-GLO-001, RN-GLO-002 |
| **Recurso (Appeal)** | Contestação formal de glosa | RN-GLO-003 a RN-GLO-009 |
| **Priorização** | Classificação por urgência baseada em valor e tipo | RN-GLO-010, RN-GLO-011 |
| **Atribuição** | Designação de equipe responsável por recurso | RN-GLO-012 |

### Entidades do Modelo de Domínio

```yaml
Glosa:
  atributos:
    - glosaId: String
    - glosaType: Enum [FULL_DENIAL, PARTIAL_DENIAL, UNDERPAYMENT, OVERPAYMENT]
    - glosaReason: String
    - glosaAmount: BigDecimal (não-negativo)
    - claimId: String
  validacoes:
    - RN-GLO-001 (tipo obrigatório)
    - RN-GLO-002 (valor não-negativo)

AppealStrategy:
  valores_possiveis:
    - AUTHORIZATION_APPEAL
    - ELIGIBILITY_VERIFICATION_APPEAL
    - CODING_REVIEW_APPEAL
    - MEDICAL_NECESSITY_APPEAL
    - TIMELY_FILING_APPEAL
    - STANDARD_APPEAL
  determinacao:
    - RN-GLO-003 a RN-GLO-009

Assignment:
  times_disponiveis:
    - SENIOR_APPEALS_TEAM (valor >= R$ 5.000)
    - AUTHORIZATION_TEAM
    - ELIGIBILITY_TEAM
    - CODING_TEAM
    - CLINICAL_APPEALS_TEAM
    - COMPLIANCE_TEAM
    - GENERAL_APPEALS_TEAM
  regra_atribuicao:
    - RN-GLO-012
```

### Invariantes de Domínio

1. **Valor de glosa nunca negativo**: Sistema valida RN-GLO-002 e rejeita glosas com valor < 0
2. **Estratégia baseada em tipo e motivo**: FULL_DENIAL sempre usa estratégia específica baseada em motivo (RN-GLO-003 a RN-GLO-007)
3. **High priority = Senior team**: Glosas ≥ R$ 5.000 sempre atribuídas a SENIOR_APPEALS_TEAM (RN-GLO-012)

---

## Metadados Estendidos

### Análise de Complexidade

- **Complexidade Ciclomática**: 12 (múltiplas estratégias e decisões aninhadas)
- **Acoplamento**: BAIXO (análise autônoma, sem dependências externas)
- **Coesão**: ALTA (todas as regras relacionadas a análise de glosa)
- **Manutenibilidade**: 75/100 (beneficiaria de externalização para DMN)

### Recomendações de Cobertura de Testes

```yaml
cobertura_minima_recomendada: 90%

cenarios_criticos:
  - glosa_tipo_nulo: RN-GLO-001
  - glosa_valor_negativo: RN-GLO-002
  - full_denial_authorization: RN-GLO-003
  - high_priority_threshold: RN-GLO-010 (R$ 5.000,00)
  - senior_team_assignment: RN-GLO-012

cenarios_edge_case:
  - glosa_exatamente_5000: RN-GLO-010 (boundary test)
  - glosa_1000_01: RN-GLO-011 (medium priority boundary)
  - partial_denial_sem_motivo: RN-GLO-009 (fallback para STANDARD_APPEAL)

cenarios_dmn:
  - glosa_classification_dmn_integration: Validar inputs/outputs DMN
  - dmn_table_multiplos_hits: Testar hit policy FIRST
```

### Impacto de Performance

| Aspecto | Avaliação | Observações |
|---------|-----------|-------------|
| **Latência** | MUITO BAIXA (< 50ms) | Lógica computacional pura, sem I/O |
| **Throughput** | MUITO ALTO | Processamento determinístico em memória |
| **I/O** | NENHUM | Não consulta sistemas externos |
| **Memória** | MUITO BAIXA | Processamento de poucos campos (< 500 bytes) |

**Gargalos Potenciais**: Nenhum identificado.

**Otimizações Recomendadas**:
- Mover lógica para DMN table (facilita manutenção sem impactar performance)
- Adicionar cache de decisões DMN se integrado (TTL 1 hora)

---

## X. Conformidade Regulatória

```yaml
regulatory_compliance:
  tiss_standards:
    - "TISS 4.01 - Estrutura de dados para registro de glosas e justificativas"
    - "TISS 4.01 - Componente Financeiro: campos de glosa e motivo de negativa"
  ans_requirements:
    - "RN 395/2016 Art. 5º - Procedimentos para recursos de glosas"
    - "RN 388/2015 Art. 12 - Prazos para apresentação de recursos (10-15 dias)"
    - "RN 259/2011 Art. 30 - Glosas técnicas e administrativas"
    - "RN 442/2018 - Qualidade assistencial e análise de glosas"
  compliance_requirements:
    - "Lei 9.656/1998 Art. 32 - Justificativa obrigatória de negativas de cobertura"
  audit_trail:
    - "Retention: 5 anos (auditoria financeira ANS)"
    - "Logging: glosaType, glosaReason, appealStrategy, priority, assignedTo, timestamp"
    - "SLA Tracking: HIGH priority 72h, MEDIUM 7 dias"
```

---

## XI. Notas de Migração

```yaml
migration_notes:
  complexity: "MÉDIA"
  estimated_effort: "4-5 dias"
  camunda_8_changes:
    - "DMN Externalization: Ativar glosa-classification.dmn em Camunda 8 decision service"
    - "Variáveis: Normalizar tipos numéricos para BigDecimal em JSON"
    - "Enum Validation: Validar glosaType na entrada do worker"
    - "Decision Service: Usar Zeebe decision evaluation com cache"
  breaking_changes:
    - "Switch-case programático → DMN table (glosa-classification.dmn)"
    - "JavaDelegate → Job Worker com DMN decision call"
    - "Limiares fixos → Configuração externalizada (HIGH_PRIORITY_THRESHOLD, MEDIUM_PRIORITY_THRESHOLD)"
  migration_strategy:
    phases:
      - "Pré-Migração: Criar DMN table baseado em lógica existente, validar hit policy FIRST"
      - "Migração: Converter para job worker com DMN call, testar decision outputs"
      - "Validação: Comparar decisões entre código Java e DMN com 100+ casos"
  critical_dependencies:
    - "DMN decision service (Camunda 8)"
    - "Configuração externa de limiares (R$ 5.000 / R$ 1.000)"
  dmn_candidate: "Sim"
  dmn_rationale: "12 estratégias de recurso com múltiplos branches - ideal para DMN table"
  dmn_migration_notes:
    - "Validar hit policy FIRST no DMN 1.3 (primeira regra que bate)"
    - "Testar inputs/outputs com boundary values (R$ 5.000,00 / R$ 1.000,00)"
    - "Externalizar limiares para configuração (permitir ajustes sem redeploy)"
```

---

## XII. Mapeamento DDD

```yaml
domain_mapping:
  bounded_context: "Glosa Management & Appeals"
  aggregate_root: "Glosa"
  aggregates:
    - identity: "Glosa"
      properties:
        - "glosaId"
        - "glosaType (FULL_DENIAL|PARTIAL_DENIAL|UNDERPAYMENT|OVERPAYMENT)"
        - "glosaReason (String)"
        - "glosaAmount (BigDecimal, não-negativo)"
        - "claimId"
        - "analysisDate"
      behaviors:
        - "validate() - RN-GLO-001, RN-GLO-002"
        - "analyze() - determinar estratégia e prioridade"
        - "categorize() - classificar tipo de glosa"
    - identity: "AppealStrategy"
      properties:
        - "strategy (Enum: AUTHORIZATION_APPEAL, ELIGIBILITY_VERIFICATION_APPEAL, etc.)"
        - "assignedTo (team)"
        - "priority (HIGH|MEDIUM|LOW)"
      behaviors:
        - "determineFromReason() - RN-GLO-003 a RN-GLO-009"
        - "prioritizeByValue() - RN-GLO-010, RN-GLO-011"
        - "assignToTeam() - RN-GLO-012"
  domain_events:
    - name: "GlosaAnalyzed"
      payload:
        - "glosaId"
        - "appealStrategy"
        - "priority"
        - "assignedTo"
        - "analysisDate"
    - name: "HighValueGlosaDetected"
      payload:
        - "glosaId"
        - "glosaAmount (>= R$ 5.000)"
        - "assignedTo (SENIOR_APPEALS_TEAM)"
    - name: "GlosaAnalysisFailed"
      payload:
        - "glosaId"
        - "failureReason (INVALID_GLOSA_DATA)"
  microservice_candidate:
    viable: true
    service_name: "glosa-analysis-service"
    bounded_context: "Glosa Management"
    api_style: "Event-Driven + DMN Decision Service"
    upstream_dependencies:
      - "claim-service (glosa details)"
      - "dmn-decision-service (glosa-classification.dmn)"
    downstream_consumers:
      - "appeal-workflow-service (consumes GlosaAnalyzed)"
      - "senior-appeals-queue (consumes HighValueGlosaDetected)"
```

---

## XIII. Metadados Técnicos

```yaml
technical_metadata:
  complexity:
    cyclomatic: 12
    cognitive: 18
    loc: 300
    decision_points: 15
    rationale: "12 estratégias de recurso + múltiplas decisões aninhadas (tipo, motivo, valor)"
  test_coverage:
    recommended: "90%"
    critical_paths:
      - "Glosa tipo nulo (RN-GLO-001)"
      - "Glosa valor negativo (RN-GLO-002)"
      - "FULL_DENIAL + AUTHORIZATION reason (RN-GLO-003)"
      - "PARTIAL_DENIAL + DUPLICATE reason (RN-GLO-008)"
      - "Valor exatamente R$ 5.000,00 (boundary high priority)"
      - "Valor exatamente R$ 1.000,00 (boundary medium priority)"
    edge_cases:
      - "glosaAmount = R$ 4.999,99 (MEDIUM priority, não HIGH)"
      - "glosaAmount = R$ 999,99 (LOW priority)"
      - "PARTIAL_DENIAL sem motivo específico (fallback STANDARD_APPEAL)"
    dmn_integration_tests:
      - "DMN decision com glosa-classification.dmn"
      - "Hit policy FIRST validation (primeira regra que bate)"
      - "Inputs: glosaType, glosaReason, glosaAmount"
      - "Outputs: appealStrategy, priority, assignedTo"
  performance:
    target_p50: "30ms"
    target_p95: "80ms"
    target_p99: "150ms"
    bottlenecks:
      - "Nenhum (lógica computacional pura, sem I/O)"
      - "DMN evaluation (se integrado): adicionar 20-50ms"
    optimization_recommendations:
      - "Cache de decisões DMN (TTL 1 hora, se externalizado)"
      - "Mover lógica para DMN table (facilita manutenção)"
  scalability:
    expected_tps: "500-800"
    limited_by: "CPU para decision logic (muito baixo)"
    horizontal_scaling: true
  monitoring:
    key_metrics:
      - "glosa_analysis_count"
      - "high_priority_glosas_count"
      - "senior_team_assignments_count"
      - "appeal_strategy_distribution (por tipo)"
    alerts:
      - "High priority glosas > 50 in 1 hour"
      - "Glosa analysis failures > 5% in 5 minutes"
```

---

**Gerado automaticamente em:** 2026-01-12
**Fonte:** Análise de código Camunda 7
**Revisão de Esquema:** 2026-01-12
