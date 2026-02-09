# RN-InvoiceRepository

## Identificação
- **ID**: RN-InvoiceRepository
- **Nome**: Repositório de Faturas
- **Versão**: 1.0
- **Autor**: Revenue Cycle Development Team
- **Tipo**: Repository Interface / Data Access

## Descrição
Interface de repositório para operações de acesso a dados de faturas (invoices) usadas em cálculos de KPIs financeiros do ciclo de receita.

## Contexto de Negócio
Fornece queries para métricas financeiras críticas:
- **A/R (Accounts Receivable)**: Valores a receber
- **Charge Lag**: Tempo entre atendimento e faturamento
- **Adjustments**: Ajustes contratuais

## Métodos

### sumOutstandingAmount
```java
double sumOutstandingAmount(LocalDate startDate, LocalDate endDate)
```

**Retorno**: Total de valores pendentes de pagamento

**Uso**: Cálculo de Days in A/R (contas a receber)

**Query Esperada**:
```sql
SELECT SUM(outstanding_amount) FROM invoices 
WHERE service_date BETWEEN :startDate AND :endDate
```

### sumTotalCharges
```java
double sumTotalCharges(LocalDate startDate, LocalDate endDate)
```

**Retorno**: Total de charges (valores cobrados)

**Uso**: Denominador para cálculos de taxa de ajuste

**Query Esperada**:
```sql
SELECT SUM(total_charges) FROM invoices 
WHERE service_date BETWEEN :startDate AND :endDate
```

### sumContractualAdjustments
```java
double sumContractualAdjustments(LocalDate startDate, LocalDate endDate)
```

**Retorno**: Total de ajustes contratuais

**Definição**: Diferença entre valores cobrados e valores contratuais com operadoras

**Uso**: Cálculo de Contractual Adjustment Rate

**Query Esperada**:
```sql
SELECT SUM(contractual_adjustments) FROM invoices 
WHERE service_date BETWEEN :startDate AND :endDate
```

### calculateAverageChargeLagDays
```java
double calculateAverageChargeLagDays(LocalDate startDate, LocalDate endDate)
```

**Retorno**: Média de dias entre serviço e faturamento

**Definição**: Eficiência do billing (quanto mais rápido, melhor)

**Query Esperada**:
```sql
SELECT AVG(DATEDIFF(charge_entry_date, service_date)) 
FROM invoices 
WHERE service_date BETWEEN :startDate AND :endDate
```

## Integração com KPIs

### Days in A/R Calculation
```java
double outstandingAmount = invoiceRepository.sumOutstandingAmount(startDate, endDate);
double totalCharges = invoiceRepository.sumTotalCharges(startDate, endDate);
double avgDailyCharges = totalCharges / daysBetween(startDate, endDate);
double daysInAR = outstandingAmount / avgDailyCharges;
```

### Contractual Adjustment Rate
```java
double adjustments = invoiceRepository.sumContractualAdjustments(startDate, endDate);
double charges = invoiceRepository.sumTotalCharges(startDate, endDate);
double adjustmentRate = (adjustments / charges) * 100;
```

### Charge Lag Analysis
```java
double avgChargeLag = invoiceRepository.calculateAverageChargeLagDays(startDate, endDate);
// Target: < 2 days
```

## Campos de Dados Esperados

### Invoice Entity
- `invoice_id`: ID único
- `service_date`: Data do atendimento
- `charge_entry_date`: Data de entrada da cobrança
- `total_charges`: Valor total cobrado
- `contractual_adjustments`: Ajustes contratuais
- `outstanding_amount`: Valor pendente de pagamento

## Índices Recomendados

```sql
CREATE INDEX idx_invoices_service_date ON invoices(service_date);
CREATE INDEX idx_invoices_outstanding ON invoices(outstanding_amount, service_date);
CREATE INDEX idx_invoices_charges ON invoices(total_charges, service_date);
CREATE INDEX idx_invoices_charge_lag ON invoices(service_date, charge_entry_date);
```

## Referências
- [RN-CalculateKPIs](../03_Servicos/RN-014-CalculateKPIs.md)
- [ClaimRepository](RN-ClaimRepository.md)
- [PaymentRepository](RN-PaymentRepository.md)

## Histórico de Alterações
| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-09 | Revenue Cycle Team | Criação inicial |
