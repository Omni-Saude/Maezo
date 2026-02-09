# RN-PaymentRepository

## Identificação
- **ID**: RN-PaymentRepository
- **Nome**: Repositório de Pagamentos
- **Versão**: 1.0
- **Autor**: Revenue Cycle Development Team
- **Tipo**: Repository Interface / Data Access

## Descrição
Interface de repositório para operações de acesso a dados de pagamentos usadas em cálculos de KPIs de cobrança e eficiência operacional.

## Contexto de Negócio
Fornece queries para métricas operacionais:
- **Collection Efficiency**: Eficiência de cobrança
- **Cost to Collect**: Custo operacional de cobrança
- **Payment Analysis**: Análise de recebimentos

## Métodos

### sumPayments
```java
double sumPayments(LocalDate startDate, LocalDate endDate)
```

**Retorno**: Total de pagamentos recebidos no período

**Uso**: Numerador para collection efficiency

**Query Esperada**:
```sql
SELECT SUM(payment_amount) FROM payments 
WHERE payment_date BETWEEN :startDate AND :endDate
```

### sumCollectionCosts
```java
double sumCollectionCosts(LocalDate startDate, LocalDate endDate)
```

**Retorno**: Total de custos operacionais de cobrança

**Definição**: Custos incluem:
- Tempo de staff
- Custos de sistema
- Agências de cobrança externas
- Postagem e comunicações

**Uso**: Cálculo de Cost to Collect

**Query Esperada**:
```sql
SELECT SUM(collection_cost) FROM collection_activities 
WHERE activity_date BETWEEN :startDate AND :endDate
```

## Integração com KPIs

### Collection Efficiency
```java
double paymentsReceived = paymentRepository.sumPayments(startDate, endDate);
double totalCharges = invoiceRepository.sumTotalCharges(startDate, endDate);
double collectionEfficiency = (paymentsReceived / totalCharges) * 100;
// Target: > 95%
```

### Cost to Collect
```java
double collectionCosts = paymentRepository.sumCollectionCosts(startDate, endDate);
double paymentsReceived = paymentRepository.sumPayments(startDate, endDate);
double costToCollect = (collectionCosts / paymentsReceived) * 100;
// Target: < 5%
```

## Campos de Dados Esperados

### Payment Entity
- `payment_id`: ID único
- `invoice_id`: FK para fatura
- `payment_date`: Data do recebimento
- `payment_amount`: Valor recebido
- `payment_method`: Método (cartão, boleto, transferência)

### Collection Activity Entity
- `activity_id`: ID único
- `invoice_id`: FK para fatura
- `activity_date`: Data da atividade
- `collection_cost`: Custo da atividade
- `activity_type`: Tipo (ligação, carta, agência)

## Índices Recomendados

```sql
CREATE INDEX idx_payments_date ON payments(payment_date);
CREATE INDEX idx_payments_amount ON payments(payment_amount, payment_date);
CREATE INDEX idx_collection_costs_date ON collection_activities(activity_date);
CREATE INDEX idx_collection_costs_invoice ON collection_activities(invoice_id, activity_date);
```

## Métricas de Performance

### Payment Velocity
```sql
SELECT 
  AVG(DATEDIFF(payment_date, invoice_date)) as avg_days_to_payment
FROM payments p
JOIN invoices i ON p.invoice_id = i.invoice_id
WHERE p.payment_date BETWEEN :startDate AND :endDate
```

### Collection Cost by Method
```sql
SELECT 
  activity_type,
  SUM(collection_cost) as total_cost,
  COUNT(*) as activity_count
FROM collection_activities
WHERE activity_date BETWEEN :startDate AND :endDate
GROUP BY activity_type
```

## Referências
- [RN-CalculateKPIs](../03_Servicos/RN-014-CalculateKPIs.md)
- [ClaimRepository](RN-ClaimRepository.md)
- [InvoiceRepository](RN-InvoiceRepository.md)

## Histórico de Alterações
| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-09 | Revenue Cycle Team | Criação inicial |
