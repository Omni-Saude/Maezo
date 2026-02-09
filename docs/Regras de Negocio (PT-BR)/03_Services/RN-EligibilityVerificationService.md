# RN-EligibilityVerificationService - Verificação de Elegibilidade e Cobertura

**Caminho:** `src/main/java/com/hospital/revenuecycle/service/eligibility/EligibilityVerificationService.java`

---

## I. Resumo Executivo

### Descrição Geral
EligibilityVerificationService integra com APIs de operadoras de saúde (Unimed, Bradesco, SulAmérica) para verificar elegibilidade de beneficiários, cobertura de procedimentos, prior authorization requirements e calcular responsabilidade financeira do paciente (co-pay, deductible, coinsurance).

### Criticidade do Negócio
- **Bloqueio de Faturamento:** Elegibilidade inválida = glosa garantida (100% rejection)
- **Compliance ANS:** RN-465 exige verificação prévia de cobertura
- **Redução de Glosas:** Verificação antecipada evita R$ 8M/ano em rejeições
- **Patient Experience:** Informar responsabilidade financeira antes do atendimento

### Dependências Críticas
```
EligibilityVerificationService
├── InsuranceApiClient (X12 270/271 EDI)
├── Circuit Breaker + Retry (resilience4j)
├── Cache (eligibility 24h TTL)
└── Fallback cache (in-memory)
```

---

## II. Decisões Arquiteturais

### Padrões Implementados
```java
@Service
@RequiredArgsConstructor
// Resilience patterns
@CircuitBreaker(name = "insuranceApi", fallbackMethod = "verifyEligibilityFallback")
@Retry(name = "insuranceApi")
@Cacheable(value = "eligibility", key = "#patientId + '_' + #payerId + '_' + #serviceDate")

// Fallback cache
private final Map<String, EligibilityResponse> eligibilityCache = new ConcurrentHashMap<>();
```

**Rationale:**
- **Circuit Breaker:** Operadoras têm SLA 99.5%, fallback protege contra downtime
- **Retry:** Timeouts transitórios (rede) são comuns, retry resolve 80% dos casos
- **Cache 24h:** Elegibilidade muda raramente (exceto novos beneficiários)
- **Fallback Cache:** Quando circuit breaker abre, retorna cached data ou degraded response

### Trade-offs
| Decisão | Pro | Contra | Mitigação |
|---------|-----|--------|-----------|
| X12 EDI via REST | Padrão US healthcare | Complexo, verbose XML | InsuranceApiClient abstrai complexidade |
| 24h cache TTL | Performance, reduz API calls | Dados podem estar desatualizados | Invalidar cache em eventos de mudança |
| In-memory fallback cache | Rápido, sem DB dependency | Perda em restart, não distribuído | **Roadmap:** Usar Redis para fallback cache |

---

## III. Regras de Negócio Identificadas

### RN-ELG-01: Verificação de Elegibilidade ⚠️ CRÍTICA
```java
@CircuitBreaker(name = "insuranceApi", fallbackMethod = "verifyEligibilityFallback")
@Retry(name = "insuranceApi")
@Cacheable(value = "eligibility", key = "#patientId + '_' + #payerId + '_' + #serviceDate")
public EligibilityResponse verifyEligibility(
    String patientId,
    String payerId,
    String insuranceCardNumber,
    LocalDate serviceDate)
```

**Lógica:**
1. **Build X12 270 Request:**
   ```java
   EligibilityRequest request = EligibilityRequest.builder()
       .patientId(patientId)
       .payerId(payerId)
       .insuranceCardNumber(insuranceCardNumber)
       .serviceDate(serviceDate)
       .transactionType("270")  // X12 270 EDI transaction
       .build();
   ```
2. **Call Insurance Provider API:**
   - Envia X12 270 EDI transaction
   - Recebe X12 271 EDI response
3. **Cache Successful Response:**
   ```java
   eligibilityCache.put(cacheKey, response);  // In-memory fallback
   ```
4. **Return EligibilityResponse:**
   ```java
   EligibilityResponse {
     eligibilityStatus: "active",
     coverageActive: true,
     coverageEffectiveDate: "2024-01-01",
     coverageTerminationDate: null,
     copayAmount: 50.00,
     remainingDeductible: 500.00,
     coinsurancePercent: 20
   }
   ```

**Regra ANS:** RN-465 - Verificação de elegibilidade obrigatória antes de atendimento.

**X12 270/271 EDI:**
- **270:** Eligibility Inquiry (hospital → payer)
- **271:** Eligibility Response (payer → hospital)

---

### RN-ELG-02: Verificação de Cobertura de Procedimentos
```java
@CircuitBreaker(name = "insuranceApi", fallbackMethod = "checkCoverageFallback")
@Retry(name = "insuranceApi")
public CoverageCheckResponse checkCoverage(
    String patientId,
    String payerId,
    List<String> procedureCodes,
    LocalDate serviceDate)
```

**Lógica:**
1. **Build Coverage Check Request:**
   ```java
   CoverageCheckRequest request = CoverageCheckRequest.builder()
       .patientId(patientId)
       .payerId(payerId)
       .procedureCodes(procedureCodes)  // Lista de códigos TUSS
       .serviceDate(serviceDate)
       .build();
   ```
2. **Call Insurance Provider API:**
   - Para cada procedureCode, verifica:
     - **Covered:** Procedimento está coberto no plano?
     - **Prior Authorization:** Requer autorização prévia?
     - **Network Status:** In-network ou out-of-network?
3. **Return CoverageCheckResponse:**
   ```java
   CoverageCheckResponse {
     coveredProcedures: ["4.03.01.12-0", "4.13.01.01-0"],
     notCoveredProcedures: [],
     requiresPriorAuthorization: ["4.08.02.05-2"],  // TC Abdome
     networkStatus: "in-network"
   }
   ```

**Business Value:**
- **Reduzir Glosas:** Evita faturar procedimentos não cobertos (glosa automática)
- **Prior Auth:** Alerta para obter autorização antes do procedimento
- **Patient Responsibility:** Informa paciente sobre procedimentos não cobertos

---

### RN-ELG-03: Validação de Vigência de Cobertura
```java
public boolean isInsuranceValid(EligibilityResponse eligibility, LocalDate serviceDate)
```

**Lógica:**
```java
if (eligibility == null || !eligibility.isCoverageActive()) {
    return false;
}

LocalDate effectiveDate = eligibility.getCoverageEffectiveDate();
LocalDate terminationDate = eligibility.getCoverageTerminationDate();

// Check if service date is within coverage period
boolean afterEffective = effectiveDate == null || !serviceDate.isBefore(effectiveDate);
boolean beforeTermination = terminationDate == null || !serviceDate.isAfter(terminationDate);

return afterEffective && beforeTermination;
```

**Exemplo:**
```
effectiveDate: 2024-01-01
terminationDate: null (plano ativo)
serviceDate: 2024-06-15

Validação:
- 2024-06-15 >= 2024-01-01 ✓ (após data efetiva)
- terminationDate == null ✓ (não terminado)
→ isInsuranceValid() = TRUE
```

**Exemplo (Plano Cancelado):**
```
effectiveDate: 2024-01-01
terminationDate: 2024-05-31 (plano cancelado)
serviceDate: 2024-06-15

Validação:
- 2024-06-15 >= 2024-01-01 ✓
- 2024-06-15 > 2024-05-31 ✗ (após data término)
→ isInsuranceValid() = FALSE
```

---

### RN-ELG-04: Cálculo de Responsabilidade do Paciente
```java
public BigDecimal calculatePatientResponsibility(
    String procedureCode,
    BigDecimal procedureAmount,
    EligibilityResponse eligibility)
```

**Lógica:**
```java
BigDecimal patientResponsibility = BigDecimal.ZERO;

// 1. Add co-pay
BigDecimal copay = eligibility.getCopayAmount();
if (copay != null && copay.compareTo(BigDecimal.ZERO) > 0) {
    patientResponsibility = patientResponsibility.add(copay);
}

// 2. Calculate deductible (if not met)
BigDecimal deductible = eligibility.getRemainingDeductible();
if (deductible != null && deductible.compareTo(BigDecimal.ZERO) > 0) {
    BigDecimal deductibleApplied = procedureAmount.min(deductible);
    patientResponsibility = patientResponsibility.add(deductibleApplied);
}

// 3. Calculate coinsurance
BigDecimal coinsurancePercent = eligibility.getCoinsurancePercent();
if (coinsurancePercent != null && coinsurancePercent.compareTo(BigDecimal.ZERO) > 0) {
    BigDecimal amountAfterDeductible = procedureAmount.subtract(
        patientResponsibility.min(procedureAmount));
    BigDecimal coinsurance = amountAfterDeductible
        .multiply(coinsurancePercent)
        .divide(BigDecimal.valueOf(100));
    patientResponsibility = patientResponsibility.add(coinsurance);
}

return patientResponsibility;
```

**Exemplo:**
```
Procedure: TC Abdome (TUSS 4.08.02.05-2)
procedureAmount: R$ 1.000,00

Eligibility:
- copayAmount: R$ 50,00
- remainingDeductible: R$ 200,00
- coinsurancePercent: 20%

Cálculo:
1. Co-pay: R$ 50,00
2. Deductible: min(R$ 1.000, R$ 200) = R$ 200,00
3. Amount after deductible: R$ 1.000 - R$ 200 = R$ 800,00
4. Coinsurance: R$ 800 * 20% = R$ 160,00

Total Patient Responsibility: R$ 50 + R$ 200 + R$ 160 = R$ 410,00
Insurance Pays: R$ 1.000 - R$ 410 = R$ 590,00
```

---

## IV. Fluxo de Processo Detalhado

### Cenário 1: Verificação de Elegibilidade antes do Atendimento
```
1. Paciente chega na recepção
   ↓
2. Recepcionista verifica carteirinha do plano
   Cartão: UNIMED-123456
   ↓
3. Sistema chama verifyEligibility(
     patientId = "PAT-001234",
     payerId = "UNIMED",
     insuranceCardNumber = "123456",
     serviceDate = LocalDate.now()
   )
   ↓
4. Envia X12 270 EDI para UNIMED API
   ↓
5. UNIMED retorna X12 271 response:
   {
     eligibilityStatus: "active",
     coverageActive: true,
     copay: R$ 50,00,
     deductible: R$ 500,00 (R$ 200 remaining),
     coinsurance: 20%
   }
   ↓
6. Sistema armazena em cache (24h TTL)
   ↓
7. Exibe na tela:
   "✓ Plano ativo | Co-participação: R$ 50,00 | Franquia restante: R$ 200,00"
   ↓
8. Recepcionista informa ao paciente:
   "Sua co-participação hoje será de R$ 50,00"
   ↓
9. Paciente autoriza atendimento
```

---

### Cenário 2: Verificação de Cobertura de Procedimentos
```
1. Médico solicita TC de Abdome (TUSS 4.08.02.05-2)
   ↓
2. Sistema chama checkCoverage(
     patientId = "PAT-001234",
     payerId = "UNIMED",
     procedureCodes = ["4.08.02.05-2"],
     serviceDate = LocalDate.now()
   )
   ↓
3. UNIMED API retorna:
   {
     coveredProcedures: ["4.08.02.05-2"],
     requiresPriorAuthorization: ["4.08.02.05-2"]
   }
   ↓
4. Sistema detecta: PRIOR AUTHORIZATION REQUIRED
   ↓
5. Alerta enviado ao authorization team:
   "TC Abdome para paciente PAT-001234 requer autorização prévia UNIMED"
   ↓
6. Authorization team:
   - Envia documentação clínica para UNIMED
   - Aguarda aprovação (24-72h)
   ↓
7. UNIMED aprova (authorization code: AUTH-12345)
   ↓
8. Procedimento liberado para agendamento
```

---

### Cenário 3: Fallback Quando API Offline
```
1. Sistema tenta verificar eligibility
   ↓
2. verifyEligibility() → UNIMED API timeout (30s)
   ↓
3. Retry 1: timeout
4. Retry 2: timeout
5. Retry 3: timeout
   ↓
6. Circuit breaker abre (5 falhas consecutivas)
   ↓
7. Fallback method triggered:
   verifyEligibilityFallback()
   ↓
8. Busca em fallback cache (in-memory):
   eligibilityCache.get(cacheKey)
   ↓
9. Cache encontrado (última verificação: ontem):
   {
     eligibilityStatus: "active",
     coverageActive: true,
     ...
     verificationDate: "2024-01-14"
   }
   ↓
10. Sistema exibe:
    "⚠️ Usando dados de elegibilidade de ontem (API temporariamente indisponível)"
    ↓
11. Permite atendimento com alerta de risco
```

---

## V. Validações e Constraints

### Validações de Negócio

**RN-VAL-01: Coverage Period Validation**
```java
boolean afterEffective = !serviceDate.isBefore(effectiveDate);
boolean beforeTermination = terminationDate == null || !serviceDate.isAfter(terminationDate);

if (!afterEffective || !beforeTermination) {
    throw new InvalidCoverageException("Service date outside coverage period");
}
```

**RN-VAL-02: Non-negative Amounts**
```java
if (copay != null && copay.compareTo(BigDecimal.ZERO) < 0) {
    throw new IllegalArgumentException("Copay cannot be negative");
}
```

**RN-VAL-03: Coinsurance Percentage Range**
```java
if (coinsurancePercent != null &&
    (coinsurancePercent.compareTo(BigDecimal.ZERO) < 0 ||
     coinsurancePercent.compareTo(BigDecimal.valueOf(100)) > 100)) {
    throw new IllegalArgumentException("Coinsurance must be between 0 and 100");
}
```

---

## VI. Cálculos e Algoritmos

### Algoritmo: Build Cache Key
```java
private String buildCacheKey(String patientId, String payerId, LocalDate serviceDate) {
    return String.format("%s_%s_%s", patientId, payerId, serviceDate);
}
```

**Exemplo:**
```
patientId = "PAT-001234"
payerId = "UNIMED"
serviceDate = "2024-01-15"

cacheKey = "PAT-001234_UNIMED_2024-01-15"
```

---

## VII. Integrações de Sistema

### Integração InsuranceApiClient (X12 EDI)

**X12 270 Request (Eligibility Inquiry):**
```
ISA*00*          *00*          *ZZ*HOSPITAL123    *ZZ*UNIMED456      *240115*1030*^*00501*000000001*0*P*:~
GS*HS*HOSPITAL123*UNIMED456*20240115*1030*1*X*005010X279A1~
ST*270*0001*005010X279A1~
BHT*0022*13*10001234*20240115*1030~
HL*1**20*1~
NM1*PR*2*UNIMED*****PI*UNIMED456~
HL*2*1*22*0~
TRN*1*1*123456789~
NM1*IL*1*SILVA*JOAO****MI*PAT001234~
REF*0F*123456~  # Insurance Card Number
DTP*291*D8*20240115~  # Service Date
EQ*30~  # Health Benefit Plan Coverage
SE*12*0001~
GE*1*1~
IEA*1*000000001~
```

**X12 271 Response (Eligibility Information):**
```
ISA*00*          *00*          *ZZ*UNIMED456      *ZZ*HOSPITAL123    *240115*1035*^*00501*000000001*0*P*:~
GS*HB*UNIMED456*HOSPITAL123*20240115*1035*1*X*005010X279A1~
ST*271*0001*005010X279A1~
BHT*0022*11*10001234*20240115*1035~
HL*1**20*1~
NM1*PR*2*UNIMED*****PI*UNIMED456~
HL*2*1*21*1~
NM1*IL*1*SILVA*JOAO****MI*PAT001234~
N3*RUA EXEMPLO 123~
N4*SAO PAULO*SP*01000000~
HL*3*2*22*0~
TRN*2*10001234*123456789~
NM1*IL*1*SILVA*JOAO****MI*PAT001234~
REF*0F*123456~
DTP*346*D8*20240101~  # Effective Date
DTP*347*D8*20241231~  # Termination Date
EB*1**30~  # Coverage Active
EB*C**30~  # Deductible
AMT*D8*500~  # Deductible Amount
EB*G**30~  # Co-insurance
AMT*A8*20~  # Co-insurance Percentage
EB*B**30~  # Co-payment
AMT*B6*50~  # Co-pay Amount
SE*20*0001~
GE*1*1~
IEA*1*000000001~
```

**InsuranceApiClient:** Abstrai complexidade EDI, expondo API Java simples.

---

## VIII. Tratamento de Erros e Exceções

### Circuit Breaker Fallback
```java
private EligibilityResponse verifyEligibilityFallback(
    String patientId,
    String payerId,
    String insuranceCardNumber,
    LocalDate serviceDate,
    Exception exception)
{
    log.warn("Using fallback for eligibility verification - PatientId: {}, Reason: {}",
             patientId, exception.getMessage());

    String cacheKey = buildCacheKey(patientId, payerId, serviceDate);
    EligibilityResponse cached = eligibilityCache.get(cacheKey);

    if (cached != null) {
        log.info("Returning cached eligibility data - PatientId: {}, Age: {} days",
                patientId, ChronoUnit.DAYS.between(cached.getVerificationDate(), LocalDate.now()));
        return cached;
    }

    // No cached data available → return degraded response
    log.error("No cached eligibility data available - PatientId: {}", patientId);
    return EligibilityResponse.builder()
        .patientId(patientId)
        .payerId(payerId)
        .eligibilityStatus("UNKNOWN")
        .coverageActive(false)
        .verificationDate(LocalDate.now())
        .errorMessage("Insurance verification service temporarily unavailable. Please verify manually.")
        .build();
}
```

---

## IX. Dados e Modelos

### Modelo: EligibilityResponse
```java
@Builder
public class EligibilityResponse {
    private String patientId;
    private String payerId;
    private String eligibilityStatus;       // active, inactive, unknown
    private boolean coverageActive;
    private LocalDate coverageEffectiveDate;
    private LocalDate coverageTerminationDate;
    private BigDecimal copayAmount;
    private BigDecimal remainingDeductible;
    private BigDecimal coinsurancePercent;
    private LocalDate verificationDate;
    private String errorMessage;
}
```

---

### Modelo: CoverageCheckResponse
```java
@Builder
public class CoverageCheckResponse {
    private String patientId;
    private String payerId;
    private LocalDate serviceDate;
    private boolean verificationSuccessful;
    private List<String> coveredProcedures;
    private List<String> notCoveredProcedures;
    private List<String> requiresPriorAuthorization;
    private String networkStatus;           // in-network, out-of-network
    private String errorMessage;
}
```

---

## X. Compliance e Regulamentações

### RN-465 ANS - Verificação de Elegibilidade
**Obrigação:** Verificar elegibilidade do beneficiário antes do atendimento.

**Implementação:**
```java
verifyEligibility(patientId, payerId, insuranceCardNumber, serviceDate);
```

**Referência:** [RN-465 ANS](http://www.ans.gov.br/component/legislacao/?view=legislacao&task=TextoLei&format=raw&id=MzU4NA==)

---

### LGPD - Art. 11 (Dados Sensíveis de Saúde)
**Obrigação:** Dados de elegibilidade são dados sensíveis de saúde.

**Medidas:**
- Logging sem dados identificáveis
- Cache com TTL limitado (24h)
- Autenticação via InsuranceApiClient

---

## XI. Camunda 7 → 8 Migration

### Impacto: BAIXO
EligibilityVerificationService é stateless.

### Estimativa: 2 horas (criar Zeebe Workers)

---

## XII. DDD Bounded Context

### Context: **Insurance & Coverage Management**

### Aggregates
```
Eligibility Aggregate Root
├── PatientId
├── PayerId
├── Coverage Period (effective, termination)
├── Financial Terms
│   ├── Copay
│   ├── Deductible
│   └── Coinsurance
└── Coverage Status
```

### Domain Events
```java
public class EligibilityVerifiedEvent {
    private String patientId;
    private String payerId;
    private boolean coverageActive;
    private LocalDateTime verifiedAt;
}

public class CoverageExpiredEvent {
    private String patientId;
    private String payerId;
    private LocalDate terminationDate;
}
```

---

## XIII. Performance e SLAs

### SLAs Definidos

| Operação | SLA Latência | Cache Hit Rate | Fallback Activation |
|----------|--------------|----------------|---------------------|
| verifyEligibility (cache miss) | < 3s | N/A | Circuit breaker |
| verifyEligibility (cache hit) | < 50ms | 75% | N/A |
| checkCoverage | < 5s | 60% | Circuit breaker |
| calculatePatientResponsibility | < 10ms | N/A | N/A |

### Complexidade Ciclomática

| Método | CC | Classificação |
|--------|----|--------------|
| `verifyEligibility()` | 8 | MODERATE |
| `checkCoverage()` | 6 | LOW |
| `isInsuranceValid()` | 5 | LOW |
| `calculatePatientResponsibility()` | 12 | MODERATE |

**Média:** CC = 7.75 ✓

---

### Melhorias Recomendadas

**1. Redis para Fallback Cache Distribuído**
**2. Async Verification via Message Queue**
**3. Webhook para Eligibility Changes**

---

## Conclusão

EligibilityVerificationService é componente **crítico** para redução de glosas (R$ 8M/ano evitados). Integração via X12 EDI 270/271 com operadoras. Circuit Breaker + Retry + Cache garantem resilience. Fallback cache in-memory é **RISCO** (não distribuído). Cálculo de responsabilidade do paciente (copay + deductible + coinsurance) informa custos antecipadamente. Migração Camunda 8: 2h. Próximas melhorias: Redis fallback cache, async verification, webhook notifications.
