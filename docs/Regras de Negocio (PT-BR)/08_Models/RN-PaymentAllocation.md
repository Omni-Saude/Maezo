# RN-PaymentAllocation - Modelo de Alocação de Pagamentos

**Arquivo:** `src/main/java/com/hospital/revenuecycle/domain/collection/PaymentAllocation.java`

**Tipo:** Domain Model - Gestão de Pagamentos

**Versão:** 1.0

---

## 1. VISÃO GERAL

### 1.1 Descrição
Modelo de domínio que gerencia a alocação de pagamentos recebidos através de múltiplas faturas e cobranças. Suporta estratégias de alocação flexíveis e rastreamento de valores não alocados.

### 1.2 Propósito
- Alocar pagamentos recebidos para faturas específicas
- Gerenciar múltiplas alocações de um único pagamento
- Rastrear valores não alocados (underpayment)
- Suportar diferentes estratégias de alocação

---

## 2. ESTRUTURA DE DADOS

### 2.1 Atributos Principais
```java
public class PaymentAllocation {
    String allocationId;           // ID único da alocação
    String paymentId;              // ID do pagamento
    BigDecimal paymentAmount;      // Valor total do pagamento
    LocalDateTime paymentDate;     // Data do pagamento
    String payerId;                // ID do pagador
    String payerType;              // Tipo: INSURANCE, PATIENT, GOVERNMENT
    String allocationStrategy;     // Estratégia: FIFO, OLDEST_FIRST, MANUAL
    List<Allocation> allocations;  // Lista de alocações individuais
    BigDecimal totalAllocated;     // Total alocado
    BigDecimal unallocatedAmount;  // Valor não alocado
    LocalDateTime allocationTimestamp;
    String allocatedById;          // Usuário que alocou
    String allocationStatus;       // Status: PENDING, COMPLETED, REVERSED
    String reversalReason;         // Motivo de reversão
    Map<String, Object> metadata;
}
```

### 2.2 Classe Interna: Allocation
```java
public static class Allocation {
    String invoiceId;              // ID da fatura
    String chargeId;               // ID da cobrança específica
    BigDecimal allocatedAmount;    // Valor alocado
    String allocationType;         // Tipo: PRINCIPAL, INTEREST, FEE
    String allocationNote;         // Observações
}
```

---

## 3. REGRAS DE NEGÓCIO

### RN-PAYALLOC-001: Validação de Alocação Total
**Descrição:** O sistema deve validar que a soma das alocações não excede o valor do pagamento.

**Critérios:**
- `totalAllocated + unallocatedAmount = paymentAmount`
- Rejeitar alocações que excedem o saldo disponível
- Permitir subalocação com rastreamento de valores não alocados

**Implementação:**
```java
public boolean isValid() {
    if (paymentAmount == null || totalAllocated == null) {
        return false;
    }
    BigDecimal sum = totalAllocated.add(
        unallocatedAmount != null ? unallocatedAmount : BigDecimal.ZERO
    );
    return sum.compareTo(paymentAmount) == 0;
}
```

### RN-PAYALLOC-002: Verificação de Alocação Completa
**Descrição:** O sistema deve identificar se o pagamento foi totalmente alocado.

**Critérios:**
- `unallocatedAmount = 0` indica alocação completa
- Pagamentos parcialmente alocados devem ser rastreáveis
- Status deve refletir estado de alocação

**Implementação:**
```java
public boolean isFullyAllocated() {
    if (unallocatedAmount == null) {
        return false;
    }
    return unallocatedAmount.compareTo(BigDecimal.ZERO) == 0;
}
```

### RN-PAYALLOC-003: Contagem de Faturas Afetadas
**Descrição:** O sistema deve contar quantas faturas distintas são afetadas pela alocação.

**Critérios:**
- Contar invoiceIds distintos na lista de allocations
- Utilizar para analytics e relatórios
- Suportar pagamentos multi-fatura

**Implementação:**
```java
public long countAffectedInvoices() {
    if (allocations == null) {
        return 0;
    }
    return allocations.stream()
        .map(Allocation::getInvoiceId)
        .distinct()
        .count();
}
```

---

## 4. ESTRATÉGIAS DE ALOCAÇÃO

### 4.1 FIFO (First In, First Out)
**Descrição:** Aloca pagamento para faturas mais antigas primeiro

**Critérios:**
- Ordenar faturas por data de emissão
- Alocar valores sequencialmente
- Minimizar juros e multas

### 4.2 OLDEST_FIRST (Mais Antigas Primeiro)
**Descrição:** Prioriza faturas vencidas há mais tempo

**Critérios:**
- Ordenar por data de vencimento
- Priorizar contas com maior atraso
- Reduzir risco de perda

### 4.3 MANUAL (Alocação Manual)
**Descrição:** Permite alocação manual pelo operador

**Critérios:**
- Usuário especifica distribuição
- Suporta alocações customizadas
- Requer aprovação adicional

### 4.4 PROPORTIONAL (Proporcional)
**Descrição:** Distribui pagamento proporcionalmente entre faturas

**Critérios:**
- Calcular proporção de cada fatura
- Alocar valores proporcionalmente
- Útil para pagamentos parciais

---

## 5. TIPOS DE ALOCAÇÃO

### 5.1 PRINCIPAL
**Descrição:** Alocação para valor principal da fatura

### 5.2 INTEREST
**Descrição:** Alocação para juros acumulados

### 5.3 FEE
**Descrição:** Alocação para taxas administrativas

### 5.4 PENALTY
**Descrição:** Alocação para multas por atraso

---

## 6. ESTADOS DE ALOCAÇÃO

### 6.1 PENDING
**Descrição:** Alocação criada mas não confirmada
- Permite edição
- Não afeta saldo de faturas
- Aguarda validação

### 6.2 COMPLETED
**Descrição:** Alocação confirmada e aplicada
- Atualiza saldo de faturas
- Gera movimentações financeiras
- Irrevogável sem compensação

### 6.3 REVERSED
**Descrição:** Alocação revertida
- Restaura saldo original
- Requer motivo documentado
- Gera histórico de auditoria

---

## 7. CENÁRIOS DE USO

### 7.1 Pagamento Completo de Fatura Única
```java
PaymentAllocation allocation = PaymentAllocation.builder()
    .paymentId("PAY-001")
    .paymentAmount(new BigDecimal("1000.00"))
    .allocations(List.of(
        Allocation.builder()
            .invoiceId("INV-001")
            .allocatedAmount(new BigDecimal("1000.00"))
            .allocationType("PRINCIPAL")
            .build()
    ))
    .totalAllocated(new BigDecimal("1000.00"))
    .unallocatedAmount(BigDecimal.ZERO)
    .build();
```

### 7.2 Pagamento Parcial com Múltiplas Faturas
```java
PaymentAllocation allocation = PaymentAllocation.builder()
    .paymentId("PAY-002")
    .paymentAmount(new BigDecimal("1500.00"))
    .allocations(List.of(
        Allocation.builder()
            .invoiceId("INV-001")
            .allocatedAmount(new BigDecimal("1000.00"))
            .allocationType("PRINCIPAL")
            .build(),
        Allocation.builder()
            .invoiceId("INV-002")
            .allocatedAmount(new BigDecimal("500.00"))
            .allocationType("PRINCIPAL")
            .build()
    ))
    .totalAllocated(new BigDecimal("1500.00"))
    .unallocatedAmount(BigDecimal.ZERO)
    .build();
```

### 7.3 Underpayment (Pagamento Inferior)
```java
PaymentAllocation allocation = PaymentAllocation.builder()
    .paymentId("PAY-003")
    .paymentAmount(new BigDecimal("800.00"))
    .allocations(List.of(
        Allocation.builder()
            .invoiceId("INV-001")
            .allocatedAmount(new BigDecimal("800.00"))
            .allocationType("PRINCIPAL")
            .build()
    ))
    .totalAllocated(new BigDecimal("800.00"))
    .unallocatedAmount(BigDecimal.ZERO)
    .build();

// Fatura INV-001 ainda tem saldo pendente de 200.00
```

---

## 8. INTEGRAÇÕES

### 8.1 Sistema Financeiro
- **Operação:** Registro de alocações
- **Impacto:** Atualização de saldos de faturas
- **Método:** Event-driven (Kafka)

### 8.2 Sistema de Cobrança
- **Operação:** Atualização de status de cobrança
- **Impacto:** Marcação de faturas pagas/parcialmente pagas
- **Método:** API REST

### 8.3 Sistema de Contabilidade
- **Operação:** Lançamento contábil
- **Impacto:** Débito/Crédito de contas contábeis
- **Método:** Batch processing

---

## 9. VALIDAÇÕES

### 9.1 Validações Obrigatórias
- paymentId não pode ser nulo
- paymentAmount deve ser positivo
- totalAllocated não pode exceder paymentAmount
- allocations não pode ser lista vazia para status COMPLETED

### 9.2 Validações de Consistência
- Soma de allocatedAmount deve igualar totalAllocated
- unallocatedAmount deve ser não-negativo
- Faturas referenciadas devem existir

---

## 10. AUDITORIA

### 10.1 Campos de Rastreamento
- `allocatedById`: Usuário que criou a alocação
- `allocationTimestamp`: Data/hora da alocação
- `reversalReason`: Motivo de reversão (se aplicável)

### 10.2 Logs de Auditoria
- Criação de alocação
- Modificação de alocação
- Reversão de alocação
- Mudanças de status

---

## 11. MÉTRICAS

### 11.1 KPIs Suportados
- Taxa de alocação automática vs manual
- Tempo médio de alocação
- Volume de underpayments
- Taxa de reversões

### 11.2 Relatórios
- Alocações por período
- Alocações por estratégia
- Alocações por tipo de pagador
- Faturas com múltiplas alocações

---

## 12. CONFORMIDADE

### 12.1 LGPD/GDPR
- Dados de pagador devem ser protegidos
- Anonimização em relatórios quando necessário
- Retenção de dados conforme política

### 12.2 SOX/Auditoria Financeira
- Histórico completo de alocações
- Rastreabilidade de modificações
- Evidências de aprovações

---

**Data de Criação:** 2026-01-12
**Autor:** Hive Mind Swarm - Coder Agent
**Revisão:** v1.0
