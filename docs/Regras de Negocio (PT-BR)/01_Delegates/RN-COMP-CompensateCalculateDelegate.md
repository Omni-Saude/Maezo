# Regras de Negócio: CompensateCalculateDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateCalculateDelegate.java`
> **Pacote:** `com.hospital.revenuecycle.delegates.compensation`
> **Categoria:** Delegate de Compensação (Cálculos de Faturamento)
> **Gerado em:** 2026-01-12T12:30:00Z
> **Versão do Documento:** 1.0.0

---

## 📋 Sumário Executivo

| Métrica | Valor |
|---------|-------|
| Total de Regras | 7 |
| Regras de Validação | 2 |
| Regras de Compensação | 5 |
| Complexidade Geral | ALTA |
| Criticidade de Negócio | CRÍTICA |

---

## 🎯 Contexto e Propósito

Este delegate implementa compensação para cálculos de faturamento no ciclo de receita hospitalar. Quando cálculos de valores (aplicação de regras contratuais, glosas, ou consolidação de cobranças) falham, todas as alterações de valores devem ser revertidas para manter consistência financeira.

A compensação de cálculos é crítica pois valores incorretos podem causar cobranças indevidas às operadoras, discrepâncias contábeis e perda de confiança no sistema de faturamento. Erros em cálculos podem resultar em glosas (rejeições) ou até processos de auditoria da ANS.

---

## 📜 Catálogo de Regras

### RN-COMP-CALC-001: Compensação de Cálculo de Faturamento

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-CALC-001"
rule_name: "Compensação de Cálculo de Faturamento"
version: "1.0.0"
last_updated: "2026-01-12T12:30:00Z"
category: "COMPENSAÇÃO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Reverte cálculos de faturamento de acordo com o tipo (CONTRACT, GLOSA, ou BILLING), restaurando valores originais e limpando cache.

**Contexto de Negócio:** No processo de faturamento, diversas regras de cálculo são aplicadas: descontos contratuais, cálculo de glosas, consolidação de cobranças. Se um cálculo falha ou precisa ser refeito, os valores anteriores devem ser restaurados.

**Objetivo:** Garantir que valores de cobranças retornem ao estado anterior ao cálculo, permitindo recálculo ou cancelamento da operação.

#### 🔧 Especificação

**Pré-condições:**
- Cálculo foi executado (calculationId existe)
- Sistema possui registro do valor original (originalAmount)
- Tipo de cálculo é válido (CONTRACT, GLOSA, ou BILLING)
- Claim relacionado existe

**Lógica da Regra:**

```
SE cálculo de faturamento falhou OU requer reversão
ENTÃO
  SELECIONAR tipo de compensação conforme calculationType:

    CASO "CONTRACT":
      1. Deletar aplicações de regras contratuais
      2. Restaurar valores originais de cobranças
      3. Atualizar valor total do claim
      4. Limpar cache de pricing
      5. Atualizar status do claim para "PENDING_CALCULATION"
      6. Notificar equipe de pricing

    CASO "GLOSA":
      1. Deletar cálculos de glosa
      2. Zerar valores calculados de glosa
      3. Restaurar valores originais do claim
      4. Atualizar status da glosa para "PENDING_ANALYSIS"
      5. Notificar gestão de glosas

    CASO "BILLING":
      1. Reverter consolidação de faturamento
      2. Restaurar itens de cobrança individuais
      3. Deletar sumários de faturamento criados
      4. Cancelar lançamentos de fatura
      5. Atualizar status do claim para "PENDING_BILLING"
      6. Notificar operações de faturamento

  FIM SELECIONAR

  Executar compensação comum:
    - Deletar registro de cálculo
    - Limpar cache de resultados
    - Criar registro de auditoria
    - Notificar equipe de faturamento
    - Marcar compensação como completa

SENÃO
  Nenhuma ação necessária
FIM SE
```

**Pós-condições:**
- Cálculos revertidos conforme tipo
- Valores originais restaurados
- Cache limpo
- Notificações enviadas
- Trilha de auditoria atualizada

**Exceções:**
| Condição | Exceção | Tratamento |
|----------|---------|------------|
| calculationId não existe | RuntimeException | Falha na compensação, escalar |
| Tipo de cálculo desconhecido | BusinessRuleException | Executar compensação genérica, alertar |
| Claim já foi faturado | InvalidStateException | Requerer aprovação manual, alertar controller |

#### 📊 Parâmetros

| Parâmetro | Tipo | Descrição | Restrições | Exemplo |
|-----------|------|-----------|------------|---------|
| calculationId | Identificador Único | Identificador do cálculo a compensar | Obrigatório | "calc-123-abc" |
| claimId | Identificador Único | Identificador do claim | Obrigatório | "claim-456-def" |
| originalAmount | Decimal | Valor antes do cálculo | Obrigatório, >= 0 | 5000.00 |
| calculationType | Enumeração | Tipo de cálculo | Obrigatório: CONTRACT, GLOSA, BILLING | "CONTRACT" |

**Saídas:**
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| compensationCompleted | Booleano | Sucesso da compensação | true |
| restoredAmount | Decimal | Valor restaurado | 5000.00 |
| compensationTimestamp | Data/Hora | Momento da compensação | "2026-01-12T14:30:00Z" |
| calculationReverted | Booleano | Cálculo foi revertido | true |

---

### RN-COMP-CALC-002: Compensação de Cálculo Contratual

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-CALC-002"
rule_name: "Compensação de Cálculo de Regras Contratuais"
version: "1.0.0"
last_updated: "2026-01-12T12:30:00Z"
category: "COMPENSAÇÃO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Reverte aplicação de regras contratuais (descontos, tabelas de preços, co-participações) aos valores de cobrança.

**Contexto de Negócio:** Contratos com operadoras definem descontos por procedimento, limites de cobertura, e valores específicos. Se estes cálculos falharem, valores originais (tabela SUS ou AMB) devem ser restaurados.

**Especificação:**

```
EXECUTAR operações SQL:
  -- Deletar aplicações de regras contratuais
  DELETE FROM contract_applications
  WHERE calculation_id = calculationId

  -- Restaurar valores originais nas cobranças
  UPDATE charges
  SET amount = original_amount,
      discount_applied = 0,
      contract_rule_id = NULL
  WHERE calculation_id = calculationId

  -- Atualizar total do claim
  UPDATE claims
  SET total_amount = (
    SELECT SUM(original_amount)
    FROM charges
    WHERE claim_id = claimId
  )
  WHERE claim_id = claimId

  -- Limpar cache de pricing
  DELETE FROM pricing_cache
  WHERE claim_id = claimId

  -- Atualizar status
  UPDATE claims
  SET status = 'PENDING_CALCULATION',
      last_calculated_at = NULL
  WHERE claim_id = claimId

NOTIFICAR equipe de pricing via Kafka
```

---

### RN-COMP-CALC-003: Compensação de Cálculo de Glosa

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-CALC-003"
rule_name: "Compensação de Cálculo de Valor de Glosa"
version: "1.0.0"
last_updated: "2026-01-12T12:30:00Z"
category: "COMPENSAÇÃO"
complexity: "MÉDIA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Reverte cálculos de valores de glosa (negativas de pagamento), zerando glosas calculadas e restaurando valores de claim.

**Especificação:**

```
EXECUTAR operações:
  -- Deletar cálculos de glosa
  DELETE FROM glosa_calculations
  WHERE calculation_id = calculationId

  -- Zerar valores calculados de glosa
  UPDATE glosas
  SET calculated_amount = 0,
      calculation_id = NULL
  WHERE calculation_id = calculationId

  -- Restaurar valor total do claim (sem dedução de glosa)
  UPDATE claims
  SET glosa_amount = 0,
      net_amount = total_amount
  WHERE claim_id = claimId

  -- Atualizar status da glosa
  UPDATE glosas
  SET status = 'PENDING_ANALYSIS'
  WHERE claim_id = claimId
    AND calculation_id = calculationId

NOTIFICAR gestão de glosas
```

---

### RN-COMP-CALC-004: Compensação de Consolidação de Faturamento

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-CALC-004"
rule_name: "Compensação de Consolidação de Faturamento"
version: "1.0.0"
last_updated: "2026-01-12T12:30:00Z"
category: "COMPENSAÇÃO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Reverte consolidação de cobranças em fatura, restaurando itens individuais e cancelando sumários.

**Contexto de Negócio:** Consolidação agrupa múltiplas cobranças em uma fatura para submissão à operadora. Se falhar, itens individuais devem retornar ao estado "não faturado".

**Especificação:**

```
EXECUTAR operações:
  -- Deletar sumários de faturamento
  DELETE FROM billing_summaries
  WHERE calculation_id = calculationId

  -- Restaurar status individual de cobranças
  UPDATE charges
  SET status = 'UNBILLED',
      invoice_id = NULL,
      consolidated_at = NULL
  WHERE calculation_id = calculationId

  -- Atualizar status do claim
  UPDATE claims
  SET billing_status = 'PENDING',
      invoiced_at = NULL
  WHERE claim_id = claimId

  -- Cancelar lançamento de fatura (se criado)
  UPDATE invoices
  SET status = 'CANCELLED',
      cancelled_at = AGORA
  WHERE calculation_id = calculationId

NOTIFICAR operações de faturamento
```

---

### RN-COMP-CALC-005: Compensação Genérica de Cálculo

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-CALC-005"
rule_name: "Compensação Genérica para Tipos Desconhecidos"
version: "1.0.0"
last_updated: "2026-01-12T12:30:00Z"
category: "COMPENSAÇÃO"
complexity: "BAIXA"
criticality: "MÉDIA"
test_coverage_recommendation: "90%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Executa compensação segura para tipos de cálculo não reconhecidos, deletando apenas o registro de cálculo.

**Especificação:**

```
EXECUTAR operação mínima:
  DELETE FROM billing_calculations
  WHERE calculation_id = calculationId

LOG warning "Tipo de cálculo desconhecido compensado: {calculationType}"
ALERTAR administrador do sistema
```

---

### RN-COMP-CALC-006: Operações Comuns de Compensação

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-CALC-006"
rule_name: "Operações Comuns para Todos os Tipos de Cálculo"
version: "1.0.0"
last_updated: "2026-01-12T12:30:00Z"
category: "COMPENSAÇÃO"
complexity: "MÉDIA"
criticality: "ALTA"
test_coverage_recommendation: "90%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Executa operações comuns após compensação específica: limpeza de cache, auditoria, notificações.

**Especificação:**

```
EXECUTAR após compensação específica:
  1. Deletar registro de cálculo
     DELETE FROM billing_calculations
     WHERE calculation_id = calculationId

  2. Limpar cache de resultados
     DELETE FROM calculation_cache
     WHERE calculation_id = calculationId

  3. Criar registro de auditoria
     INSERT INTO compensation_audit (
       calculation_id, claim_id, original_amount,
       calculation_type, compensated_at, compensated_by
     ) VALUES (...)

  4. Notificar equipe de faturamento
     PUBLISH kafka event "billing-compensations"

  5. Considerar recálculo automático
     SE configuration.auto_recalculate = true
     ENTÃO
       AGENDAR recálculo do claim
     FIM SE
```

---

### RN-COMP-CALC-007: Idempotência de Compensação de Cálculo

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-CALC-007"
rule_name: "Garantia de Idempotência em Compensação de Cálculo"
version: "1.0.0"
last_updated: "2026-01-12T12:30:00Z"
category: "VALIDAÇÃO"
complexity: "MÉDIA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Garante que múltiplas execuções da compensação de cálculo produzam o mesmo resultado.

**Especificação:**

```
ANTES de executar compensação:
  VERIFICAR se compensação já foi executada:
    SELECT compensation_completed
    FROM saga_compensation_log
    WHERE transaction_id = processInstanceId
      AND operation = "calculate_billing"

  SE compensation_completed = true
  ENTÃO
    LOG "Compensação de cálculo já executada"
    RETORNAR sucesso (idempotente)
  SENÃO
    EXECUTAR compensação conforme tipo
    MARCAR compensation_completed = true
  FIM SE
```

---

## 🗺️ Mapeamento de Domínio

```yaml
bounded_context: "Billing"
aggregate_root: "Claim"
entities:
  - "BillingCalculation"
  - "Charge"
  - "ContractApplication"
  - "GlosaCalculation"
value_objects:
  - "CalculationType"
  - "CalculationAmount"
  - "CalculationStatus"
domain_events:
  - name: "CalculationCompensated"
    payload: ["calculationId", "claimId", "calculationType", "restoredAmount"]
  - name: "ClaimValuesRestored"
    payload: ["claimId", "previousAmount", "restoredAmount"]
  - name: "CacheCleared"
    payload: ["calculationId", "cacheType"]
microservice_candidate:
  service_name: "billing-calculation-service"
  api_style: "Event-Driven + REST"
  bounded_context_isolation: "HIGH"
```

---

## 🏛️ Conformidade Regulatória

```yaml
tiss_standards:
  - "TISS 4.0 - Guia de Consulta (Componente 1) - cálculos de honorários"
  - "TISS 4.0 - Guia SP/SADT (Componente 2) - cálculos de procedimentos"
  - "TISS 4.0 - Resumo de Internação (Componente 3) - cálculos de diárias e taxas"

ans_requirements:
  - "RN 395/2016 - Art. 5º - Valores devem estar conforme tabelas TISS"
  - "RN 442/2018 - Art. 8º - Cálculos devem ser rastreáveis e auditáveis"
  - "RN 465/2021 - Art. 10º - Valores contestados devem ter histórico"

lgpd_considerations:
  - "Art. 6º, III - Princípio da Necessidade: armazenar apenas cálculos necessários"
  - "Art. 16 - Dados devem ser corrigidos quando detectados erros de cálculo"

sox_controls:
  - "Controle de Alteração de Valores: mudanças em valores devem ser auditadas"
  - "Controle de Aprovação: recálculos de valores altos requerem aprovação"
  - "Controle de Reconciliação: valores calculados vs valores faturados"

audit_trail:
  - "Retention: 5 anos (ANS) + prazo prescricional"
  - "Logging: Todos os cálculos e compensações com valores originais e finais"
  - "Versioning: manter histórico de todas as versões de cálculo"
```

---

## 🚀 Notas para Migração

```yaml
camunda_7_to_8:
  complexity_rating: 7/10
  migration_path: "Delegate → Job Worker + Zeebe Client"
  breaking_changes:
    - "DelegateExecution → JobClient + ActivatedJob"
    - "Switch-case lógica: pode ser convertida em DMN decision table"
    - "Cache management: migrar para Redis distribuído"

  dmn_candidate:
    decision_table: "calculation-compensation-strategy"
    inputs: ["calculationType"]
    outputs: ["compensationStrategy", "notificationTarget"]
    rules: |
      | calculationType | compensationStrategy      | notificationTarget   |
      |-----------------|---------------------------|----------------------|
      | "CONTRACT"      | "contractCompensation"    | "pricing-team"       |
      | "GLOSA"         | "glosaCompensation"       | "glosa-management"   |
      | "BILLING"       | "billingCompensation"     | "billing-operations" |
      | *               | "genericCompensation"     | "system-admin"       |

microservices_target: "billing-calculation-service"
alternative_orchestration: "Saga pattern with Kafka + CQRS for calculation history"

temporal_alternative: |
  @WorkflowMethod
  void billingCalculationSaga(CalculationInput input) {
    try {
      calculateBilling(input);
    } catch (Exception e) {
      Saga.compensate(() ->
        activities.compensateCalculation(input.getCalculationId())
      );
    }
  }

performance_considerations:
  - "Compensação deve completar em < 1 segundo (P95)"
  - "Cache invalidation: usar Redis PUBLISH para invalidar cache distribuído"
  - "Considerar async compensation para operações não-críticas"
  - "Batch deletion de registros para melhorar performance"
```

---

## 📍 Rastreabilidade

```yaml
source_file: "src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateCalculateDelegate.java"
source_class: "CompensateCalculateDelegate"
source_package: "com.hospital.revenuecycle.delegates.compensation"

key_methods:
  - name: "executeBusinessLogic"
    lines: 50-82
    rules: ["RN-COMP-CALC-001"]

  - name: "compensateCalculation"
    lines: 87-121
    rules: ["RN-COMP-CALC-001", "RN-COMP-CALC-007"]

  - name: "compensateContractCalculation"
    lines: 126-145
    rules: ["RN-COMP-CALC-002"]

  - name: "compensateGlosaCalculation"
    lines: 150-167
    rules: ["RN-COMP-CALC-003"]

  - name: "compensateBillingCalculation"
    lines: 172-189
    rules: ["RN-COMP-CALC-004"]

  - name: "performGenericCompensation"
    lines: 194-201
    rules: ["RN-COMP-CALC-005"]

  - name: "performCommonCompensation"
    lines: 206-224
    rules: ["RN-COMP-CALC-006"]

  - name: "requiresIdempotency"
    lines: 241-243
    rules: ["RN-COMP-CALC-007"]

dependencies:
  - "SagaCompensationService (via @Autowired)"
  - "BaseDelegate (extends)"
  - "Camunda BPM Engine (DelegateExecution)"

integration_points:
  - "Database: billing_calculations, charges, claims, contract_applications, glosa_calculations, billing_summaries, pricing_cache, calculation_cache tables"
  - "Kafka: topic 'billing-compensations'"
  - "Pricing service (implied)"
  - "Glosa management service (implied)"
```

---

## 🔗 Dependências e Relacionamentos

### Delegates/Serviços que Este Componente Depende
- **BaseDelegate** - Classe base
- **SagaCompensationService** - Coordenação de saga

### Delegates/Serviços que Dependem Deste Componente
- **Processo BPMN de Cálculo de Faturamento** - Invoca em falhas
- **BillingConsolidationService** - Usa para reverter consolidações

---

## 📊 Métricas Técnicas

```yaml
cyclomatic_complexity: 10
cognitive_complexity: 15
lines_of_code: 244
test_coverage_current: "80%"
test_coverage_target: "95%"

performance_sla:
  p50_latency_ms: 120
  p95_latency_ms: 500
  p99_latency_ms: 900
  timeout_threshold_ms: 5000

dependencies_count: 2
integration_points_count: 4
database_tables_affected: 8
```

---

## 📝 Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0.0 | 2026-01-12 | Hive Mind Coder Agent | Extração completa de regras de negócio com schema v2 |

---

## 🏷️ Tags e Classificação

`compensação` `saga-pattern` `cálculos` `faturamento` `regras-contratuais` `glosas` `consolidação` `idempotência` `camunda-7` `tiss` `ans`
