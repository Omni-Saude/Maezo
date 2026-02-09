# Regras de Negócio: CompensateAllocationDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateAllocationDelegate.java`
> **Pacote:** `com.hospital.revenuecycle.delegates.compensation`
> **Categoria:** Delegate de Compensação (Padrão Saga - Cobrança)
> **Gerado em:** 2026-01-12T12:25:00Z
> **Versão do Documento:** 1.0.0

---

## 📋 Sumário Executivo

| Métrica | Valor |
|---------|-------|
| Total de Regras | 10 |
| Regras de Validação | 2 |
| Regras de Compensação | 8 |
| Complexidade Geral | MUITO ALTA |
| Criticidade de Negócio | CRÍTICA |

---

## 🎯 Contexto e Propósito

Este delegate implementa a lógica de compensação para alocação de pagamentos no ciclo de cobrança hospitalar. Quando uma alocação de pagamento falha (por inconsistências, erros de sistema ou decisões de negócio), todas as operações de alocação devem ser revertidas para manter a integridade financeira e contábil.

A compensação de alocações é crítica pois envolve reconciliação de pagamentos com faturas, saldos de contas a receber, lançamentos contábeis e integração com ERP. Erros nesta compensação podem causar descasamento financeiro entre sistemas e perda de controle sobre recebíveis.

---

## 📜 Catálogo de Regras

### RN-COMP-ALLOC-001: Reversão Completa de Alocação de Pagamento

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-001"
rule_name: "Reversão Completa de Alocação de Pagamento"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "COMPENSAÇÃO"
complexity: "MUITO_ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "98%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Reverte todas as operações relacionadas à alocação de um pagamento às faturas correspondentes, restaurando saldos e cancelando lançamentos contábeis.

**Contexto de Negócio:** No processo de cobrança, quando um pagamento da operadora é recebido, ele é alocado (matching) às faturas pendentes. Se este processo falha após alocação parcial, é necessário reverter completamente para evitar que faturas fiquem marcadas como pagas indevidamente ou que o pagamento seja alocado duas vezes.

**Objetivo:** Garantir integridade financeira revertendo alocações, restaurando saldos não alocados de pagamentos, e cancelando quaisquer lançamentos contábeis criados.

#### 🔧 Especificação

**Pré-condições:**
- Alocação de pagamento foi iniciada (allocationId existe)
- Pagamento existe e possui valores alocados
- Faturas envolvidas na alocação são identificadas
- Sistema possui registro de valores originais

**Lógica da Regra:**

```
SE alocação de pagamento falhou OU requer reversão
ENTÃO
  1. Deletar registros de alocação (tabela payment_allocations)
  2. Restaurar valor não alocado do pagamento
     pagamento.unallocated_amount += allocatedAmount
  3. Reverter valores alocados nas faturas
     PARA CADA fatura em invoiceIds:
       fatura.allocated_amount -= valor_alocado_para_esta_fatura
       SE fatura.allocated_amount = 0 ENTÃO
         fatura.status = "PENDING"
       FIM SE
     FIM PARA CADA
  4. Cancelar registros de matching automático
  5. Atualizar saldos de contas a receber (AR)
  6. Criar lançamentos contábeis de reversão
  7. Notificar controladores financeiros
  8. Registrar em trilha de auditoria
  9. Retornar valor revertido
SENÃO
  Nenhuma ação necessária
FIM SE
```

**Fórmula:**
```
unallocated_amount_new = unallocated_amount_old + allocatedAmount

PARA CADA fatura:
  allocated_amount_new = allocated_amount_old - (allocatedAmount * peso_da_fatura)

  peso_da_fatura = fatura.outstanding_amount / soma_todas_faturas_outstanding
```

**Pós-condições:**
- Registros de alocação deletados
- Saldo não alocado do pagamento restaurado
- Faturas retornam ao status "PENDING" se não possuem mais alocação
- Lançamentos contábeis de reversão criados
- Notificações enviadas

**Exceções:**
| Condição | Exceção | Tratamento |
|----------|---------|------------|
| allocationId não existe | RuntimeException | Falha na compensação, escalar para reconciliação manual |
| Pagamento já foi compensado | IdempotencyException | Log warning, retornar sucesso (idempotente) |
| Fatura já foi liquidada | BusinessRuleException | Reverter manualmente, notificar controller |
| Falha em lançamento contábil | AccountingException | Rollback completo, alertar financeiro |

#### 📊 Parâmetros

| Parâmetro | Tipo | Descrição | Restrições | Exemplo |
|-----------|------|-----------|------------|---------|
| allocationId | Identificador Único | Identificador da alocação a compensar | Obrigatório, formato UUID | "al123-abc" |
| paymentId | Identificador Único | Identificador do pagamento | Obrigatório | "pay456-def" |
| allocatedAmount | Decimal | Valor total alocado a reverter | Obrigatório, > 0 | 15000.00 |
| invoiceIds | Lista de Identificadores | IDs das faturas envolvidas | Opcional, pode ser vazio | ["inv1", "inv2"] |

**Saídas:**
| Variável | Tipo | Descrição | Exemplo |
|----------|------|-----------|---------|
| compensationCompleted | Booleano | Indica sucesso da compensação | true |
| reversedAmount | Decimal | Valor total revertido | 15000.00 |
| compensationTimestamp | Data/Hora | Momento da compensação | "2026-01-12T14:30:00Z" |
| unallocatedBalance | Decimal | Novo saldo não alocado | 15000.00 |

---

### RN-COMP-ALLOC-002: Deleção de Registros de Alocação

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-002"
rule_name: "Deleção de Registros de Alocação"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "ROTEAMENTO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Remove todos os registros de alocação da tabela `payment_allocations` para o allocationId especificado.

**Especificação:**

```
EXECUTAR comando SQL:
  DELETE FROM payment_allocations
  WHERE allocation_id = allocationId

VERIFICAR:
  SE linhas_afetadas = 0 ENTÃO
    LOG warning "Nenhuma alocação encontrada para deletar"
  SENÃO
    LOG info "Deletados {linhas_afetadas} registros de alocação"
  FIM SE
```

---

### RN-COMP-ALLOC-003: Restauração de Saldo Não Alocado

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-003"
rule_name: "Restauração de Valor Não Alocado do Pagamento"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "CÁLCULO"
complexity: "MÉDIA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Incrementa o valor não alocado (unallocated_amount) do pagamento com o valor que estava alocado.

**Contexto de Negócio:** Quando um pagamento é recebido da operadora, ele possui um valor total. À medida que é alocado às faturas, o `unallocated_amount` diminui. Ao reverter, devemos restaurar este saldo.

**Especificação:**

```
EXECUTAR comando SQL:
  UPDATE payments
  SET unallocated_amount = unallocated_amount + allocatedAmount,
      last_modified = AGORA
  WHERE payment_id = paymentId

VALIDAR:
  SE unallocated_amount_new > total_amount ENTÃO
    LANÇAR exceção "Saldo não alocado não pode exceder valor total do pagamento"
  FIM SE
```

**Fórmula:**
```
unallocated_amount_new = unallocated_amount_old + allocatedAmount

Invariante: unallocated_amount ≤ total_amount
```

---

### RN-COMP-ALLOC-004: Reversão de Valores Alocados em Faturas

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-004"
rule_name: "Reversão de Valores Alocados nas Faturas"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "CÁLCULO"
complexity: "MÉDIA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "MEDIUM"
```

#### 📖 Descrição

**Resumo:** Reduz o campo `allocated_amount` das faturas envolvidas, revertendo os valores que foram alocados.

**Especificação:**

```
PARA CADA invoice_id EM invoiceIds:
  EXECUTAR SQL:
    UPDATE invoices
    SET allocated_amount = allocated_amount - valor_alocado_para_invoice,
        status = CASE
          WHEN allocated_amount - valor_alocado_para_invoice = 0
          THEN 'PENDING'
          ELSE status
        END
    WHERE invoice_id = invoice_id

ATENÇÃO:
  Se fatura estava "PAID" e após reversão fica "PENDING",
  gerar alerta para controller financeiro
FIM PARA CADA
```

---

### RN-COMP-ALLOC-005: Cancelamento de Matching Automático

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-005"
rule_name: "Cancelamento de Registros de Matching Automático"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "ROTEAMENTO"
complexity: "BAIXA"
criticality: "MÉDIA"
test_coverage_recommendation: "90%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Remove registros da tabela `automatic_matching` que foram criados por algoritmos de matching automático (ex: matching por número de fatura, matching por valor).

**Especificação:**

```
EXECUTAR SQL:
  DELETE FROM automatic_matching
  WHERE allocation_id = allocationId

LOG informações sobre matching cancelado
```

---

### RN-COMP-ALLOC-006: Atualização de Contas a Receber

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-006"
rule_name: "Atualização de Saldos de Contas a Receber"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "CÁLCULO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Atualiza os saldos agregados de contas a receber (AR - Accounts Receivable) para refletir a reversão da alocação.

**Contexto de Negócio:** O sistema mantém saldos agregados de AR por operadora, especialidade, período, etc. Esses saldos devem ser atualizados quando alocações são revertidas.

**Especificação:**

```
PARA CADA fatura EM invoiceIds:
  payer_id = fatura.payer_id
  specialty = fatura.specialty
  period = fatura.billing_period

  EXECUTAR SQL:
    UPDATE accounts_receivable_summary
    SET outstanding_balance = outstanding_balance + valor_revertido_fatura,
        allocated_balance = allocated_balance - valor_revertido_fatura,
        last_updated = AGORA
    WHERE payer_id = payer_id
      AND specialty = specialty
      AND period = period
FIM PARA CADA
```

---

### RN-COMP-ALLOC-007: Criação de Lançamentos Contábeis de Reversão

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-007"
rule_name: "Lançamentos Contábeis de Reversão de Alocação"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "CÁLCULO"
complexity: "ALTA"
criticality: "CRÍTICA"
test_coverage_recommendation: "95%"
performance_impact: "HIGH"
```

#### 📖 Descrição

**Resumo:** Cria lançamentos contábeis para reverter os efeitos financeiros da alocação de pagamento.

**Contexto de Negócio:** Quando um pagamento é alocado a faturas, lançamentos contábeis são criados (Débito: Caixa/Banco, Crédito: Contas a Receber). Na reversão, esses lançamentos devem ser estornados.

**Especificação:**

```
CRIAR lançamento contábil de reversão:
  Débito: Contas a Receber (Ativo Circulante) - Valor: allocatedAmount
  Crédito: Caixa/Bancos (Ativo Circulante) - Valor: allocatedAmount

  Metadados do lançamento:
    - data: data_compensação
    - referência: "REV-ALLOC-{allocationId}"
    - descrição: "Reversão de alocação de pagamento {paymentId}"
    - tipo: "REVERSAL"
    - allocation_id: allocationId
    - payment_id: paymentId

INVOCAR AccountingIntegrationService.postJournalEntry(lançamento)

ATENÇÃO:
  Se ERP retornar erro, toda a compensação deve falhar (transação distribuída)
```

---

### RN-COMP-ALLOC-008: Notificação de Controladores Financeiros

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-008"
rule_name: "Notificação de Reversão de Alocação"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "NOTIFICAÇÃO"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "85%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Envia notificações aos controladores financeiros sobre a reversão de alocação para ação manual se necessário.

**Especificação:**

```
ENVIAR notificação VIA Kafka:
  TÓPICO: "payment-allocations-reversed"
  PAYLOAD: {
    allocationId: identificador_alocação,
    paymentId: identificador_pagamento,
    reversedAmount: valor_revertido,
    invoiceIds: lista_faturas_afetadas,
    reversedAt: data_hora_reversão,
    notificationType: "ALLOCATION_REVERSED"
  }

ENVIAR email PARA:
  - Controller Financeiro
  - Gestor de Contas a Receber
  - Analista de Reconciliação (se valor > R$ 10.000)
```

---

### RN-COMP-ALLOC-009: Registro em Trilha de Auditoria

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-009"
rule_name: "Registro de Compensação em Auditoria"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "AUDITORIA"
complexity: "BAIXA"
criticality: "ALTA"
test_coverage_recommendation: "95%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Registra todas as operações de compensação de alocação em trilha de auditoria para rastreabilidade e conformidade.

**Especificação:**

```
INSERIR em trilha_auditoria_alocação:
  allocation_id: identificador_alocação
  payment_id: identificador_pagamento
  ação: "COMPENSATED"
  reversed_amount: valor_revertido
  invoice_ids: lista_faturas
  usuário: usuário_ou_sistema_executor
  timestamp: data_hora_ação
  motivo: motivo_compensação

GARANTIR retenção: 7 anos (conformidade SOX + ANS)
```

---

### RN-COMP-ALLOC-010: Idempotência de Compensação de Alocação

#### 📝 Metadados

```yaml
rule_id: "RN-COMP-ALLOC-010"
rule_name: "Garantia de Idempotência em Compensação de Alocação"
version: "1.0.0"
last_updated: "2026-01-12T12:25:00Z"
category: "VALIDAÇÃO"
complexity: "MÉDIA"
criticality: "CRÍTICA"
test_coverage_recommendation: "98%"
performance_impact: "LOW"
```

#### 📖 Descrição

**Resumo:** Garante que múltiplas execuções da compensação de alocação produzam o mesmo resultado, evitando reversões duplicadas.

**Contexto de Negócio:** Em operações financeiras, reversões duplicadas podem causar descasamento de saldos, faturas pagas marcadas como pendentes, e inconsistências contábeis graves.

**Especificação:**

```
ANTES de executar compensação:
  VERIFICAR se compensação já foi executada:
    SELECT compensation_completed
    FROM saga_compensation_log
    WHERE transaction_id = processInstanceId
      AND operation = "allocate_payment"

  SE compensation_completed = true
  ENTÃO
    LOG "Compensação de alocação já executada anteriormente"
    RETORNAR sucesso (operação idempotente)
  SENÃO
    EXECUTAR compensação
    MARCAR compensation_completed = true
  FIM SE
```

---

## 🗺️ Mapeamento de Domínio

```yaml
bounded_context: "Collection"
aggregate_root: "Payment"
entities:
  - "PaymentAllocation"
  - "Invoice"
  - "AccountsReceivable"
value_objects:
  - "AllocationAmount"
  - "InvoiceStatus"
  - "PaymentStatus"
domain_events:
  - name: "PaymentAllocationCompensated"
    payload: ["allocationId", "paymentId", "reversedAmount", "invoiceIds"]
  - name: "InvoiceStatusReverted"
    payload: ["invoiceIds", "previousStatus", "newStatus"]
  - name: "AccountsReceivableAdjusted"
    payload: ["payerId", "adjustmentAmount", "reason"]
microservice_candidate:
  service_name: "payment-allocation-service"
  api_style: "Event-Driven + REST"
  bounded_context_isolation: "VERY_HIGH"
```

---

## 🏛️ Conformidade Regulatória

```yaml
tiss_standards:
  - "TISS 4.0 - Demonstrativo de Pagamento (Componente 30)"
  - "TISS 4.0 - Reconciliação de Contas (Componente 31)"

ans_requirements:
  - "RN 395/2016 - Art. 14º - Demonstrativo de pagamento deve ser rastreável"
  - "RN 442/2018 - Art. 10º - Prazo de 30 dias para pagamento após aprovação"
  - "RN 465/2021 - Art. 18º - Transparência em glosas e pagamentos"

lgpd_considerations:
  - "Art. 6º, IV - Princípio da Segurança: operações financeiras devem ter controles de reversão"
  - "Art. 46 - Obrigação de manter logs de operações financeiras sensíveis"

sox_controls:
  - "Controle de Segregação de Funções: alocação e compensação não podem ser executadas pela mesma pessoa"
  - "Controle de Aprovação: compensações de valores altos requerem aprovação do controller"
  - "Controle de Auditoria: trilha completa de todas as operações financeiras"
  - "Controle de Reconciliação: saldos de AR devem ser reconciliados diariamente"

audit_trail:
  - "Retention: 7 anos (SOX) + 5 anos (ANS) = 7 anos"
  - "Logging: Todas as compensações de alocação com timestamp, valor, faturas e motivo"
  - "Immutability: Trilha de auditoria em append-only log (S3 + blockchain hash)"
```

---

## 🚀 Notas para Migração

```yaml
camunda_7_to_8:
  complexity_rating: 8/10
  migration_path: "Delegate → Job Worker + Zeebe Client"
  breaking_changes:
    - "DelegateExecution → JobClient + ActivatedJob"
    - "Transações distribuídas: usar Zeebe variables + job completion"
    - "Idempotência: implementar em banco de dados externo (não mais em memória)"

  example_camunda_8:
    worker_type: "compensate-allocation"
    handler: |
      @JobWorker(type = "compensate-allocation")
      public void handle(JobClient client, ActivatedJob job) {
        Map<String, Object> variables = job.getVariablesAsMap();
        String allocationId = (String) variables.get("allocationId");

        // Check idempotency
        if (isAlreadyCompensated(allocationId)) {
          client.newCompleteCommand(job.getKey()).send();
          return;
        }

        // Execute compensation
        Double reversedAmount = compensateAllocation(variables);

        client.newCompleteCommand(job.getKey())
          .variables(Map.of(
            "compensationCompleted", true,
            "reversedAmount", reversedAmount
          ))
          .send();
      }

microservices_target: "payment-allocation-service"
alternative_orchestration: "Saga pattern with Kafka + Outbox pattern (recommended)"
data_migration:
  - "payment_allocations table: migrate to event sourcing"
  - "Audit trail: migrate to immutable append-only store"
  - "Compensation log: migrate to distributed log (Kafka Streams)"

temporal_alternative: |
  // Temporal Saga with compensation
  Saga saga = new Saga(new Saga.Options.Builder()
    .setParallelCompensation(false)
    .build());

  try {
    saga.addCompensation(() ->
      activities.compensateAllocation(allocationId, paymentId, amount)
    );
    // Execute main workflow
  } catch (Exception e) {
    saga.compensate();
  }

performance_considerations:
  - "Compensação deve completar em < 2 segundos (P95)"
  - "Operações SQL: usar transações ACID com isolation level SERIALIZABLE"
  - "Considerar sharding de payment_allocations por payer_id"
  - "Cache de saldos de AR para reduzir queries"
  - "Notificações assíncronas para não bloquear compensação"
```

---

## 📍 Rastreabilidade

```yaml
source_file: "src/main/java/com/hospital/revenuecycle/delegates/compensation/CompensateAllocationDelegate.java"
source_class: "CompensateAllocationDelegate"
source_package: "com.hospital.revenuecycle.delegates.compensation"

key_methods:
  - name: "executeBusinessLogic"
    lines: 50-84
    rules: ["RN-COMP-ALLOC-001"]

  - name: "compensateAllocation"
    lines: 89-128
    rules: ["RN-COMP-ALLOC-002", "RN-COMP-ALLOC-003", "RN-COMP-ALLOC-004", "RN-COMP-ALLOC-005", "RN-COMP-ALLOC-006", "RN-COMP-ALLOC-007", "RN-COMP-ALLOC-008", "RN-COMP-ALLOC-009"]

  - name: "requiresIdempotency"
    lines: 185-187
    rules: ["RN-COMP-ALLOC-010"]

dependencies:
  - "SagaCompensationService (via @Autowired)"
  - "BaseDelegate (extends)"
  - "Camunda BPM Engine (DelegateExecution)"

integration_points:
  - "Database: payment_allocations, payments, invoices, accounts_receivable_summary, automatic_matching tables"
  - "AccountingIntegrationService: journal entry posting"
  - "Kafka: topic 'payment-allocations-reversed'"
  - "Email service: financial controller notifications"
```

---

## 🔗 Dependências e Relacionamentos

### Delegates/Serviços que Este Componente Depende
- **BaseDelegate** - Classe base com operações comuns
- **SagaCompensationService** - Coordenação de compensações distribuídas
- **AccountingIntegrationService** (implícito) - Integração com ERP/contabilidade

### Delegates/Serviços que Dependem Deste Componente
- **Processo BPMN de Alocação de Pagamentos** - Invoca em caso de falha
- **PaymentReconciliationService** - Usa lógica de reversão para reconciliação

---

## 📊 Métricas Técnicas

```yaml
cyclomatic_complexity: 12
cognitive_complexity: 18
lines_of_code: 189
test_coverage_current: "82%"
test_coverage_target: "98%"

performance_sla:
  p50_latency_ms: 250
  p95_latency_ms: 800
  p99_latency_ms: 1500
  timeout_threshold_ms: 5000

dependencies_count: 3
integration_points_count: 5
database_tables_affected: 5
```

---

## 📝 Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0.0 | 2026-01-12 | Hive Mind Coder Agent | Extração completa de regras de negócio com schema v2 |

---

## 🏷️ Tags e Classificação

`compensação` `saga-pattern` `alocação-pagamentos` `cobrança` `contas-a-receber` `reconciliação` `idempotência` `sox` `camunda-7`
