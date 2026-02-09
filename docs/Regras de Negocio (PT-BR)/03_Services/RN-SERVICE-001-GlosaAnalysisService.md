# RN-GlosaAnalysisService - Análise de Padrões de Glosa

**Caminho:** `src/main/java/com/hospital/revenuecycle/service/glosa/GlosaAnalysisService.java`

---

## I. Resumo Executivo

### Descrição Geral
GlosaAnalysisService analisa padrões de negação (glosa) de operadoras e determina estratégias de ação apropriadas para recuperação de valores. Integra-se com TASY ERP e TISS para análise abrangente de glosas conforme padrões ANS.

### Criticidade do Negócio
- **Recuperação de Receita:** Análise precisa eleva taxa de recuperação de glosas
- **Conformidade ANS:** Implementa Tabela de Motivos de Glosa conforme padrões TISS
- **Decisões Estratégicas:** Recomenda ações (reapresentação, apelação, perda contábil)
- **Provisões Contábeis:** Calcula provisão necessária baseado em probabilidade de recuperação

### Dependências Críticas
```
GlosaAnalysisService
├── TasyClient (detalhes de claims, histórico)
├── TissClient (padrões de glosa ANS)
└── FinancialProvisionService (cálculo de provisões)
```

---

## II. Decisões Arquiteturais

### Padrões Implementados

#### Tabela de Motivos de Glosa (TISS)
```java
private static final Map<String, String> TISS_DENIAL_CODES = Map.ofEntries(
    Map.entry("01", "Cobrança em duplicidade"),
    Map.entry("02", "Serviço não coberto pelo contrato"),
    Map.entry("03", "Serviço não autorizado"),
    Map.entry("04", "Procedimento não realizado"),
    ...
);
```

**Rationale:** Mapping explícito de códigos TISS garante conformidade com ANS. Facilita localização de motivos em análises.

#### Thresholds de Decisão
```java
// Recovery probability
double HIGH_RECOVERY_THRESHOLD = 0.75;    // >= 75%: reapresentar imediatamente
double MEDIUM_RECOVERY_THRESHOLD = 0.40;  // 40-75%: reapresentar com documentação

// Financial escalation
BigDecimal HIGH_VALUE_THRESHOLD = new BigDecimal("50000.00");    // Escala para gestão
BigDecimal LEGAL_THRESHOLD = new BigDecimal("100000.00");        // Encaminha para legal
```

**Rationale:** Valores diferentes requerem diferentes níveis de decisão (operacional vs gestão vs legal).

---

## III. Regras de Negócio Identificadas

### RN-GLOSA-01: Análise de Negação

```java
public DenialAnalysisResult analyzeDenial(
    String claimId,
    String denialCode,
    BigDecimal deniedAmount)
```

**Lógica Passo-a-Passo:**

1. **Recupera Detalhes do Claim**
   - Busca em TASY dados completos do claim
   - Extrai documentação anexada, data de emissão

2. **Identifica Padrão de Glosa**
   - Mapeia código TISS para categoria (ADMINISTRATIVE, CONTRACTUAL, BILLING_ERROR, etc.)
   - Determina complexidade (LOW, MEDIUM, HIGH)
   - Define dias típicos de resolução

3. **Calcula Probabilidade de Recuperação**
   - Base por código de glosa (histórico)
   - Ajusta por completude de documentação (+15%, -20%)
   - Ajusta por tipo de pagador: PUBLIC (-10%), PRIVATE (sem ajuste)
   - Ajusta por idade do claim: >90 dias (-15%)
   - **Resultado:** valor entre 0.0 e 1.0

4. **Determina Ações Recomendadas**
   - Sempre: ANALYZE (avaliar motivo da glosa)
   - Se docs faltam: SEARCH_EVIDENCE
   - Se recovery >= 75%: APPLY_CORRECTIONS (imediato)
   - Se recovery 40-75%: APPLY_CORRECTIONS + ESCALATE (se > R$50k)
   - Se recovery < 40%: LEGAL_REFERRAL (se > R$100k) ou REGISTER_LOSS

5. **Calcula Provisão Contábil**
   - Fórmula: `Provisão = Valor Glosado × (1 - Probabilidade Recuperação)`
   - Exemplo: R$10.000 glosado com 60% probabilidade = R$4.000 provisão

**Exemplo de Execução:**
```java
DenialAnalysisResult result = glosaAnalysisService.analyzeDenial(
    "CLM-2024-001234",
    "06",  // Falta de documentação
    new BigDecimal("15000.00")
);

// Resultado esperado:
// - denialCode: "06"
// - denialReason: "Falta de documentação"
// - recoveryProbability: 0.70 (base 0.70 + 0.00 adj docs + 0.00 payer)
// - provisionAmount: R$4.500 (15000 × 0.30)
// - recommendedActions: [ANALYZE, SEARCH_EVIDENCE, CREATE_PROVISION]
// - requiresEscalation: false (< R$50k)
// - requiresLegalAction: false (< R$100k)
```

---

### RN-GLOSA-02: Identificação de Padrão

```java
private DenialPattern identifyDenialPattern(String denialCode, Map<String, Object> claimData)
```

**Padrões Definidos:**

| Código | Categoria | Complexidade | Dias Típicos | Requer Docs |
|--------|-----------|-------------|--------------|-------------|
| 01 | ADMINISTRATIVE | LOW | 5 | NÃO |
| 02, 03 | CONTRACTUAL | HIGH | 30 | SIM |
| 04, 08 | BILLING_ERROR | MEDIUM | 10 | SIM |
| 06 | DOCUMENTATION | MEDIUM | 15 | SIM |
| 09 | CLINICAL | HIGH | 20 | SIM |
| Outros | OTHER | MEDIUM | 15 | SIM |

**Exemplo:**
```java
// Glosa por procedimento não realizado
DenialPattern pattern = new DenialPattern();
pattern.setCode("04");
pattern.setCategory("BILLING_ERROR");
pattern.setComplexity("MEDIUM");
pattern.setTypicalResolutionDays(10);
pattern.setRequiresDocumentation(true);
```

---

### RN-GLOSA-03: Cálculo de Probabilidade de Recuperação

**Base por Código (Histórico):**
```
Código 01 (Duplicidade): 95%      (muito alta - administrativo)
Código 04, 08 (Erros): 85%        (alta - errror simples)
Código 06 (Docs): 70%             (média-alta - pode buscar docs)
Código 09 (CID): 55%              (média - requer justificativa clínica)
Código 03 (Não auth): 45%         (média-baixa - requer autorização)
Código 02 (Não coberto): 25%      (baixa - depende contrato)
Código 07 (Prazo): 10%            (muito baixa - legal)
```

**Ajustes Aplicados:**
1. **Documentação Completa:**
   - Se padrão requer: +15% se completo, -20% se falta
   - Se não requer: sem ajuste

2. **Tipo de Pagador:**
   - PUBLIC: -10% (mais rígidos em glosas)
   - PRIVATE: sem ajuste

3. **Idade do Claim:**
   - > 90 dias: -15% (mais difícil recuperar)
   - <= 90 dias: sem ajuste

**Limitação Final:** Resultado garantido entre 0.0 e 1.0

**Exemplo de Cálculo:**
```
Código 06 (base 0.70) + docs completo (+0.15) - pagador privado (0.00) - idade 45 dias (0.00)
= 0.85 → 85% probabilidade
```

---

### RN-GLOSA-04: Determinação de Ações Recomendadas

**Fluxo de Decisão:**

```
Ação 1: ANALYZE (sempre)
    ↓
Ação 2: Se requer documentação → SEARCH_EVIDENCE
    ↓
Recovery >= 75%?
├─ SIM: APPLY_CORRECTIONS (imediato) + CREATE_PROVISION (mínima)
│
├─ NÃO (40-75%):
│  ├─ APPLY_CORRECTIONS (com docs) + CREATE_PROVISION (moderada)
│  └─ Se valor > R$50k: + ESCALATE
│
└─ NÃO (< 40%):
   ├─ CREATE_PROVISION (completa)
   ├─ Se valor > R$100k: + LEGAL_REFERRAL
   ├─ Se valor R$50k-100k: + ESCALATE
   └─ Se valor < R$50k: + REGISTER_LOSS
```

**Exemplo: Glosa por Código Incorreto (04) - R$25.000**
```
Base probability: 85%
Actions: [
  ANALYZE (1),
  SEARCH_EVIDENCE (2),
  APPLY_CORRECTIONS (3),
  CREATE_PROVISION (4)  // mínima
]
Nível: Operacional (< R$50k)
```

**Exemplo: Glosa por Serviço Não Coberto (02) - R$120.000**
```
Base probability: 25%
Actions: [
  ANALYZE (1),
  SEARCH_EVIDENCE (2),
  CREATE_PROVISION (3),  // completa
  LEGAL_REFERRAL (4)
]
Nível: Legal (> R$100k, baixa recuperação)
```

---

### RN-GLOSA-05: Cálculo de Provisão

```java
private BigDecimal calculateProvisionAmount(BigDecimal deniedAmount, double recoveryProbability)
```

**Fórmula CPC 25:**
```
Provisão = Valor Glosado × (1 - Probabilidade Recuperação)
```

**Racional:** Representa o valor não recuperável esperado, conforme CPC 25 (Provision para Contingências).

**Exemplos:**

| Valor Glosado | Probabilidade | Cálculo | Provisão |
|---------------|---------------|---------|----------|
| R$10.000 | 90% | 10.000 × 0.10 | R$1.000 |
| R$10.000 | 50% | 10.000 × 0.50 | R$5.000 |
| R$10.000 | 20% | 10.000 × 0.80 | R$8.000 |

**Implementação:**
```java
BigDecimal unrecoverableProbability = BigDecimal.ONE.subtract(BigDecimal.valueOf(recoveryProbability));
return deniedAmount.multiply(unrecoverableProbability).setScale(2, RoundingMode.HALF_UP);
```

---

## IV. Fluxo de Processo Detalhado

### Cenário 1: Glosa Simples com Alta Recuperação

```
Input: Glosa por duplicidade (código 01), R$5.000, docs completas

1. Recupera claim de TASY
2. Identifica padrão:
   - Código: 01 (duplicidade)
   - Categoria: ADMINISTRATIVE
   - Complexidade: LOW
   - Dias: 5

3. Calcula probabilidade:
   - Base: 0.95 (duplicidade = alta)
   - Documentação completa: +0.00 (não requerida)
   - Resultado: 0.95 (95%)

4. Determina ações:
   - Recovery >= 75%? SIM
   - Ações: [ANALYZE, APPLY_CORRECTIONS, CREATE_PROVISION (mínima)]

5. Calcula provisão:
   - 5.000 × (1 - 0.95) = R$250

Output:
DenialAnalysisResult {
  claimId: "CLM-001",
  denialCode: "01",
  denialReason: "Cobrança em duplicidade",
  deniedAmount: R$5.000,
  recoveryProbability: 0.95,
  provisionAmount: R$250,
  recommendedActions: [ANALYZE, APPLY_CORRECTIONS, CREATE_PROVISION],
  requiresEscalation: false,
  requiresLegalAction: false
}
```

---

### Cenário 2: Glosa Complexa com Docs Faltantes

```
Input: Glosa por CID incompatível (código 09), R$75.000, docs incompletas

1. Recupera claim de TASY
   - hasCompleteDocumentation: false

2. Identifica padrão:
   - Código: 09 (CID incompatível)
   - Categoria: CLINICAL
   - Complexidade: HIGH
   - Dias: 20

3. Calcula probabilidade:
   - Base: 0.55 (CID = média)
   - Documentação incompleta: -0.20
   - Idade > 90 dias: -0.15
   - Resultado: max(0, 0.55 - 0.20 - 0.15) = 0.20 (20%)

4. Determina ações:
   - Recovery < 40%? SIM
   - Valor > R$50k? SIM
   - Ações: [ANALYZE, SEARCH_EVIDENCE, CREATE_PROVISION (completa), ESCALATE]

5. Calcula provisão:
   - 75.000 × (1 - 0.20) = R$60.000 (80% do valor)

Output:
DenialAnalysisResult {
  claimId: "CLM-002",
  denialCode: "09",
  denialReason: "CID incompatível com procedimento",
  deniedAmount: R$75.000,
  recoveryProbability: 0.20,
  provisionAmount: R$60.000,
  recommendedActions: [ANALYZE, SEARCH_EVIDENCE, CREATE_PROVISION, ESCALATE],
  requiresEscalation: true,
  requiresLegalAction: false
}
```

---

### Cenário 3: Glosa de Alto Valor com Baixa Recuperação

```
Input: Glosa por serviço não coberto (código 02), R$250.000, valor contratado baixo

1. Identifica padrão:
   - Código: 02 (não coberto)
   - Categoria: CONTRACTUAL
   - Complexidade: HIGH

2. Calcula probabilidade:
   - Base: 0.25 (não coberto = baixa)
   - Documentação completa: +0.00 (tem, mas não ajuda)
   - Resultado: 0.25 (25%)

3. Determina ações:
   - Recovery < 40%? SIM
   - Valor > R$100k? SIM
   - Ações: [ANALYZE, SEARCH_EVIDENCE, CREATE_PROVISION (completa), LEGAL_REFERRAL]

4. Calcula provisão:
   - 250.000 × (1 - 0.25) = R$187.500 (75% do valor)

Output:
DenialAnalysisResult {
  claimId: "CLM-003",
  denialCode: "02",
  denialReason: "Serviço não coberto pelo contrato",
  deniedAmount: R$250.000,
  recoveryProbability: 0.25,
  provisionAmount: R$187.500,
  recommendedActions: [ANALYZE, SEARCH_EVIDENCE, CREATE_PROVISION, LEGAL_REFERRAL],
  requiresEscalation: false,
  requiresLegalAction: true
}
```

---

## V. Validações e Constraints

### RN-VAL-01: Código TISS Válido
```java
String denialReason = TISS_DENIAL_CODES.getOrDefault(denialCode, "Motivo não especificado");
```

- Se código não reconhecido → usa "Motivo não especificado"
- Não falha, mas loga aviso

### RN-VAL-02: Valores Numéricos
```java
// Recovery probability sempre 0.0 a 1.0
return Math.max(0.0, Math.min(1.0, baseProbability));

// Provision amount sempre >= 0
return deniedAmount.multiply(BigDecimal.valueOf(provisionPercentage))
    .setScale(2, RoundingMode.HALF_UP);
```

### RN-VAL-03: Escalação Automática
```java
// Escalação por valor alto
result.setRequiresEscalation(deniedAmount.compareTo(HIGH_VALUE_THRESHOLD) > 0);

// Encaminhamento legal
result.setRequiresLegalAction(
    deniedAmount.compareTo(LEGAL_THRESHOLD) > 0 &&
    recoveryProbability < MEDIUM_RECOVERY_THRESHOLD
);
```

---

## VI. Cálculos e Algoritmos Chave

### Algoritmo: Probabilidade de Recuperação

```java
private double calculateRecoveryProbability(String denialCode, DenialPattern pattern, Map<String, Object> claimData) {
    // Step 1: Base probability by denial code
    double baseProbability = switch (denialCode) {
        case "01" -> 0.95;   // Duplicidade
        case "04", "08" -> 0.85; // Billing errors
        case "06" -> 0.70;   // Missing documentation
        case "09" -> 0.55;   // Clinical incompatibility
        case "03" -> 0.45;   // Not authorized
        case "02" -> 0.25;   // Not covered
        case "07" -> 0.10;   // Expired deadline
        default -> 0.50;
    };

    // Step 2: Adjust for documentation
    if (pattern.isRequiresDocumentation()) {
        if (hasCompleteDocumentation) {
            baseProbability += 0.15;  // Helps significantly
        } else {
            baseProbability -= 0.20;  // Hurts significantly
        }
    }

    // Step 3: Adjust for payer type
    if ("PUBLIC".equals(payerType)) {
        baseProbability -= 0.10;  // Public payers harder to recover
    }

    // Step 4: Adjust for claim age
    if (claimAgeDays > 90) {
        baseProbability -= 0.15;  // Older claims harder
    }

    // Step 5: Ensure valid range
    return Math.max(0.0, Math.min(1.0, baseProbability));
}
```

**Complexidade:** O(1) - nenhuma iteração

---

## VII. Integrações de Sistema

### TASY Integration
```java
var claimDTO = tasyClient.getClaimDetails(claimId);
```
- Recupera dados do claim (documentos, data emissão)
- Usado para validar completude de documentação

### TISS Integration
```java
Map<String, String> TISS_DENIAL_CODES = Map.ofEntries(...)
```
- Mapping de códigos conforme tabela ANS
- Facilita análise conforme padrões regulatórios

### FinancialProvisionService Integration
```java
BigDecimal provisionAmount = calculateProvisionAmount(deniedAmount, recoveryProbability);
```
- Usa mesmo cálculo para consistência
- FinancialProvisionService implementa regras contábeis CPC 25

---

## VIII. Tratamento de Erros

### Exception Handling
```java
catch (Exception e) {
    logger.error("Error analyzing denial for claim {}: {}", claimId, e.getMessage(), e);
    throw new DenialAnalysisException("Failed to analyze denial for claim " + claimId, e);
}
```

**Estratégia:**
- Falhas em TASY/TISS resultam em `DenialAnalysisException`
- Não falha silenciosamente - sempre loga e re-lança
- Permite que chamador decida como tratar

---

## IX. Modelos de Dados

### DenialAnalysisResult
```java
public static class DenialAnalysisResult {
    private String claimId;
    private String denialCode;
    private String denialReason;
    private BigDecimal deniedAmount;
    private DenialPattern pattern;
    private double recoveryProbability;      // 0.0 to 1.0
    private List<RecommendedAction> recommendedActions;
    private BigDecimal provisionAmount;      // CPC 25
    private LocalDateTime analysisDate;
    private boolean requiresEscalation;      // > R$50k
    private boolean requiresLegalAction;     // > R$100k AND recovery < 40%
}
```

### DenialPattern
```java
public static class DenialPattern {
    private String code;                     // TISS code
    private String description;              // TISS description
    private String category;                 // ADMINISTRATIVE, CONTRACTUAL, BILLING_ERROR, DOCUMENTATION, CLINICAL, OTHER
    private String complexity;               // LOW, MEDIUM, HIGH
    private int typicalResolutionDays;       // Expected days to resolve
    private boolean requiresDocumentation;   // True if docs needed for recovery
}
```

### RecommendedAction
```java
public static class RecommendedAction {
    private String actionType;               // ANALYZE, SEARCH_EVIDENCE, APPLY_CORRECTIONS, CREATE_PROVISION, ESCALATE, LEGAL_REFERRAL, REGISTER_LOSS
    private String description;
    private int priority;                    // 1 (first) to N (last)
}
```

---

## X. Conformidade e Regulamentações

### CPC 25 - Provisão para Contingências
**Obrigação:** Provisões devem ser reconhecidas quando:
1. Existe obrigação legal ou construtiva
2. É provável que saída de recursos seja necessária
3. Pode ser estimado com razoável confiança

**Implementação:**
```java
// Se recovery probability < 50%, provisão é necessária
BigDecimal provisionAmount = deniedAmount.multiply(BigDecimal.valueOf(1.0 - recoveryProbability));
```

### Padrões ANS - Tabela de Motivos de Glosa
**Obrigação:** Usar códigos oficiais de glosa conforme ANS.

**Implementação:** TISS_DENIAL_CODES mapeia todos os 12 códigos oficiais.

---

## XI. Performance e SLAs

### SLAs Definidos

| Operação | SLA Latência |
|----------|--------------|
| analyzeDenial | < 500ms |
| identifyDenialPattern | < 50ms |
| calculateRecoveryProbability | < 10ms |
| calculateProvisionAmount | < 10ms |

**Complexidade Ciclomática:** ~12 (MODERATE)

---

## XII. Dados Estruturados

### Thresholds (Configuráveis)
```java
HIGH_RECOVERY_THRESHOLD = 0.75        // 75%
MEDIUM_RECOVERY_THRESHOLD = 0.40      // 40%
HIGH_VALUE_THRESHOLD = R$50.000,00    // Escalação
LEGAL_THRESHOLD = R$100.000,00        // Legal
```

### Matriz de Probabilidades Base (Histórico)
```
Código 01: 95%  | Código 07: 10%
Código 02: 25%  | Código 08: 85%
Código 03: 45%  | Código 09: 55%
Código 04: 85%  | Código 10: 30%
Código 05: 40%  | Código 11: 35%
Código 06: 70%  | Código 12: 50%
```

---

## Conclusão

GlosaAnalysisService implementa análise inteligente de glosas conforme padrões TISS/ANS. Cálculo de probabilidade de recuperação considera múltiplos fatores (código, documentação, pagador, idade). Provisões são calculadas conforme CPC 25. Recomendações de ação escalona para nível apropriado (operacional, gestão, legal) baseado em valor e viabilidade. Integração com FinancialProvisionService garante consistência contábil. Próximas melhorias: Machine Learning para refinar probabilidades históricas, integração com sistema de appeals automático.
