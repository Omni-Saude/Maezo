# RN-ClaimRepository

## Identificação
- **ID**: RN-ClaimRepository
- **Nome**: Repositório de Contas Médicas
- **Versão**: 1.0
- **Autor**: Revenue Cycle Development Team
- **Tipo**: Repository Interface / Data Access

## Descrição
Interface de repositório para operações de acesso a dados de contas médicas (claims) usadas em cálculos de KPIs do ciclo de receita.

## Contexto de Negócio
Fornece queries especializadas para métricas financeiras e operacionais:
- **Taxa de Negativas (Denial Rate)**: Claims negadas vs aprovadas
- **Taxa de Aprovação Primeiro Passe (First-Pass Approval Rate)**: Aprovações sem iteração
- **Volume de Contas**: Tracking de volume por período

## Métodos

### countByStatus
```java
long countByStatus(String status, LocalDate startDate, LocalDate endDate)
```

**Parâmetros**:
- `status`: Status da conta ("DENIED", "APPROVED", "PENDING")
- `startDate`: Início do período (inclusive)
- `endDate`: Fim do período (inclusive)

**Retorno**: Contagem de contas com o status especificado

**Uso em KPIs**:
- Cálculo de denial rate
- Análise de taxa de aprovação
- Tracking de contas pendentes

### countAll
```java
long countAll(LocalDate startDate, LocalDate endDate)
```

**Retorno**: Total de contas no período

**Uso**: Denominador para cálculos de taxa

### countByFirstPassApproval
```java
long countByFirstPassApproval(boolean firstPassApproval, LocalDate startDate, LocalDate endDate)
```

**Parâmetros**:
- `firstPassApproval`: true = aprovadas na primeira submissão

**Uso**: Cálculo de First-Pass Approval Rate (FPAR)

**Definição First-Pass**: Contas aprovadas sem:
- Rejeições anteriores
- Solicitações de informação adicional
- Correções necessárias

## Queries Esperadas (Implementação JPA)

```sql
-- countByStatus
SELECT COUNT(*) FROM claims 
WHERE status = :status 
  AND submission_date BETWEEN :startDate AND :endDate

-- countAll
SELECT COUNT(*) FROM claims 
WHERE submission_date BETWEEN :startDate AND :endDate

-- countByFirstPassApproval
SELECT COUNT(*) FROM claims 
WHERE first_pass_approved = :firstPassApproval 
  AND submission_date BETWEEN :startDate AND :endDate
```

## Integração com KPIs

### Denial Rate Calculation
```java
long deniedClaims = claimRepository.countByStatus("DENIED", startDate, endDate);
long totalClaims = claimRepository.countAll(startDate, endDate);
double denialRate = (double) deniedClaims / totalClaims * 100;
```

### First-Pass Approval Rate
```java
long firstPassApproved = claimRepository.countByFirstPassApproval(true, startDate, endDate);
long totalClaims = claimRepository.countAll(startDate, endDate);
double fpar = (double) firstPassApproved / totalClaims * 100;
```

## Índices Recomendados

```sql
CREATE INDEX idx_claims_status_date ON claims(status, submission_date);
CREATE INDEX idx_claims_first_pass ON claims(first_pass_approved, submission_date);
CREATE INDEX idx_claims_submission_date ON claims(submission_date);
```

## Referências
- [RN-CalculateKPIs](../03_Servicos/RN-014-CalculateKPIs.md)
- [InvoiceRepository](RN-InvoiceRepository.md)
- [PaymentRepository](RN-PaymentRepository.md)

## Histórico de Alterações
| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-09 | Revenue Cycle Team | Criação inicial |
