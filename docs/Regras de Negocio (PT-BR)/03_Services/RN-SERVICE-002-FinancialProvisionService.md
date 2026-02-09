# RN-FinancialProvisionService - Gestão de Provisões Contábeis

**Caminho:** `src/main/java/com/hospital/revenuecycle/service/glosa/FinancialProvisionService.java`

---

## I. Resumo Executivo

### Descrição Geral
FinancialProvisionService implementa cálculo e gestão de provisões contábeis para valores glosados conforme CPC 25 (Provision para Contingências). Gerencia ciclo completo: criação, ajuste, reversão (recuperação) e baixa (perda).

### Criticidade do Negócio
- **Conformidade Contábil:** CPC 25, IFRS 15 (reconhecimento de receita)
- **Integridade Financeira:** Garante provisionamento correto de glosas no balanço
- **Auditoria:** Rastreamento de todas as operações de provisão
- **Reporte Executivo:** KPIs de cobertura de glosas dependem de provisões

### Dependências Críticas
```
FinancialProvisionService
├── TasyClient (registro em ERP, atualização)
├── GlosaAnalysisService (probabilidade recuperação)
└── AccountingClient (integração contábil)
```

---

## II. Decisões Arquiteturais

### Padrões Implementados

#### Cálculo CPC 25
```java
// Provisão = Valor Glosado × (1 - Probabilidade Recuperação)
BigDecimal unrecoverableProbability = BigDecimal.ONE.subtract(BigDecimal.valueOf(recoveryProbability));
return deniedAmount.multiply(unrecoverableProbability).setScale(2, RoundingMode.HALF_UP);
```

**Rationale:** Alinha-se com normas contábeis - provisiona pelo valor esperado não-recuperável.

#### Classificação de Provisão
```java
public enum ProvisionType {
    MINIMAL,    // < 40% do valor (recovery >= 60%)
    PARTIAL,    // 40-80% do valor (recovery 20-60%)
    FULL        // > 80% do valor (recovery < 20%)
}
```

**Rationale:** Facilita análise de risco (baixa/média/alta).

#### Lançamentos Contábeis (Plano de Contas)
```java
GL_PROVISION_EXPENSE = "3.1.2.01.001"       // Despesa com Provisão (P&L)
GL_PROVISION_LIABILITY = "2.1.3.01.001"     // Provisão para Glosas (Balanço)
GL_RECOVERY_REVENUE = "3.2.1.01.005"        // Receita Recuperação (P&L)
GL_WRITE_OFF = "3.1.2.01.002"               // Perda com Glosa (P&L)
```

**Rationale:** Separação clara: despesa (criar), receita (recuperação), perda (write-off).

---

## III. Regras de Negócio Identificadas

### RN-PROV-01: Criação de Provisão

```java
public ProvisionResult createProvision(
    String claimId,
    BigDecimal deniedAmount,
    double recoveryProbability,
    String denialCategory)
```

**Lógica Passo-a-Passo:**

1. **Calcula Valor da Provisão**
   - Fórmula: `Provisão = Valor Glosado × (1 - Probabilidade Recuperação)`
   - Exemplo: R$10.000 × (1 - 0.60) = R$4.000

2. **Determina Tipo de Provisão**
   - recovery >= 60%: MINIMAL (provisiona <40%)
   - recovery 20-60%: PARTIAL (provisiona 40-80%)
   - recovery < 20%: FULL (provisiona >80%)

3. **Gera Lançamentos Contábeis**
   ```
   DEBIT:  3.1.2.01.001 (Despesa com Provisão)     R$4.000
   CREDIT: 2.1.3.01.001 (Provisão para Glosas)     R$4.000
   ```

4. **Registra em TASY**
   - Cria registro de provisão no ERP
   - Vincula ao claim original
   - Armazena histórico de lançamentos

5. **Retorna ProvisionResult**
   - ID único da provisão
   - Valor, tipo, status
   - Lançamentos contábeis

**Exemplo:**
```java
ProvisionResult result = financialProvisionService.createProvision(
    "CLM-2024-001234",
    new BigDecimal("10000.00"),
    0.60,  // 60% recovery probability
    "BILLING_ERROR"
);

// Resultado:
// - provisionId: "PROV-2024-001234"
// - provisionAmount: R$4.000,00
// - provisionType: MINIMAL
// - accountingEntries: [DEBIT 3.1.2.01.001, CREDIT 2.1.3.01.001]
// - status: "ACTIVE"
```

---

### RN-PROV-02: Atualização de Provisão

```java
public ProvisionResult updateProvision(
    String provisionId,
    double newRecoveryProbability,
    String updateReason)
```

**Lógica:**

1. **Recupera Provisão Existente**
   - Obtém provisionId, claimId, deniedAmount, oldProvisionAmount

2. **Calcula Nova Provisão**
   - `newProvision = deniedAmount × (1 - newRecoveryProbability)`

3. **Determina Ajuste**
   - `adjustmentAmount = newProvision - oldProvision`
   - Se ajuste < 5% em valor: não atualiza (evita ruído contábil)
   - Se ajuste >= 5%: procede com atualização

4. **Gera Lançamentos de Ajuste**
   - Se ajuste positivo (aumenta provisão):
     ```
     DEBIT:  3.1.2.01.001 (Despesa Ajuste)        R$ ajuste
     CREDIT: 2.1.3.01.001 (Provisão Ajuste)       R$ ajuste
     ```
   - Se ajuste negativo (reduz provisão):
     ```
     DEBIT:  2.1.3.01.001 (Provisão Reversão)     R$ |ajuste|
     CREDIT: 3.1.2.01.001 (Despesa Reversão)      R$ |ajuste|
     ```

5. **Atualiza em TASY**
   - Modifica valor de provisão
   - Armazena lançamentos de ajuste
   - Mantém auditoria completa

**Exemplo:**
```java
// Provisão original: R$4.000 (60% recovery)
// Nova informação: recovery subiu para 80%

ProvisionResult result = financialProvisionService.updateProvision(
    "PROV-2024-001234",
    0.80,  // 80% recovery
    "Documentação adicional encontrada"
);

// Cálculo:
// newProvision = 10.000 × (1 - 0.80) = R$2.000
// adjustmentAmount = 2.000 - 4.000 = -R$2.000 (reduz)
// changePercentage = 2.000 / 4.000 × 100 = 50% (> 5%, faz ajuste)

// Lançamentos:
// DEBIT:  2.1.3.01.001 (Provisão Reversão)       R$2.000
// CREDIT: 3.1.2.01.001 (Despesa Reversão)        R$2.000

// Status: UPDATED
```

---

### RN-PROV-03: Reversão de Provisão (Recuperação)

```java
public ProvisionReversalResult reverseProvision(
    String provisionId,
    BigDecimal recoveredAmount,
    String recoveryReason)
```

**Lógica:**

1. **Recupera Detalhes da Provisão**
   - provisionId, claimId, provisionAmount

2. **Valida Valor Recuperado**
   - Se `recoveredAmount > provisionAmount`: loga warning (pode ser excesso)
   - Não falha, pois é situação válida (over-recovery)

3. **Gera Lançamentos de Reversão**
   ```
   DEBIT:  2.1.3.01.001 (Provisão Reversão)       R$ recoveredAmount
   CREDIT: 3.2.1.01.005 (Receita Recuperação)     R$ recoveredAmount
   ```

   **Racional:**
   - Remove valor de "Provisão para Glosas" (Balanço)
   - Reconhece "Receita com Recuperação" (P&L)

4. **Registra em TASY**
   - Marca provisão como parcialmente/totalmente revertida
   - Calcula `remainingProvision = originalProvision - recoveredAmount`

5. **Retorna ProvisionReversalResult**
   - Valor recuperado, valor remanescente
   - Percentual de recuperação

**Exemplo:**
```java
// Provisão original: R$4.000
// Glosa recuperada: R$3.200 (80% de recuperação)

ProvisionReversalResult result = financialProvisionService.reverseProvision(
    "PROV-2024-001234",
    new BigDecimal("3200.00"),
    "Glosa recuperada em apelação"
);

// Resultado:
// - recoveredAmount: R$3.200
// - remainingProvision: R$800 (ainda em dúvida)
// - recoveryPercentage: 80%
// - accountingEntries: [DEBIT Provisão, CREDIT Receita]
// - reversalDate: 2024-01-15T10:30:00
```

---

### RN-PROV-04: Baixa de Provisão (Write-Off)

```java
public ProvisionWriteOffResult writeOffProvision(
    String provisionId,
    String writeOffReason)
```

**Lógica:**

1. **Recupera Provisão**
   - Obtém provisionId, claimId, provisionAmount

2. **Marca como Irrecuperável**
   - Motivos: prazo expirado, contrato rescindido, decisão legal, etc.

3. **Gera Lançamento Final**
   ```
   DEBIT:  2.1.3.01.001 (Provisão Baixa)          R$ provisionAmount
   CREDIT: 3.1.2.01.002 (Perda com Glosa)         R$ provisionAmount
   ```

   **Racional:**
   - Remove da Provisão (Balanço)
   - Reconhece Perda (P&L) - afeta resultado

4. **Registra em TASY**
   - Status: WRITTEN_OFF
   - Motivo da perda
   - Data e auditoria

**Exemplo:**
```java
// Provisão de R$4.000 não recuperada (prazo expirou)

ProvisionWriteOffResult result = financialProvisionService.writeOffProvision(
    "PROV-2024-001234",
    "Prazo de cobrança expirou - Lei 10.520"
);

// Resultado:
// - writeOffAmount: R$4.000
// - reason: "Prazo de cobrança expirado - Lei 10.520"
// - accountingEntries: [DEBIT Provisão, CREDIT Perda]
// - writeOffDate: 2024-01-15T10:30:00
```

---

### RN-PROV-05: Determinação de Tipo de Provisão

```java
public ProvisionType determineProvisionType(double recoveryProbability)
```

**Lógica:**

```
recoveryProbability >= 60%  →  MINIMAL     (< 40% do valor)
20% <= recoveryProbability < 60%  →  PARTIAL  (40-80% do valor)
recoveryProbability < 20%   →  FULL        (> 80% do valor)
```

**Exemplo:**
| Recovery | Tipo | Provisão | Racional |
|----------|------|----------|----------|
| 85% | MINIMAL | R$1.500 (15%) | Muito provável recuperação |
| 50% | PARTIAL | R$5.000 (50%) | Equiprovável |
| 15% | FULL | R$8.500 (85%) | Improvável recuperação |

---

### RN-PROV-06: Cálculo de Percentuais

```java
// Percentual de provisão em relação ao valor glosado
BigDecimal provisionPercentage = provisionAmount.divide(deniedAmount, 4, RoundingMode.HALF_UP).multiply(new BigDecimal("100"));

// Percentual de recuperação em relação à provisão
BigDecimal recoveryPercentage = recoveredAmount.divide(provisionAmount, 4, RoundingMode.HALF_UP).multiply(new BigDecimal("100"));
```

**Exemplos:**
```
provisão R$4.000 / glosado R$10.000 = 40% de provisão
recuperado R$3.200 / provisão R$4.000 = 80% de recuperação
```

---

## IV. Fluxo de Processo Detalhado

### Cenário 1: Glosa com Recuperação Total

```
1. Glosa identificada: R$10.000, 60% recovery
   ↓
2. createProvision()
   - provisionAmount = 10.000 × (1 - 0.60) = R$4.000
   - provisionType = MINIMAL
   - Lançamentos: DEBIT 3.1.2 / CREDIT 2.1.3 (R$4.000)
   - Status: ACTIVE
   ↓
3. [Dias depois] Glosa recuperada integralmente
   ↓
4. reverseProvision("PROV-001", 4000.00, "Glosa recuperada")
   - remainingProvision = 4.000 - 4.000 = R$0
   - recoveryPercentage = 100%
   - Lançamentos: DEBIT 2.1.3 / CREDIT 3.2.1 (R$4.000)
   ↓
5. Resultado Final:
   - Provisão: Zerada
   - P&L: Despesa R$4.000 - Receita R$4.000 = Neutro
   - Balanço: Sem impacto
```

---

### Cenário 2: Glosa com Ajuste de Probabilidade

```
1. Glosa inicial: R$10.000, 40% recovery (alta incerteza)
   ↓
2. createProvision()
   - provisionAmount = 10.000 × (1 - 0.40) = R$6.000
   - provisionType = PARTIAL
   - Balanço: Provisão R$6.000
   ↓
3. [Semana depois] Documentação completa encontrada → 70% recovery
   ↓
4. updateProvision("PROV-001", 0.70, "Docs encontradas")
   - newProvision = 10.000 × (1 - 0.70) = R$3.000
   - adjustment = 3.000 - 6.000 = -R$3.000 (reduz)
   - changePercentage = 50% (> 5%, faz ajuste)
   - Lançamentos: DEBIT 2.1.3 / CREDIT 3.1.2 (R$3.000) [reversão]
   ↓
5. [Outro momento] Recuperação parcial de R$7.000
   ↓
6. reverseProvision("PROV-001", 7000.00, "Recuperação parcial")
   - remainingProvision = 3.000 - 7.000 = -R$4.000 (over-recovery)
   - recoveryPercentage = 233%
   - Lançamentos: DEBIT 2.1.3 / CREDIT 3.2.1 (R$7.000)
   ↓
7. Resultado Final:
   - Provisão zerada (até over-recovery de R$4.000)
   - P&L: Despesa inicial R$6.000 - Ajuste R$3.000 - Receita R$7.000 = -R$4.000
```

---

### Cenário 3: Glosa com Baixa (Perda Total)

```
1. Glosa: R$10.000, 15% recovery (muito improvável)
   ↓
2. createProvision()
   - provisionAmount = 10.000 × (1 - 0.15) = R$8.500
   - provisionType = FULL
   - Balanço: Provisão R$8.500
   ↓
3. [Meses depois] Prazo de cobrança expira (Lei 10.520)
   ↓
4. writeOffProvision("PROV-001", "Prazo expirado")
   - Status: WRITTEN_OFF
   - Lançamentos: DEBIT 2.1.3 / CREDIT 3.1.2.02 (R$8.500)
   ↓
5. Resultado Final:
   - Provisão removida do Balanço
   - P&L: Despesa R$8.500 (reconhece perda)
   - Resultado: Prejuízo R$8.500
```

---

## V. Validações e Constraints

### RN-VAL-01: Threshold de Atualização (5%)
```java
BigDecimal changePercentage = adjustmentAmount.abs()
    .divide(oldProvisionAmount, 4, RoundingMode.HALF_UP)
    .multiply(new BigDecimal("100"));

if (changePercentage.compareTo(new BigDecimal("5")) < 0) {
    return null;  // No update needed
}
```

**Racional:** Evita ruído contábil de ajustes mínimos.

### RN-VAL-02: Validação de Over-Recovery
```java
if (recoveredAmount.compareTo(provisionAmount) > 0) {
    logger.warn("Recovered amount {} exceeds provision amount {}",
                recoveredAmount, provisionAmount);
}
```

**Racional:** Válido (ex: glosa recuperada integralmente + custas), mas deve ser registrado.

### RN-VAL-03: Integridade de Lançamentos
```java
// Sempre cria pares: DEBIT + CREDIT
// Nunca um sem o outro
entries.add(new AccountingEntry(..., "DEBIT", ...));
entries.add(new AccountingEntry(..., "CREDIT", ...));
```

---

## VI. Lançamentos Contábeis Detalhados

### Tabela de Lançamentos

| Operação | DEBIT | CREDIT | Valor |
|----------|-------|--------|-------|
| Criar | 3.1.2.01.001 (Despesa) | 2.1.3.01.001 (Provisão) | Provisão |
| Aumentar | 3.1.2.01.001 (Despesa) | 2.1.3.01.001 (Provisão) | Aumento |
| Diminuir | 2.1.3.01.001 (Provisão) | 3.1.2.01.001 (Despesa) | Redução |
| Recuperar | 2.1.3.01.001 (Provisão) | 3.2.1.01.005 (Receita) | Recuperado |
| Baixar | 2.1.3.01.001 (Provisão) | 3.1.2.01.002 (Perda) | Provision |

---

## VII. Integração com GlosaAnalysisService

```java
// GlosaAnalysisService calcula probabilidade
double recoveryProbability = glosaAnalysisService.analyzeDenial(...).getRecoveryProbability();

// FinancialProvisionService usa probabilidade
BigDecimal provision = this.calculateProvisionAmount(deniedAmount, recoveryProbability);
```

**Benefício:** Duas camadas utilizam mesmo cálculo - resultado consistente.

---

## VIII. Dados e Modelos

### AccountingEntry
```java
public static class AccountingEntry {
    private String accountCode;       // GL code (e.g., "3.1.2.01.001")
    private String description;       // Claim reference
    private BigDecimal amount;        // Entry amount
    private String entryType;         // "DEBIT" or "CREDIT"
    private LocalDateTime entryDate;  // When recorded
}
```

### ProvisionResult
```java
public static class ProvisionResult {
    private String provisionId;
    private String claimId;
    private BigDecimal deniedAmount;
    private BigDecimal provisionAmount;
    private BigDecimal provisionPercentage;  // % of denied amount
    private ProvisionType provisionType;
    private double recoveryProbability;
    private List<AccountingEntry> accountingEntries;
    private LocalDateTime createdDate;
    private String status;  // "ACTIVE", "UPDATED"
}
```

### ProvisionReversalResult
```java
public static class ProvisionReversalResult {
    private String provisionId;
    private String claimId;
    private BigDecimal originalProvision;
    private BigDecimal recoveredAmount;
    private BigDecimal remainingProvision;
    private BigDecimal recoveryPercentage;  // % of provision recovered
    private List<AccountingEntry> accountingEntries;
    private LocalDateTime reversalDate;
    private String reason;
}
```

---

## IX. Conformidade CPC 25

### CPC 25 - Provision para Contingências

**Critérios para Reconhecimento:**

1. **Obrigação Legal ou Construtiva Existente**
   - Glosa é obrigação legal (contrato com operadora)
   - Hospital tem responsabilidade

2. **Saída de Recursos Provável**
   - Probability-weighted: calculado com base em histórico
   - Formula: Provisão = Valor × (1 - Recovery Probability)

3. **Estimativa Confiável**
   - Histórico de glosas por código
   - Análise de documentação
   - Ajustes por idade, pagador

**Implementação:**
```java
public ProvisionType determineProvisionType(double recoveryProbability) {
    if (recoveryProbability >= 0.60) {
        return ProvisionType.MINIMAL;  // <40% provisão
    } else if (recoveryProbability >= 0.20) {
        return ProvisionType.PARTIAL;  // 40-80% provisão
    } else {
        return ProvisionType.FULL;     // >80% provisão
    }
}
```

---

## X. Performance e SLAs

### SLAs Definidos

| Operação | SLA Latência |
|----------|--------------|
| createProvision | < 200ms |
| updateProvision | < 300ms |
| reverseProvision | < 250ms |
| writeOffProvision | < 250ms |
| calculateProvisionAmount | < 10ms |

**Complexidade Ciclomática:** ~8 (LOW-MODERATE)

---

## XI. Tratamento de Erros

### Exception Handling
```java
catch (Exception e) {
    logger.error("Error creating provision for claim {}: {}", claimId, e.getMessage(), e);
    throw new ProvisionException("Failed to create provision for claim " + claimId, e);
}
```

**Estratégia:**
- Qualquer falha em TASY ou TasyClient resulta em ProvisionException
- Não falha silenciosamente
- Permite retry ou manual intervention

---

## Conclusão

FinancialProvisionService implementa gestão completa de provisões conforme CPC 25. Cálculo probabilístico (`Provisão = Valor × (1 - Recovery Probability)`) alinha-se com normas contábeis. Ciclo completo: criação, ajuste (threshold 5%), reversão (recuperação), baixa (perda). Lançamentos contábeis separados por operação (DEBIT/CREDIT). Integração com GlosaAnalysisService garante probabilidades consistentes. Próximas melhorias: persistência em PostgreSQL, dashboard de cobertura de provisões, alertas de vencimento.
