# Regras de Negócio - GenerateClaimDelegate

**Arquivo:** `GenerateClaimDelegate.java`
**Domínio:** Billing (Faturamento)
**Processo BPMN:** SUB_06 Billing Submission Process
**Versão:** 2.0
**Data:** 2025-12-23

---

## Visão Geral

Delegate responsável por gerar guias de cobrança (claims) a partir de dados de atendimento com cálculo baseado em DMN.

---

## Regras de Negócio Identificadas

### RN-GEN-001: Validação de Formato de Códigos TUSS
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Códigos TUSS devem seguir formato de 8 dígitos numéricos.
**Implementação:**
```java
// Linha 140-142
private boolean isValidTUSSCode(String code) {
    return code.matches("\\d{8}");
}
```
**Entrada:** `procedureCodes` (List<String>)
**Saída:** Validação booleana
**Erro:** `INVALID_PROCEDURE_CODES` se formato inválido

---

### RN-GEN-002: Validação de Formato de Códigos CBHPM
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Códigos CBHPM devem seguir formato X.XX.XX.XX-X (ex: 1.01.01.01-0).
**Implementação:**
```java
// Linha 147-150
private boolean isValidCBHPMCode(String code) {
    // CBHPM codes: 1.01.01.01-0 format
    return code.matches("\\d\\.\\d{2}\\.\\d{2}\\.\\d{2}-\\d");
}
```
**Entrada:** `procedureCodes` (List<String>)
**Saída:** Validação booleana
**Erro:** `INVALID_PROCEDURE_CODES` se formato inválido

---

### RN-GEN-003: Proibição de Códigos Vazios
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Lista de códigos de procedimento não pode ser nula, vazia ou conter códigos vazios.
**Implementação:**
```java
// Linha 116-125
if (procedureCodes == null || procedureCodes.isEmpty()) {
    throw new BpmnError("INVALID_PROCEDURE_CODES",
            "Procedure codes list cannot be null or empty");
}

for (String code : procedureCodes) {
    if (code == null || code.trim().isEmpty()) {
        throw new BpmnError("INVALID_PROCEDURE_CODES",
                "Procedure code cannot be null or empty");
    }
}
```
**Entrada:** `procedureCodes` (List<String>)
**Erro:** `INVALID_PROCEDURE_CODES`

---

### RN-GEN-004: Geração de ID Único de Guia
**Prioridade:** MÉDIA
**Tipo:** Processamento
**Descrição:** ID de guia deve seguir formato CLM-{encounterId}-{timestamp}.
**Implementação:**
```java
// Linha 157-160
private String generateClaimId(String encounterId) {
    long timestamp = System.currentTimeMillis();
    return String.format("CLM-%s-%d", encounterId, timestamp);
}
```
**Entrada:** `encounterId` (String)
**Saída:** `claimId` (String)

---

### RN-GEN-005: Cálculo de Total de Guia
**Prioridade:** ALTA
**Tipo:** Cálculo
**Descrição:** Valor total da guia é a soma de todos os itens individuais.
**Implementação:**
```java
// Linha 220-224
private BigDecimal calculateTotalAmount(List<Map<String, Object>> claimItems) {
    return claimItems.stream()
            .map(item -> (BigDecimal) item.get("totalPrice"))
            .reduce(BigDecimal.ZERO, BigDecimal::add);
}
```
**Entrada:** `claimItems` (List<Map>)
**Saída:** `claimAmount` (BigDecimal)

---

### RN-GEN-006: Validação de Valor Mínimo
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Valor calculado da guia deve ser maior que zero.
**Implementação:**
```java
// Linha 253-256
if (claimAmount.compareTo(BigDecimal.ZERO) <= 0) {
    throw new BpmnError("CALCULATION_ERROR",
            "Calculated claim amount must be greater than zero");
}
```
**Entrada:** `claimAmount` (BigDecimal)
**Erro:** `CALCULATION_ERROR`

---

### RN-GEN-007: Limite Máximo de Valor de Guia
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Guias com valor final superior a R$ 1.000.000,00 são rejeitadas.
**Implementação:**
```java
// Linha 304-307
if (finalAmount > 1000000.00) {
    throw new BpmnError("CALCULATION_ERROR",
            "Final claim amount exceeds maximum allowed value: " + finalAmount);
}
```
**Entrada:** `finalAmount` (Double - do DMN)
**Erro:** `CALCULATION_ERROR`

---

### RN-GEN-008: Integração com DMN de Cálculo de Faturamento
**Prioridade:** ALTA
**Tipo:** Integração
**Descrição:** Sistema deve invocar billing-calculation.dmn para validação e cálculo final considerando contratos e glosas.
**Implementação:**
```java
// Linha 266-278
Map<String, Object> dmnInput = new HashMap<>();
dmnInput.put("procedureType", procedureType);
dmnInput.put("insuranceTable", insuranceTable);
dmnInput.put("baseValue", claimAmount.doubleValue());
dmnInput.put("hasGlosa", hasGlosa);
dmnInput.put("glosaPercentage", glosaPercentage);

// Execute DMN decision table
Map<String, Object> dmnResult = evaluateDMN(execution, "billing-calculation", dmnInput);
```
**Entrada:**
- `procedureType` (String): SURGICAL, CLINICAL, DIAGNOSTIC, THERAPEUTIC, HOSPITALIZATION
- `insuranceTable` (String): SUS, AMB, CBHPM, BRASINDICE, SIMPRO, CUSTOM
- `baseValue` (Double)
- `hasGlosa` (Boolean)
- `glosaPercentage` (Double)

**Saída:**
- `billableAmount` (Double)
- `discountApplied` (Double)
- `finalAmount` (Double)
- `calculationRule` (String)
- `needsAudit` (Boolean)

---

### RN-GEN-009: Validação de Valor Final DMN
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Valor final retornado pelo DMN deve ser maior que zero.
**Implementação:**
```java
// Linha 299-302
if (finalAmount <= 0) {
    throw new BpmnError("CALCULATION_ERROR",
            "Final claim amount must be greater than zero: " + finalAmount);
}
```
**Entrada:** `finalAmount` (Double - do DMN)
**Erro:** `CALCULATION_ERROR`

---

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `encounterId` | String | Sim | Identificador único do atendimento |
| `patientId` | String | Sim | Identificador do paciente |
| `procedureCodes` | List<String> | Sim | Lista de códigos de procedimento (TUSS/CBHPM) |
| `insuranceId` | String | Não | Identificador do convênio para lookup de tabela |
| `hasGlosa` | Boolean | Não (default: false) | Indica se há glosa |
| `glosaPercentage` | Double | Não (default: 0.0) | Percentual de glosa |

---

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `claimId` | String | ID único da guia gerada |
| `claimAmount` | BigDecimal | Valor inicial calculado |
| `claimItems` | List<Map> | Itens da guia com códigos e valores |
| `claimGeneratedDate` | LocalDateTime | Data/hora de geração |
| `billableAmount` | BigDecimal | Valor faturável (do DMN) |
| `discountApplied` | BigDecimal | Desconto aplicado (do DMN) |
| `finalClaimAmount` | BigDecimal | Valor final após DMN |
| `calculationRule` | String | Regra usada no cálculo (do DMN) |
| `needsAudit` | Boolean | Se necessita auditoria (do DMN) |

---

## Erros BPMN

| Código | Descrição |
|--------|-----------|
| `ENCOUNTER_NOT_FOUND` | Atendimento não existe |
| `INVALID_PROCEDURE_CODES` | Códigos de procedimento inválidos |
| `CALCULATION_ERROR` | Falha no cálculo ou valor excede máximo |

---

## Dependências

- **DMN:** `billing-calculation.dmn`
- **Padrões:** TUSS (8 dígitos), CBHPM (X.XX.XX.XX-X)
- **ADR:** ADR-003 BPMN Implementation Standards
- **Processo:** SUB_06 Billing Submission Process

---

## Notas de Implementação

1. **Pricing Mock:** Implementação atual usa preços mockados. Em produção, deve consultar tabelas de preços por contrato.
2. **DMN Fallback:** Sistema continua operação mesmo se DMN falhar, usando lógica programática.
3. **Scope de Variáveis:** Todas as variáveis de saída são definidas em escopo PROCESS para rastreamento pelo orquestrador.
4. **Determinação de Tipo:** Tipo de procedimento é derivado do primeiro código (mock - produção deve usar tabela de classificação).

---

## 🏛️ Conformidade Regulatória

```yaml
tiss_standards:
  - "TISS 4.0 - Estrutura de dados para geração de guias (SP/SADT, Honorários, Internação)"
  - "TISS 4.0 - Vínculo obrigatório entre atendimento e guia gerada"
  - "TISS 4.0 - Rastreabilidade de origem dos dados da conta"
  - "TISS 4.0 - Validação de códigos TUSS (8 dígitos) e CBHPM (formato X.XX.XX.XX-X)"
ans_requirements:
  - "RN 305/2012 - Prazo para envio de contas após alta do paciente"
  - "RN 124/2006 - Requisitos mínimos de informações em guias TISS"
  - "RN 424/2017 - Padrão obrigatório TISS para intercâmbio de informações"
lgpd_considerations:
  - "Art. 11 - Tratamento de dados sensíveis de saúde com finalidade de prestação de serviços de saúde"
  - "Art. 37 - Controlador deve manter registro das operações de geração de contas"
  - "Art. 46 - Garantir rastreabilidade da origem dos dados clínicos"
audit_trail:
  - "Retention: 20 anos (conforme Resolução CFM 1821/2007)"
  - "Logging: encounter_id, claim_id, generated_by, timestamp, claim_status, procedure_codes, claim_amount"
  - "Rastreabilidade: Vincular claim ao encounter original para auditoria ANS"
```

## 🚀 Notas para Migração

```yaml
microservices_target: "claim-generation-service"
camunda_alternative: "Event-Driven Architecture"
breaking_changes:
  - "Substituir chamadas síncronas ao ClaimService por eventos assíncronos (EncounterCompletedEvent)"
  - "Migrar de delegate Camunda para handler de evento"
  - "Refatorar variáveis de processo BPMN para contexto de evento"
  - "Substituir DMN billing-calculation por regras externalizadas (REST API ou configuração)"
data_migration:
  - "Mapear variáveis BPMN (encounterId, procedureCodes, insuranceId) para payload de evento"
  - "Migrar registros de execução de tarefas para event sourcing"
  - "Preservar audit trail de geração de claims durante transição"
technology_agnostic_implementation: |
  Implementar como serviço reativo que:

  1. **Entrada por Evento**: Escuta "EncounterCompletedEvent" ou "GenerateClaimRequested"
  2. **Busca de Dados**: Consulta dados do atendimento via API de Encounters
  3. **Transformação**: Aplica regras de negócio para mapear encounter → claim
  4. **Validação**: Verifica códigos de procedimento (TUSS/CBHPM) e dados obrigatórios
  5. **Pricing**: Consulta tabelas de preços contratuais (substituir mock por API)
  6. **Cálculo**: Aplica regras de faturamento (substituir DMN por Rules Engine externo)
  7. **Persistência**: Salva claim gerada com status DRAFT
  8. **Evento de Saída**: Publica "ClaimGenerated" para downstream services
  9. **Idempotência**: Usa claim_id único para evitar duplicação

  Alternativas de orquestração:
  - Temporal Workflow para processos de longa duração
  - Apache Kafka + KSQL para processamento em stream
  - REST API síncrona para casos simples
  - Business Rules Engine (Drools, Easy Rules) para substituir DMN
```

## 🗺️ Mapeamento de Domínio

```yaml
bounded_context: "Claims Management"
aggregate_root: "Claim"
entities:
  - "Claim"
  - "ClaimLineItem (procedure code, quantidade, valor unitário)"
  - "ClaimDiagnosis (códigos ICD-10)"
value_objects:
  - "ClaimId (CLM-{encounterId}-{timestamp})"
  - "EncounterReference"
  - "ClaimStatus (DRAFT, SUBMITTED, APPROVED, DENIED)"
  - "DatePeriod (startDate, endDate)"
  - "ProcedureCode (TUSS ou CBHPM com validação de formato)"
  - "ClaimAmount (BigDecimal com precisão financeira)"
domain_events:
  - name: "ClaimGenerated"
    payload:
      - "claimId"
      - "encounterId"
      - "patientId"
      - "providerId"
      - "procedureCodes"
      - "generatedAt"
      - "claimStatus"
      - "totalAmount"
      - "billableAmount"
  - name: "ClaimGenerationFailed"
    payload:
      - "encounterId"
      - "failureReason"
      - "timestamp"
      - "procedureCodes"
microservice_candidate:
  service_name: "claim-generation-service"
  api_style: "Event-Driven"
  upstream_dependencies:
    - "encounter-service (read encounter data)"
    - "pricing-service (substituir mock de preços)"
  downstream_consumers:
    - "claim-validation-service (consumes ClaimGenerated)"
    - "billing-service (consumes ClaimGenerated)"
```

## 📊 Metadados

```yaml
complexity: "MÉDIA"
test_coverage_recommendation: "90%"
performance_impact: "MEDIUM"
version: "1.0.0"
last_updated: "2025-01-12T00:00:00Z"
rationale: |
  Complexidade MÉDIA devido a:
  - Transformação de dados entre domínios (Encounter → Claim)
  - Suporte a batch processing (período de datas)
  - Integração com múltiplas entidades
  - Validação de múltiplos formatos de código (TUSS e CBHPM)
  - Integração com DMN para cálculo de faturamento

  Performance MEDIUM devido a:
  - Operações de I/O de banco de dados
  - Potencial processamento em lote de múltiplos atendimentos
  - Dependência de latência do ClaimService
  - Chamada ao DMN para cálculo (pode ser otimizada com cache)

  Alta cobertura de testes recomendada devido a:
  - Impacto financeiro direto (erros afetam faturamento)
  - Validações críticas de formato de código
  - Conformidade com padrões TISS obrigatória
```

---

## X. Conformidade Regulatória

```yaml
regulatory_compliance:
  tiss_standards:
    - "TISS 4.0 - Estrutura de dados para geração de guias SP/SADT, Honorários, Internação"
    - "TISS 4.0 - Validação de códigos TUSS (8 dígitos) e CBHPM (X.XX.XX.XX-X)"
    - "TISS 4.0 - Vínculo obrigatório entre encounterId e claimId gerado"
    - "TISS 4.0 - Rastreabilidade de origem dos dados clínicos na conta"
  ans_requirements:
    - "RN 305/2012 - Prazo para envio de contas após alta do paciente (30-60 dias)"
    - "RN 124/2006 - Requisitos mínimos de informações em guias TISS"
    - "RN 424/2017 - Padrão obrigatório TISS para intercâmbio de informações de saúde"
    - "RN 442/2018 - Qualidade assistencial e coerência entre procedimentos e diagnósticos"
  lgpd_considerations:
    - "Art. 11 - Tratamento de dados sensíveis de saúde (procedureCodes vinculados a patientId)"
    - "Art. 37 - Registro de operações de geração de contas para auditoria"
    - "Art. 46 - Rastreabilidade da origem dos dados clínicos (encounter → claim)"
  audit_trail:
    - "Retention: 20 anos (Resolução CFM 1821/2007 - prontuário médico)"
    - "Logging: encounterId, claimId, procedureCodes, claimAmount, generatedBy, timestamp"
    - "Compliance: Manter vínculo encounter-claim para auditorias ANS"
```

---

## XI. Notas de Migração

```yaml
migration_notes:
  complexity: "MÉDIA"
  estimated_effort: "5-6 dias"
  camunda_8_changes:
    - "Event-Driven: Substituir delegate por handler de EncounterCompletedEvent"
    - "DMN Integration: Externalizar billing-calculation.dmn para Camunda 8 decision service"
    - "Pricing API: Substituir mock por REST API para tabelas de preços contratuais"
    - "Variables: Serializar procedureCodes e claimItems como JSON payload"
  breaking_changes:
    - "JavaDelegate → Event Handler assíncrono"
    - "Variáveis BPMN → Event payload (JSON)"
    - "DMN síncrono → DMN decision service com cache"
    - "ClaimService mock → API real de persistência de claims"
  migration_strategy:
    phases:
      - "Pré-Migração: Implementar API de pricing e validar tabelas de preços"
      - "Migração: Converter para event handler, testar DMN decision service"
      - "Validação: Comparar claims geradas entre Camunda 7 e 8 por 2 semanas"
  critical_dependencies:
    - "Encounter service API (dados de atendimento)"
    - "Pricing service API (tabelas TUSS/CBHPM/contratuais)"
    - "DMN decision service (billing-calculation.dmn)"
  dmn_candidate: "Sim"
  dmn_rationale: "billing-calculation.dmn já implementado - migração direta para Camunda 8"
  dmn_migration_notes:
    - "Validar hit policy FIRST no DMN 1.3"
    - "Testar inputs/outputs com valores limite (R$ 0, R$ 1.000.000)"
```

---

## XII. Mapeamento DDD

```yaml
domain_mapping:
  bounded_context: "Claims Management"
  aggregate_root: "Claim"
  aggregates:
    - identity: "Claim"
      properties:
        - "claimId (CLM-{encounterId}-{timestamp})"
        - "encounterId"
        - "patientId"
        - "procedureCodes (List<String>)"
        - "claimAmount (BigDecimal)"
        - "claimStatus (DRAFT|SUBMITTED|APPROVED|DENIED)"
        - "generatedAt"
      behaviors:
        - "validate() - RN-GEN-001 a RN-GEN-003"
        - "calculateTotal() - RN-GEN-005"
        - "applyContractRules() - RN-GEN-008 (DMN)"
        - "submit() - transição DRAFT → SUBMITTED"
    - identity: "ClaimLineItem"
      properties:
        - "procedureCode (TUSS|CBHPM)"
        - "quantity"
        - "unitPrice"
        - "totalPrice"
      behaviors:
        - "validateCode() - formato TUSS/CBHPM"
  domain_events:
    - name: "ClaimGenerated"
      payload:
        - "claimId"
        - "encounterId"
        - "patientId"
        - "procedureCodes"
        - "claimAmount"
        - "billableAmount"
        - "generatedAt"
    - name: "ClaimGenerationFailed"
      payload:
        - "encounterId"
        - "failureReason (INVALID_PROCEDURE_CODES|CALCULATION_ERROR)"
        - "timestamp"
  microservice_candidate:
    viable: true
    service_name: "claim-generation-service"
    bounded_context: "Claims Management"
    api_style: "Event-Driven (async) + REST (sync)"
    upstream_dependencies:
      - "encounter-service (read encounter data)"
      - "pricing-service (tabelas de preços contratuais)"
      - "dmn-decision-service (billing-calculation)"
    downstream_consumers:
      - "claim-validation-service (consumes ClaimGenerated)"
      - "billing-submission-service (consumes ClaimGenerated)"
```

---

## XIII. Metadados Técnicos

```yaml
technical_metadata:
  complexity:
    cyclomatic: 10
    cognitive: 15
    loc: 320
    decision_points: 8
    rationale: "Validação múltipla de códigos + integração DMN + batch processing"
  test_coverage:
    recommended: "90%"
    critical_paths:
      - "Validação formato TUSS (8 dígitos)"
      - "Validação formato CBHPM (X.XX.XX.XX-X)"
      - "Cálculo total com múltiplos itens"
      - "DMN integration com valores limite"
      - "Valor final > R$ 1.000.000 (erro)"
    integration_tests_required:
      - "DMN service indisponível (fallback lógico)"
      - "Pricing service timeout (retry logic)"
      - "Claim generation com 100+ procedureCodes (performance)"
  performance:
    target_p50: "150ms"
    target_p95: "400ms"
    target_p99: "800ms"
    bottlenecks:
      - "DMN evaluation (50-150ms)"
      - "ClaimService persistence (50-100ms)"
      - "Pricing lookup mockado (em produção: 100-200ms)"
    optimization_recommendations:
      - "Cache de DMN decisions (TTL 1 hora)"
      - "Batch pricing lookup (múltiplos códigos)"
      - "Async claim persistence com callback"
  scalability:
    expected_tps: "200-300"
    limited_by: "DMN decision service throughput"
    horizontal_scaling: true
  monitoring:
    key_metrics:
      - "claims_generated_count"
      - "claim_generation_errors_count"
      - "dmn_evaluation_latency_ms"
      - "invalid_procedure_codes_count"
    alerts:
      - "Claim generation errors > 10% in 5 minutes"
      - "DMN evaluation latency > 500ms (p95)"
```

---

**Gerado automaticamente em:** 2026-01-12
**Fonte:** Análise de código Camunda 7
