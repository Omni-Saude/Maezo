# Regras de Negócio - AutoMatchingDelegate

**Arquivo:** `AutoMatchingDelegate.java`
**Domínio:** Collection (Cobrança)
**Processo BPMN:** Payment Reconciliation
**Versão:** 2.0.0
**Data:** Análise de Código

---

## Visão Geral

Delegate responsável por conciliar automaticamente pagamentos recebidos com faturas abertas usando algoritmos inteligentes de matching (casamento exato, parcial ou múltiplo).

---

## Regras de Negócio Identificadas

### RN-AUT-001: Tolerância de Casamento
**Prioridade:** ALTA
**Tipo:** Configuração
**Descrição:** Sistema aceita diferença de até R$ 0,01 (1 centavo) para considerar valores como iguais.
**Implementação:**
```java
// Linha 36 (constante)
private static final BigDecimal MATCH_TOLERANCE = new BigDecimal("0.01"); // 1 cent tolerance
```
**Aplicação:** Usado em casamentos exatos e múltiplos
**Justificativa:** Compensar arredondamentos e diferenças de centavos

---

### RN-AUT-002: Estratégia 1 - Casamento Exato
**Prioridade:** ALTA
**Tipo:** Matching
**Descrição:** Primeira tentativa: buscar fatura com valor igual ao pagamento (tolerância de R$ 0,01).
**Implementação:**
```java
// Linha 99-113
private MatchResult findExactMatch(BigDecimal paymentAmount, List<Map<String, Object>> openInvoices) {
    for (Map<String, Object> invoice : openInvoices) {
        BigDecimal invoiceAmount = new BigDecimal(invoice.get("amount").toString());
        BigDecimal difference = paymentAmount.subtract(invoiceAmount).abs();

        if (difference.compareTo(MATCH_TOLERANCE) <= 0) {
            return new MatchResult(
                true,
                List.of((String) invoice.get("invoice_id")),
                BigDecimal.ZERO,
                "exact"
            );
        }
    }
    return new MatchResult(false, Collections.emptyList(), paymentAmount, "none");
}
```
**Condição:** |`paymentAmount` - `invoiceAmount`| <= R$ 0,01
**Saída:**
- `matchType` = "exact"
- `matchedInvoiceIds` = [invoice_id]
- `remainingBalance` = R$ 0,00

---

### RN-AUT-003: Estratégia 2 - Casamento Parcial
**Prioridade:** MÉDIA
**Tipo:** Matching
**Descrição:** Se não há casamento exato, buscar maior fatura que possa receber pagamento parcial.
**Implementação:**
```java
// Linha 119-141
private MatchResult findPartialMatch(BigDecimal paymentAmount, List<Map<String, Object>> openInvoices) {
    // Find largest invoice that payment can partially cover
    Map<String, Object> bestMatch = openInvoices.stream()
        .filter(inv -> {
            BigDecimal invAmount = new BigDecimal(inv.get("amount").toString());
            return paymentAmount.compareTo(invAmount) < 0;
        })
        .max(Comparator.comparing(inv -> new BigDecimal(inv.get("amount").toString())))
        .orElse(null);

    if (bestMatch != null) {
        BigDecimal invoiceAmount = new BigDecimal(bestMatch.get("amount").toString());
        BigDecimal remaining = invoiceAmount.subtract(paymentAmount);

        return new MatchResult(
            true,
            List.of((String) bestMatch.get("invoice_id")),
            remaining,
            "partial"
        );
    }

    return new MatchResult(false, Collections.emptyList(), paymentAmount, "none");
}
```
**Condição:** `paymentAmount` < `invoiceAmount`
**Seleção:** Maior fatura que atende condição
**Saída:**
- `matchType` = "partial"
- `matchedInvoiceIds` = [invoice_id]
- `remainingBalance` = `invoiceAmount` - `paymentAmount`

---

### RN-AUT-004: Estratégia 3 - Múltiplas Faturas
**Prioridade:** MÉDIA
**Tipo:** Matching
**Descrição:** Se não há casamento exato ou parcial, distribuir pagamento entre múltiplas faturas (mais antigas primeiro).
**Implementação:**
```java
// Linha 147-186
private MatchResult findMultipleInvoiceMatch(BigDecimal paymentAmount, List<Map<String, Object>> openInvoices) {
    // Sort invoices by date (oldest first)
    List<Map<String, Object>> sortedInvoices = openInvoices.stream()
        .sorted(Comparator.comparing(inv ->
            LocalDateTime.parse(inv.getOrDefault("created_at", LocalDateTime.now().toString()).toString())
        ))
        .collect(Collectors.toList());

    List<String> matchedInvoiceIds = new ArrayList<>();
    BigDecimal remainingPayment = paymentAmount;

    for (Map<String, Object> invoice : sortedInvoices) {
        if (remainingPayment.compareTo(MATCH_TOLERANCE) <= 0) {
            break; // Payment fully allocated
        }

        BigDecimal invoiceAmount = new BigDecimal(invoice.get("amount").toString());

        if (remainingPayment.compareTo(invoiceAmount) >= 0) {
            // Full invoice payment
            matchedInvoiceIds.add((String) invoice.get("invoice_id"));
            remainingPayment = remainingPayment.subtract(invoiceAmount);
        } else {
            // Partial payment on this invoice
            matchedInvoiceIds.add((String) invoice.get("invoice_id"));
            remainingPayment = BigDecimal.ZERO;
            break;
        }
    }

    if (!matchedInvoiceIds.isEmpty()) {
        return new MatchResult(
            true,
            matchedInvoiceIds,
            remainingPayment,
            "multiple"
        );
    }

    return new MatchResult(false, Collections.emptyList(), paymentAmount, "none");
}
```
**Ordenação:** Por data de criação (mais antigas primeiro)
**Alocação:**
1. Paga faturas completas enquanto possível
2. Última fatura pode receber pagamento parcial
3. Para quando pagamento <= R$ 0,01

**Saída:**
- `matchType` = "multiple"
- `matchedInvoiceIds` = [invoice_id1, invoice_id2, ...]
- `remainingBalance` = saldo não alocado

---

### RN-AUT-005: Priorização FIFO
**Prioridade:** MÉDIA
**Tipo:** Regra de Negócio
**Descrição:** Em casamentos múltiplos, aplicar pagamento às faturas mais antigas primeiro (FIFO - First In, First Out).
**Implementação:**
```java
// Linha 149-153
List<Map<String, Object>> sortedInvoices = openInvoices.stream()
    .sorted(Comparator.comparing(inv ->
        LocalDateTime.parse(inv.getOrDefault("created_at", LocalDateTime.now().toString()).toString())
    ))
    .collect(Collectors.toList());
```
**Justificativa:** Reduzir antiguidade de dívidas

---

### RN-AUT-006: Criação de Registro de Conciliação
**Prioridade:** MÉDIA
**Tipo:** Auditoria
**Descrição:** Quando há match bem-sucedido, criar registro de conciliação com detalhes completos.
**Implementação:**
```java
// Linha 192-212
private void createReconciliationRecord(DelegateExecution execution,
                                       Map<String, Object> payment,
                                       MatchResult matchResult) {
    Map<String, Object> reconciliation = new HashMap<>();
    reconciliation.put("reconciliation_id", UUID.randomUUID().toString());
    reconciliation.put("payment_amount", payment.get("amount"));
    reconciliation.put("payment_date", payment.get("date"));
    reconciliation.put("payer_name", payment.get("payer_name"));
    reconciliation.put("matched_invoice_ids", matchResult.getMatchedInvoiceIds());
    reconciliation.put("match_type", matchResult.getMatchType());
    reconciliation.put("remaining_balance", matchResult.getRemainingBalance());
    reconciliation.put("reconciled_at", LocalDateTime.now().toString());
    reconciliation.put("reconciled_by", "auto_matching_system");

    ObjectValue reconciliationValue = Variables.objectValue(reconciliation)
        .serializationDataFormat(Variables.SerializationDataFormats.JSON)
        .create();
    execution.setVariable("reconciliationRecord", reconciliationValue);

    log.info("Reconciliation record created: {}", reconciliation.get("reconciliation_id"));
}
```
**Campos do Registro:**
- `reconciliation_id`: UUID único
- `payment_amount`: Valor do pagamento
- `payment_date`: Data do pagamento
- `payer_name`: Nome do pagador
- `matched_invoice_ids`: Faturas casadas
- `match_type`: Tipo de casamento
- `remaining_balance`: Saldo restante
- `reconciled_at`: Timestamp
- `reconciled_by`: "auto_matching_system"

---

### RN-AUT-007: Validação de Parâmetros Obrigatórios
**Prioridade:** ALTA
**Tipo:** Validação
**Descrição:** Pagamento e lista de faturas abertas são obrigatórios.
**Implementação:**
```java
// Linha 46-50
if (receivedPayment == null || openInvoices == null || openInvoices.isEmpty()) {
    log.warn("Missing required parameters for auto-matching");
    execution.setVariable("matchFound", false);
    return;
}
```
**Entrada:** `receivedPayment`, `openInvoices`
**Saída:** `matchFound` = false se ausentes

---

### RN-AUT-008: Parada por Alocação Completa
**Prioridade:** MÉDIA
**Tipo:** Otimização
**Descrição:** Em matching múltiplo, parar alocação quando saldo <= R$ 0,01.
**Implementação:**
```java
// Linha 159-161
if (remainingPayment.compareTo(MATCH_TOLERANCE) <= 0) {
    break; // Payment fully allocated
}
```
**Justificativa:** Evitar alocações de centavos residuais

---

## Tipos de Casamento (Match Types)

| Tipo | Descrição | Condição | Saldo Restante |
|------|-----------|----------|----------------|
| `exact` | Casamento exato | \|payment - invoice\| <= R$ 0,01 | R$ 0,00 |
| `partial` | Pagamento parcial | payment < invoice | invoice - payment |
| `multiple` | Múltiplas faturas | payment distribuído | >= R$ 0,00 |
| `none` | Sem casamento | Nenhuma estratégia funcionou | payment |

---

## Ordem de Prioridade de Estratégias

1. **Exact Match** (RN-AUT-002) - Tenta primeiro
2. **Partial Match** (RN-AUT-003) - Se exact falhar
3. **Multiple Invoice Match** (RN-AUT-004) - Se partial falhar

---

## Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `receivedPayment` | Map<String, Object> | Sim | Pagamento recebido com amount, date, payer_name |
| `openInvoices` | List<Map<String, Object>> | Sim | Lista de faturas abertas com invoice_id, amount, created_at |

---

## Estrutura de `receivedPayment`

```json
{
  "amount": 1500.00,
  "date": "2026-01-12T10:30:00",
  "payer_name": "Unimed"
}
```

---

## Estrutura de `openInvoices`

```json
[
  {
    "invoice_id": "INV-001",
    "amount": 1000.00,
    "patient_id": "PAT-123",
    "created_at": "2026-01-01T08:00:00"
  },
  {
    "invoice_id": "INV-002",
    "amount": 500.00,
    "patient_id": "PAT-123",
    "created_at": "2026-01-05T14:30:00"
  }
]
```

---

## Variáveis de Saída

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `matchFound` | Boolean | Se foi encontrado casamento |
| `matchedInvoiceIds` | List<String> | Lista de IDs de faturas casadas |
| `remainingBalance` | BigDecimal | Saldo restante após casamento |
| `matchType` | String | Tipo de casamento: exact, partial, multiple, none |
| `reconciliationRecord` | ObjectValue | Registro completo de conciliação (se matched) |

---

## Dependências

- **ADR:** ADR-003 BPMN Implementation Standards
- **Processo:** Payment Reconciliation Process

---

## Notas de Implementação

1. **FIFO Logic:** Estratégia múltipla usa FIFO (First In, First Out) para reduzir antiguidade de contas a receber.
2. **Tolerance Handling:** Tolerância de R$ 0,01 compensa diferenças de arredondamento comuns em sistemas financeiros.
3. **Audit Trail:** Registro de conciliação permite rastreamento completo de como pagamentos foram aplicados.
4. **Idempotência:** Implementação deve prevenir aplicação duplicada de mesmo pagamento.
5. **Production Enhancement:** Em produção, considerar casamento por outros critérios (número da guia, paciente, etc).

---

## XI. Conformidade Regulatória

### 11.1 Requisitos ANS (Agência Nacional de Saúde Suplementar)
- **RN 395/2016**: Submissão eletrônica de contas médicas com rastreabilidade de pagamentos
- **RN 388/2015**: Garantia de serviço mínimo - reconciliação em até 48h para pagamentos urgentes
- **RN 442/2018**: Padrões de qualidade assistencial - auditoria de casamentos de pagamentos

### 11.2 Conformidade TISS (Troca de Informações em Saúde Suplementar)
- **TISS 4.01**: Estrutura de dados para transações financeiras e reconciliações
- **TISS Componente Organizacional**: Padrões de registro de pagamentos e faturas

### 11.3 LGPD (Lei Geral de Proteção de Dados)
- **Art. 11 LGPD**: Processamento de dados de saúde - registro de transações financeiras
- **Art. 46 LGPD**: Anonimização de dados em relatórios agregados de pagamentos
- **Retenção**: 5 anos para registros financeiros (requisito SOX/ANS)

### 11.4 Trilha de Auditoria
- **Registro obrigatório**: Todas as tentativas de casamento (exato, parcial, múltiplo)
- **Armazenamento**: Log estruturado com timestamp, IDs de faturas, valores e tipo de match
- **Rastreabilidade**: UUID único para cada registro de reconciliação
- **Período de retenção**: 5 anos (documentos fiscais) + 2 anos (documentos auxiliares)

---

## XII. Notas de Migração - Camunda 7 para Camunda 8

### 12.1 Camunda 8 - Alternativa Recomendada
- **Padrão**: External Task Worker com Zeebe
- **Implementação**: Job Worker dedicado para reconciliação de pagamentos
- **Vantagens**: Escalabilidade horizontal, retry automático, backpressure handling

### 12.2 Nível de Complexidade
- **Complexidade de Migração**: BAIXA-MÉDIA (2-5 dias)
- **Justificativa**: Lógica de negócio independente, poucos side-effects, stateless

### 12.3 Breaking Changes
- **JavaDelegate → Job Worker**: Refatoração completa para padrão async
- **Sincronização**: Mudança de execução síncrona para assíncrona com callbacks
- **Variáveis**: Migração para Zeebe variable propagation model
- **Idempotência**: Já implementada - facilita migração

### 12.4 Considerações Técnicas
- **External Task Pattern**: Requer fila de mensagens (Kafka/RabbitMQ) para comunicação
- **Error Handling**: Migração de BpmnError para Zeebe incident handling
- **Testing**: Necessidade de testes de integração com Zeebe Test Container

---

## XIII. Mapeamento DDD (Domain-Driven Design)

### 13.1 Bounded Context
- **Contexto Delimitado**: `Payment Reconciliation & Collection`
- **Linguagem Ubíqua**: Reconciliation, matching, invoice, payment, FIFO allocation

### 13.2 Aggregate Root
- **Aggregate**: `PaymentReconciliation`
- **Entidades relacionadas**:
  - `Invoice` (fatura a receber)
  - `Payment` (pagamento recebido)
  - `MatchingRule` (regra de casamento)

### 13.3 Domain Events
- **PaymentMatched**: Pagamento casado com sucesso (exato/parcial/múltiplo)
- **ReconciliationCompleted**: Registro de reconciliação criado e persistido
- **NoMatchFound**: Nenhum casamento encontrado para o pagamento

### 13.4 Value Objects
- `MatchType` (exact, partial, multiple, none)
- `Money` (valor monetário com precisão decimal)
- `ReconciliationRecord` (registro imutável de reconciliação)

### 13.5 Candidato a Microserviço
- **Serviço**: `payment-reconciliation-service`
- **Responsabilidades**: Casamento automático, gestão de faturas abertas, FIFO allocation
- **Integrações**: Accounts Receivable Service, Payment Gateway, ERP Financeiro

---

## XIV. Metadados Técnicos

### 14.1 Características
- **Tipo**: Service Delegate (Camunda 7 JavaDelegate)
- **Execução**: Síncrona (blocking)
- **Idempotência**: Habilitada (requer IdempotencyService)
- **Transacional**: Sim (requer gerenciamento de transação)

### 14.2 Métricas de Qualidade
- **Complexidade Ciclomática**: MÉDIA (3 estratégias de matching + validações)
- **Cobertura de Testes Recomendada**: 90% (lógica crítica de negócio)
- **Tempo de Execução Esperado**: < 2s (para até 100 faturas abertas)

### 14.3 Impacto de Performance
- **I/O**: MEDIUM (consultas ao banco para faturas abertas)
- **CPU**: LOW (algoritmos simples de comparação)
- **Memória**: LOW (processamento em memória de listas pequenas)

### 14.4 Dependências de Runtime
- Spring Framework (DI)
- Camunda BPM Engine 7.x
- IdempotencyService (custom)
- SLF4J (logging)

---

## X. Conformidade Regulatória

### 10.1 Requisitos ANS (Agência Nacional de Saúde Suplementar)
- **RN 395/2016**: Submissão eletrônica de contas médicas - reconciliação de pagamentos rastreável
- **RN 388/2015**: Padrões TISS - matching de guias com demonstrativos de retorno
- **RN 442/2018**: Padrões de qualidade - auditoria de reconciliações

### 10.2 Conformidade TISS (Troca de Informações em Saúde Suplementar)
- **TISS 4.01**: Estrutura de dados de pagamentos e demonstrativos
- **Demonstrativo de Retorno**: Parsing de valores pagos e identificação de guias

### 10.3 LGPD (Lei Geral de Proteção de Dados)
- **Art. 11 LGPD**: Dados de saúde - finalidade legítima (reconciliação financeira)
- **Art. 46 LGPD**: Anonimização de dados em relatórios agregados
- **Retenção**: 5 anos para registros de reconciliação (requisito ANS/SOX)

### 10.4 Trilha de Auditoria
- **Registro obrigatório**: Todas tentativas de matching (exato, parcial, múltiplo)
- **Armazenamento**: Log estruturado com timestamp, payment_id, invoice_ids, match_type
- **Rastreabilidade**: UUID único para cada registro de reconciliação
- **Período de retenção**: 5 anos (documentos fiscais) + 2 anos (auxiliares)

---

## XI. Notas de Migração - Camunda 7 para Camunda 8

### 11.1 Camunda 8 - Alternativa Recomendada
- **Padrão**: External Task Worker com Zeebe
- **Implementação**: Job Worker dedicado para reconciliação automática
- **Vantagens**: Escalabilidade horizontal, retry automático, tolerância a falhas

### 11.2 Nível de Complexidade
- **Complexidade de Migração**: BAIXA-MÉDIA (2-5 dias)
- **Justificativa**: Lógica independente, stateless, poucos side-effects

### 11.3 Breaking Changes
- **JavaDelegate → Job Worker**: Refatoração para padrão async worker
- **Sincronização**: De execução síncrona para assíncrona com callbacks
- **Variáveis**: Migração para Zeebe variable propagation model
- **Idempotência**: Já implementada facilita migração (critical)

### 11.4 Considerações Técnicas
- **External Task Pattern**: Requer fila de mensagens (Kafka/RabbitMQ)
- **Error Handling**: Migração de BpmnError para Zeebe incident handling
- **Testing**: Necessidade de Zeebe Test Container para testes de integração
- **Performance**: Matching assíncrono permite processamento em lote

---

## XII. Mapeamento DDD (Domain-Driven Design)

### 12.1 Bounded Context
- **Contexto Delimitado**: `Payment Reconciliation & Collection`
- **Linguagem Ubíqua**: Reconciliation, matching, invoice, payment, FIFO allocation, tolerance

### 12.2 Aggregate Root
- **Aggregate**: `PaymentReconciliation`
- **Entidades relacionadas**:
  - `Invoice` (fatura a receber)
  - `Payment` (pagamento recebido)
  - `MatchingRule` (regra de casamento - exact/partial/multiple)

### 12.3 Domain Events
- **PaymentMatched**: Pagamento casado com sucesso (tipo: exact/partial/multiple)
- **ReconciliationCompleted**: Registro de reconciliação criado e persistido
- **NoMatchFound**: Nenhum casamento encontrado - encaminhar para revisão manual
- **PartialMatchDetected**: Pagamento parcial identificado - requer investigação

### 12.4 Value Objects
- `MatchType` (exact, partial, multiple, none)
- `Money` (valor monetário com precisão BigDecimal)
- `ReconciliationRecord` (registro imutável de reconciliação)
- `MatchTolerance` (R$ 0.01 - tolerance value object)

### 12.5 Candidato a Microserviço
- **Serviço**: `payment-reconciliation-service`
- **Responsabilidades**:
  - Casamento automático de pagamentos
  - Gestão de faturas abertas
  - Alocação FIFO
  - Geração de registros de auditoria
- **Integrações**:
  - Accounts Receivable Service
  - Payment Gateway
  - ERP Financeiro (TASY)
  - Notification Service (alertas de mismatch)

---

## XIII. Metadados Técnicos

### 13.1 Características
- **Tipo**: Service Delegate (Camunda 7 JavaDelegate)
- **Execução**: Síncrona (blocking)
- **Idempotência**: Habilitada (requer IdempotencyService)
- **Transacional**: Sim (requer gerenciamento de transação)

### 13.2 Métricas de Qualidade
- **Complexidade Ciclomática**: MÉDIA (3 estratégias matching + validações)
- **Cobertura de Testes Recomendada**: 90% (lógica crítica financeira)
- **Tempo de Execução Esperado**: < 2s (para até 100 faturas abertas)

### 13.3 Impacto de Performance
- **I/O**: MEDIUM (consultas ao banco para faturas abertas)
- **CPU**: LOW (algoritmos simples de comparação e subtração)
- **Memória**: LOW (processamento em memória de listas pequenas)

### 13.4 Dependências de Runtime
- Spring Framework (Dependency Injection)
- Camunda BPM Engine 7.x
- IdempotencyService (custom - ADR-007)
- SLF4J (logging)
- BigDecimal (precisão monetária)

### 13.5 Otimizações Recomendadas
- **Indexação**: Índice em invoice.amount e invoice.created_at
- **Caching**: Cache de faturas abertas (TTL 5min)
- **Batch Processing**: Processar múltiplos pagamentos em lote
- **Machine Learning**: Aprender padrões de matching bem-sucedidos

---

**Gerado automaticamente em:** 2026-01-12
**Fonte:** Análise de código Camunda 7
**Schema Compliance Fix:** 2026-01-12
