# RN-AllocatePaymentDelegate - Alocação de Pagamentos de Pacientes

## Metadados
- **ID**: RN-AllocatePaymentDelegate
- **Categoria**: Cobrança (SUB_09_Collections)
- **Prioridade**: HIGH
- **Versão**: 1.0
- **Autor**: Revenue Cycle Development Team
- **Data Criação**: 2026-01-09
- **Última Atualização**: 2026-01-12
- **Status**: Ativo

## Referência de Implementação
- **Arquivo**: `/src/main/java/com/hospital/revenuecycle/delegates/collection/AllocatePaymentDelegate.java`
- **Bean BPMN**: `allocatePaymentDelegate`
- **Service Layer**: `PaymentAllocationService`

---

## Descrição Geral

O **AllocatePaymentDelegate** implementa a lógica de alocação inteligente de pagamentos de pacientes entre múltiplas faturas pendentes. Este delegate aplica diferentes estratégias de alocação para distribuir o valor recebido de forma otimizada.

**Contexto de Negócio:**
- Pacientes frequentemente fazem pagamentos parciais que precisam ser distribuídos entre várias faturas
- Diferentes estratégias de alocação afetam o aging de contas e a gestão de recebíveis
- A alocação correta é crítica para compliance financeiro e auditoria

---

## Regras de Negócio

### RN-ALC-001: Estratégias de Alocação
**Descrição:** O sistema suporta 4 estratégias distintas de alocação de pagamentos:
- **FIFO (First In, First Out)**: Prioriza faturas mais antigas primeiro (padrão)
- **LIFO (Last In, First Out)**: Prioriza faturas mais recentes primeiro
- **PROPORTIONAL**: Distribui proporcionalmente entre todas as faturas
- **HIGHEST_BALANCE**: Prioriza faturas com maior saldo devedor

**Justificativa:** Diferentes estratégias atendem diferentes objetivos de gestão financeira

**Fórmula (PROPORTIONAL):**
```
alocacao_fatura_i = (saldo_fatura_i / saldo_total) * valor_pagamento
```

**Exemplo:**
```
Faturas: FAT-001 ($1000), FAT-002 ($500), FAT-003 ($1500)
Pagamento: $600
Estratégia: PROPORTIONAL

Total: $3000
FAT-001: (1000/3000) * 600 = $200
FAT-002: (500/3000) * 600 = $100
FAT-003: (1500/3000) * 600 = $300
```

---

### RN-ALC-002: Validação de Valor de Pagamento
**Descrição:** O valor do pagamento deve ser maior que zero.

**Condições:**
- `payment_amount > 0`

**BPMN Error:** `INVALID_PAYMENT_AMOUNT` - "Payment amount must be greater than zero"

**Implementação:**
```java
if (paymentAmount.compareTo(BigDecimal.ZERO) <= 0) {
    throw new BpmnError("INVALID_PAYMENT_AMOUNT",
        "Payment amount must be greater than zero");
}
```

---

### RN-ALC-003: Validação de Faturas Pendentes
**Descrição:** Deve existir pelo menos uma fatura pendente para alocação.

**Condições:**
- `outstanding_invoices NOT NULL`
- `outstanding_invoices.size() > 0`

**BPMN Error:** `NO_OUTSTANDING_INVOICES` - "No outstanding invoices to allocate payment to"

**Implementação:**
```java
if (invoicesData == null || invoicesData.isEmpty()) {
    throw new BpmnError("NO_OUTSTANDING_INVOICES",
        "No outstanding invoices to allocate payment to");
}
```

---

### RN-ALC-004: Cálculo de Saldo Remanescente
**Descrição:** Para cada fatura, calcular o saldo remanescente após alocação.

**Fórmula:**
```
saldo_remanescente = saldo_original - valor_alocado
```

**Implementação:**
```java
Map<String, BigDecimal> remainingBalances = new HashMap<>();
for (InvoiceBalance invoice : invoices) {
    BigDecimal allocated = allocationDetails.getOrDefault(invoice.getInvoiceId(), BigDecimal.ZERO);
    BigDecimal remaining = invoice.getBalanceOwed().subtract(allocated);
    remainingBalances.put(invoice.getInvoiceId(), remaining);
}
```

---

### RN-ALC-005: Geração de Relatório de Alocação
**Descrição:** Gerar relatório detalhado da alocação para auditoria.

**Conteúdo do Relatório:**
- Estratégia utilizada
- Valor total do pagamento
- Valor total alocado
- Valor não aplicado (se houver)
- Detalhamento por fatura

**Formato:**
```
Payment Allocation Summary - Strategy: FIFO
Payment Amount: $600.00
Total Allocated: $600.00
Unapplied Amount: $0.00

Allocation Details:
  Invoice INV-001: $300.00
  Invoice INV-002: $300.00
```

---

### RN-ALC-006: Idempotência de Operação
**Descrição:** A operação de alocação é idempotente - múltiplas execuções com os mesmos parâmetros devem produzir o mesmo resultado.

**Implementação:**
```java
@Override
public boolean requiresIdempotency() {
    return true; // Inherited from BaseDelegate
}
```

---

## Variáveis do Processo BPMN

### Variáveis de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `payment_amount` | BigDecimal | Sim | Valor do pagamento a ser alocado |
| `patient_id` | String | Sim | Identificador do paciente |
| `outstanding_invoices` | List&lt;Map&gt; | Sim | Lista de faturas pendentes com campos: `invoice_id`, `balance_owed`, `invoice_date` |
| `allocation_strategy` | String | Não | Estratégia de alocação (padrão: "FIFO") |

**Exemplo de `outstanding_invoices`:**
```json
[
  {
    "invoice_id": "INV-001",
    "balance_owed": 1000.00,
    "invoice_date": "2025-11-15"
  },
  {
    "invoice_id": "INV-002",
    "balance_owed": 500.00,
    "invoice_date": "2025-12-20"
  }
]
```

### Variáveis de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `payment_allocated` | Boolean | Indica se a alocação foi bem-sucedida |
| `allocation_details` | Map&lt;String, BigDecimal&gt; | Mapa de invoice_id → valor alocado |
| `total_allocated` | BigDecimal | Valor total alocado |
| `remaining_balances` | Map&lt;String, BigDecimal&gt; | Saldo remanescente por fatura |
| `allocation_strategy_used` | String | Estratégia que foi utilizada |
| `allocation_date` | LocalDate | Data da alocação |
| `allocation_summary` | String | Relatório legível da alocação |

**Em caso de erro:**
| Variável | Tipo | Descrição |
|----------|------|-----------|
| `payment_allocated` | Boolean | `false` |
| `allocation_error` | String | Mensagem de erro técnico |

---

## Eventos de Erro BPMN

### INVALID_PAYMENT_AMOUNT
- **Quando:** Valor de pagamento é zero ou negativo
- **Mensagem:** "Payment amount must be greater than zero"
- **Ação Recomendada:** Validar entrada antes de iniciar processo

### NO_OUTSTANDING_INVOICES
- **Quando:** Nenhuma fatura pendente encontrada para o paciente
- **Mensagem:** "No outstanding invoices to allocate payment to"
- **Ação Recomendada:** Verificar se pagamento já foi totalmente aplicado

### ALLOCATION_FAILED
- **Quando:** Falha técnica no processo de alocação
- **Mensagem:** "Technical failure in payment allocation: {detalhes}"
- **Ação Recomendada:** Revisar logs e tentar novamente

---

## Integrações

### PaymentAllocationService
**Método:** `allocatePayment(BigDecimal paymentAmount, List<InvoiceBalance> invoices, AllocationStrategy strategy)`

**Responsabilidades:**
- Implementar algoritmos de alocação (FIFO, LIFO, Proportional, Highest Balance)
- Calcular distribuição de valores entre faturas
- Garantir que soma das alocações não exceda valor do pagamento

**Retorno:** `Map<String, BigDecimal>` (invoice_id → allocated_amount)

---

## Cenários de Teste

### CT-ALC-001: Alocação FIFO com Múltiplas Faturas
**Dado:**
- Pagamento de $800
- 3 faturas: INV-001 ($500, 2025-11-01), INV-002 ($300, 2025-11-15), INV-003 ($400, 2025-12-01)

**Quando:** Executar alocação com estratégia FIFO

**Então:**
- INV-001 recebe $500 (totalmente paga)
- INV-002 recebe $300 (totalmente paga)
- INV-003 recebe $0
- Total alocado: $800

---

### CT-ALC-002: Alocação Proporcional
**Dado:**
- Pagamento de $600
- 3 faturas: INV-001 ($1000), INV-002 ($500), INV-003 ($1500)

**Quando:** Executar alocação com estratégia PROPORTIONAL

**Então:**
- INV-001 recebe $200 (saldo remanescente: $800)
- INV-002 recebe $100 (saldo remanescente: $400)
- INV-003 recebe $300 (saldo remanescente: $1200)
- Total alocado: $600

---

### CT-ALC-003: Erro - Valor Inválido
**Dado:**
- Pagamento de $0
- 1 fatura pendente

**Quando:** Executar alocação

**Então:**
- BPMN Error `INVALID_PAYMENT_AMOUNT` é lançado
- Variável `payment_allocated` = false

---

### CT-ALC-004: Erro - Sem Faturas
**Dado:**
- Pagamento de $500
- Lista de faturas vazia

**Quando:** Executar alocação

**Então:**
- BPMN Error `NO_OUTSTANDING_INVOICES` é lançado
- Variável `payment_allocated` = false

---

## Métricas e KPIs

### Operacionais
- **Taxa de Sucesso de Alocação**: % de alocações concluídas com sucesso
- **Valor Médio Alocado**: Média do valor de pagamentos alocados
- **Distribuição por Estratégia**: % de uso de cada estratégia

### Performance
- **Tempo Médio de Alocação**: < 200ms
- **Latência P95**: < 500ms

### Auditoria
- **Total de Alocações por Dia**: Contagem diária
- **Valor Total Alocado**: Soma dos valores processados

---

## Considerações de Segurança

### Validação de Dados
- Validar tipos e ranges de todos os valores monetários
- Sanitizar invoice_ids antes de processar

### Auditoria
- Toda alocação deve gerar entrada em log de auditoria
- Relatório de alocação deve ser armazenado para compliance

### Integridade Financeira
- Garantir que soma das alocações não exceda valor do pagamento
- Prevenir double-posting através de idempotência

---

## Observações de Implementação

### Mapeamento de Dados
O delegate converte dados do formato Map para objetos `InvoiceBalance`:

```java
private InvoiceBalance mapToInvoiceBalance(Map<String, Object> data) {
    String invoiceId = (String) data.get("invoice_id");
    BigDecimal balanceOwed = data.get("balance_owed") instanceof BigDecimal ?
            (BigDecimal) data.get("balance_owed") :
            new BigDecimal(data.get("balance_owed").toString());

    Object dateObj = data.get("invoice_date");
    LocalDate invoiceDate = dateObj instanceof LocalDate ?
            (LocalDate) dateObj :
            LocalDate.parse(dateObj.toString());

    return InvoiceBalance.builder()
            .invoiceId(invoiceId)
            .balanceOwed(balanceOwed)
            .invoiceDate(invoiceDate)
            .build();
}
```

### Logging
Logging detalhado em todos os níveis:
- **INFO**: Início/fim de alocação, resultados
- **DEBUG**: Detalhes de conversão e cálculos intermediários
- **ERROR**: Falhas e exceções

---

## Referências
- Payment Posting Standards (Healthcare Financial Management Association)
- Revenue Cycle Best Practices Guide
- BPMN Process: SUB_09_Collections
- Service: PaymentAllocationService

---

## Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-09 | Revenue Cycle Team | Versão inicial com 4 estratégias de alocação |
