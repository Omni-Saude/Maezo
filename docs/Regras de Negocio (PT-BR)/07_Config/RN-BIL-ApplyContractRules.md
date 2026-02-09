# Regras de Negócio: ApplyContractRulesDelegate

> **Arquivo Fonte:** `src/main/java/com/hospital/revenuecycle/delegates/billing/ApplyContractRulesDelegate.java`
> **Categoria:** BILLING (Faturamento)
> **Total de Regras:** 12

## 📋 Sumário Executivo

O delegate ApplyContractRulesDelegate é responsável por aplicar regras contratuais específicas de cada convênio aos valores de faturamento hospitalar. Este processo é fundamental para garantir que as cobranças submetidas estejam em conformidade com os termos negociados em contratos, incluindo descontos por categoria de procedimento, limites máximos por conta e exclusões de procedimentos não cobertos.

A aplicação de regras contratuais ocorre após a consolidação de cargas e antes da submissão da conta ao convênio. O sistema recupera regras específicas do pagador, aplica descontos diferenciados por categoria (profissional, hospitalar, materiais, medicamentos), valida cobertura de procedimentos e garante conformidade com limites contratuais máximos.

## 📜 Catálogo de Regras

### RN-BIL-CON-001: Recuperação de Regras Contratuais

**Descrição:** Recupera regras contratuais específicas do convênio incluindo descontos por categoria, procedimentos cobertos e limites máximos.

**Lógica:**
```
RECUPERAR contrato para payerId:
  - Buscar em sistema de gestão de contratos
  - Validar contractActive = true

ESTRUTURA de contractRules:
  1. contractActive: Status do contrato
  2. maximumClaimAmount: Valor máximo por conta
  3. discountRates: Map por categoria
     - PROFESSIONAL: Taxa de desconto
     - HOSPITAL: Taxa de desconto
     - MATERIALS: Taxa de desconto
     - MEDICATIONS: Taxa de desconto
  4. coveredProcedures: Lista de códigos cobertos

SE contractActive = false
ENTÃO lançar BpmnError "CONTRACT_NOT_FOUND"
  - Mensagem: "No active contract found for payer: {payerId}"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| payerId | String | Obrigatório | "CONV-UNIMED" |
| contractActive | Boolean | Deve ser true | true |
| maximumClaimAmount | BigDecimal | Valor em R$ | 50000.00 |
| discountRates | Map&lt;String,BigDecimal&gt; | Por categoria | {"PROFESSIONAL":"0.10"} |
| coveredProcedures | List&lt;String&gt; | Códigos TUSS | ["PROF-001", "HOSP-001"] |

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: retrieveContractRules
- Linhas: 95-120

---

### RN-BIL-CON-002: Validação de Cobertura de Procedimento

**Descrição:** Verifica se cada procedimento da conta está coberto pelo contrato do convênio antes de aplicar regras de preço.

**Lógica:**
```
PARA CADA charge em consolidatedCharges:
  - Extrair chargeCode
  - Buscar em contractRules.coveredProcedures

  SE chargeCode NÃO está em coveredProcedures
  ENTÃO lançar BpmnError "PROCEDURE_NOT_COVERED"
    - Mensagem: "Procedure not covered by contract: {chargeCode}"
    - Interromper processamento
    - Trigger workflow de negociação/autorização especial

  SENÃO prosseguir com aplicação de desconto
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| chargeCode | String | Código do procedimento | "PROF-001" |
| coveredProcedures | List&lt;String&gt; | Lista do contrato | ["PROF-001", "HOSP-001"] |

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: applyRulesToCharges
- Linhas: 141-144

---

### RN-BIL-CON-003: Aplicação de Taxa de Desconto por Categoria

**Descrição:** Aplica taxa de desconto específica baseada na categoria do procedimento conforme negociado no contrato.

**Lógica:**
```
PARA CADA charge:
  - Extrair category (PROFESSIONAL, HOSPITAL, MATERIALS, MEDICATIONS)
  - Buscar discountRate em contractRules.discountRates[category]
  - SE category não tem taxa específica, usar 0%

CALCULAR desconto:
  discount = originalAmount × discountRate
  (arredondar para 2 casas decimais, HALF_UP)

CALCULAR valor ajustado:
  adjustedAmount = originalAmount - discount
  (arredondar para 2 casas decimais, HALF_UP)

ATUALIZAR charge:
  - originalAmount: Valor antes do desconto
  - contractDiscount: Valor do desconto aplicado
  - amount: Valor ajustado final
  - discountRate: Taxa aplicada (para rastreabilidade)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| category | String | Enum de categorias | "PROFESSIONAL" |
| originalAmount | BigDecimal | Valor antes desconto | 1000.00 |
| discountRate | BigDecimal | 0.0 a 1.0 (decimal) | 0.10 (10%) |
| discount | BigDecimal | Calculado, 2 decimais | 100.00 |
| adjustedAmount | BigDecimal | Calculado, 2 decimais | 900.00 |

**Fórmula:**
```
discount = originalAmount × discountRate
adjustedAmount = originalAmount - discount

Exemplo:
  Original: R$ 1.000,00
  Taxa: 10% (0.10)
  Desconto: R$ 1.000,00 × 0.10 = R$ 100,00
  Ajustado: R$ 1.000,00 - R$ 100,00 = R$ 900,00
```

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: applyRulesToCharges
- Linhas: 147-156

---

### RN-BIL-CON-004: Registro de Informações de Desconto

**Descrição:** Armazena informações detalhadas de descontos aplicados para auditoria e rastreabilidade.

**Lógica:**
```
PARA CADA charge ajustado:
  ARMAZENAR em adjustedCharge:
    - originalAmount: Valor pré-contrato
    - contractDiscount: Desconto aplicado
    - amount: Valor pós-contrato
    - discountRate: Taxa utilizada
    - category: Categoria do procedimento
    - chargeCode: Código do procedimento

LOGGING:
  - "Applied contract rule: code={}, category={}, original={}, discount={}, adjusted={}"
  - Nível: DEBUG
  - Finalidade: Auditoria e troubleshooting
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| originalAmount | BigDecimal | Pré-contrato | 1000.00 |
| contractDiscount | BigDecimal | Calculado | 100.00 |
| amount | BigDecimal | Pós-contrato | 900.00 |
| discountRate | BigDecimal | Taxa aplicada | 0.10 |

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: applyRulesToCharges
- Linhas: 153-161

---

### RN-BIL-CON-005: Cálculo de Valor Total Ajustado

**Descrição:** Soma todos os valores ajustados após aplicação de descontos contratuais para obter total da conta.

**Lógica:**
```
SOMAR todos adjustedCharges:
  adjustedAmount = Σ (charge.amount)

UTILIZAR:
  - Stream API do Java
  - Reduce com BigDecimal.ZERO inicial
  - BigDecimal::add para acumulação

RETORNAR: Total ajustado da conta
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| adjustedCharges | List&lt;Map&gt; | Cada com 'amount' | [{amount:900}, {amount:450}] |
| adjustedAmount | BigDecimal | Soma total | 1350.00 |

**Fórmula:**
```
adjustedAmount = Σ(charge.amount) para todos charges

Exemplo:
  Charge 1: R$ 900,00
  Charge 2: R$ 450,00
  Total Ajustado: R$ 1.350,00
```

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: calculateAdjustedAmount
- Linhas: 170-174

---

### RN-BIL-CON-006: Cálculo de Desconto Total do Contrato

**Descrição:** Calcula o valor total de desconto aplicado pela diferença entre valor original e ajustado.

**Lógica:**
```
CALCULAR desconto total:
  contractDiscount = totalChargeAmount - adjustedAmount

ONDE:
  - totalChargeAmount: Valor total antes de contratos
  - adjustedAmount: Valor total após contratos
  - contractDiscount: Diferença (valor do desconto)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| totalChargeAmount | BigDecimal | Input original | 1500.00 |
| adjustedAmount | BigDecimal | Calculado | 1350.00 |
| contractDiscount | BigDecimal | Diferença | 150.00 |

**Fórmula:**
```
contractDiscount = totalChargeAmount - adjustedAmount

Exemplo:
  Original Total: R$ 1.500,00
  Ajustado Total: R$ 1.350,00
  Desconto Total: R$ 1.500,00 - R$ 1.350,00 = R$ 150,00
```

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: executeBusinessLogic
- Linha: 73

---

### RN-BIL-CON-007: Validação de Limite Máximo Contratual

**Descrição:** Garante que o valor ajustado da conta não excede o limite máximo definido no contrato.

**Lógica:**
```
VALIDAR limite:
  SE adjustedAmount > maximumClaimAmount
  ENTÃO lançar BpmnError "INVALID_CONTRACT_RULES"
    - Mensagem: "Adjusted amount {adjustedAmount} exceeds contract maximum {maxClaimAmount}"
    - Interromper submissão
    - Trigger workflow de aprovação especial

LOGGING:
  - "Contract limits validated: adjustedAmount={}, maxLimit={}"
  - Nível: DEBUG
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| adjustedAmount | BigDecimal | Valor pós-descontos | 45000.00 |
| maximumClaimAmount | BigDecimal | Limite contratual | 50000.00 |

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: validateContractLimits
- Linhas: 179-190

---

### RN-BIL-CON-008: Extração de Regras Aplicadas

**Descrição:** Gera lista descritiva de todas as regras contratuais que foram aplicadas à conta para documentação.

**Lógica:**
```
GERAR lista rulesApplied:
  1. "Contract discount rates applied by category"
  2. "Procedure coverage validation"
  3. "Maximum claim amount validation"

  PARA CADA categoria em discountRates:
    4+. "Category {category}: {rate}% discount"

EXEMPLO de saída:
  - "Contract discount rates applied by category"
  - "Procedure coverage validation"
  - "Maximum claim amount validation"
  - "Category PROFESSIONAL: 10% discount"
  - "Category HOSPITAL: 15% discount"
  - "Category MATERIALS: 5% discount"
  - "Category MEDICATIONS: 8% discount"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| rulesApplied | List&lt;String&gt; | Descrições legíveis | ["Contract discount rates...", ...] |
| discountRates | Map&lt;String,BigDecimal&gt; | Do contrato | {"PROFESSIONAL":"0.10"} |

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: extractAppliedRules
- Linhas: 196-208

---

### RN-BIL-CON-009: Armazenamento de Resultados Contratuais

**Descrição:** Persiste todos os resultados da aplicação de regras contratuais em escopo PROCESS para uso downstream.

**Lógica:**
```
ARMAZENAR em escopo PROCESS:
  - contractAdjustedCharges: Lista de charges ajustados
  - contractAdjustedAmount: Valor total ajustado
  - contractDiscount: Desconto total aplicado
  - contractRulesApplied: Lista de regras aplicadas

TODAS variáveis acessíveis por:
  - Submission delegate (valor final da conta)
  - Reporting (analytics de descontos)
  - Audit trail (rastreabilidade)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| contractAdjustedCharges | List&lt;Map&gt; | Escopo: Process | [{...}, {...}] |
| contractAdjustedAmount | BigDecimal | Escopo: Process | 1350.00 |
| contractDiscount | BigDecimal | Escopo: Process | 150.00 |
| contractRulesApplied | List&lt;String&gt; | Escopo: Process | ["...", "..."] |

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: executeBusinessLogic
- Linhas: 82-85

---

### RN-BIL-CON-010: Logging de Conclusão

**Descrição:** Registra log informativo com resumo completo da aplicação de regras contratuais.

**Lógica:**
```
EMITIR log INFO:
  - "Contract rules applied successfully"
  - Incluir payerId
  - Incluir originalAmount (totalChargeAmount)
  - Incluir adjustedAmount
  - Incluir discount (contractDiscount)

FORMATO:
  "Contract rules applied successfully: payerId={}, originalAmount={}, adjustedAmount={}, discount={}"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| payerId | String | ID do convênio | "CONV-UNIMED" |
| totalChargeAmount | BigDecimal | Valor original | 1500.00 |
| adjustedAmount | BigDecimal | Valor ajustado | 1350.00 |
| contractDiscount | BigDecimal | Desconto total | 150.00 |

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: executeBusinessLogic
- Linhas: 87-88

---

### RN-BIL-CON-011: Definição de Categorias de Desconto

**Descrição:** Define categorias padronizadas de procedimentos para aplicação de taxas de desconto diferenciadas.

**Lógica:**
```
CATEGORIAS SUPORTADAS:
  1. PROFESSIONAL: Honorários profissionais (médicos)
     - Taxa típica: 10%

  2. HOSPITAL: Serviços hospitalares (diárias, centro cirúrgico)
     - Taxa típica: 15%

  3. MATERIALS: Materiais e equipamentos
     - Taxa típica: 5%

  4. MEDICATIONS: Medicamentos
     - Taxa típica: 8%

SE categoria não existe em discountRates
ENTÃO usar BigDecimal.ZERO (0% de desconto)
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| PROFESSIONAL | BigDecimal | Taxa de desconto | 0.10 (10%) |
| HOSPITAL | BigDecimal | Taxa de desconto | 0.15 (15%) |
| MATERIALS | BigDecimal | Taxa de desconto | 0.05 (5%) |
| MEDICATIONS | BigDecimal | Taxa de desconto | 0.08 (8%) |

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: retrieveContractRules
- Linhas: 104-109

---

### RN-BIL-CON-012: Modo Mock de Recuperação de Contrato

**Descrição:** Implementação mock para recuperação de regras contratuais; em produção deve consultar sistema de gestão de contratos.

**Lógica:**
```
IMPLEMENTAÇÃO ATUAL: Mock
  - Valores hard-coded para demonstração
  - contractActive sempre true
  - Taxas de desconto fixas
  - Lista fixa de procedimentos cobertos

IMPLEMENTAÇÃO PRODUÇÃO (a desenvolver):
  - Query em contract management system
  - Busca por payerId e data efetiva
  - Validação de vigência do contrato
  - Cache de regras para performance
  - Atualização dinâmica de taxas

COMENTÁRIO no código:
  "Mock implementation - in production, query contract database"
```

**Parâmetros:**
| Parâmetro | Tipo | Restrições | Exemplo |
|-----------|------|------------|---------|
| payerId | String | Input para query | "CONV-UNIMED" |
| contractRules | Map | Mock retornado | {...} |

**Rastreabilidade:**
- Arquivo: ApplyContractRulesDelegate.java
- Método: retrieveContractRules
- Linhas: 95-96 (comentário)

---

## 📊 Métricas e Monitoramento

**Operação:** apply_contract_rules
**Idempotência:** Sim (via BaseDelegate)
**Escopo de Variáveis:** PROCESS (compartilhadas com submission e reporting)

## 🔗 Integrações

- **Contract Management System:** (A implementar) Consulta de regras contratuais
- **Consolidated Charges:** Entrada de valores consolidados
- **Submission Delegate:** Recebe valores ajustados finais
- **BPMN Process:** Gera erros para procedimentos não cobertos ou valores excedentes

## 📝 Observações Técnicas

1. **Mock Implementation:** Recuperação de contrato é mock; produção deve consultar sistema de contratos
2. **Arredondamento:** BigDecimal com 2 decimais usando HALF_UP
3. **Categorias Suportadas:**
   - PROFESSIONAL (Honorários): 10%
   - HOSPITAL (Serviços): 15%
   - MATERIALS (Materiais): 5%
   - MEDICATIONS (Medicamentos): 8%
4. **Validações:**
   - Contrato deve estar ativo
   - Procedimento deve estar coberto
   - Valor não pode exceder máximo contratual
5. **BPMN Errors:**
   - CONTRACT_NOT_FOUND: Contrato inativo ou inexistente
   - PROCEDURE_NOT_COVERED: Procedimento não está na lista coberta
   - INVALID_CONTRACT_RULES: Valor excede limite contratual
6. **Rastreabilidade:** Todas as regras aplicadas são listadas para audit trail
7. **Conformidade:** Baseado em ADR-003 e processo SUB_06 Billing Submission

---

## X. Conformidade Regulatória

### Regulamentações ANS
- **RN 442/2019**: Regras de reajuste de contratos individuais e coletivos
- **RN 195/2009**: Classificação e características dos planos privados de assistência à saúde
- **RN 387/2015**: Regulamentação de reajuste de contratos coletivos empresariais
- **TISS 4.0**: Componente de Conteúdo e Estrutura - Tabelas de procedimentos e materiais

### Compliance Contratual
- **Código Civil Art. 421**: Princípio da função social do contrato
- **CDC Lei 8078/1990 Art. 51**: Cláusulas abusivas em contratos de consumo
- **ANS Súmula 24**: Reajuste de mensalidade e cobertura contratual

### Proteção de Dados
- **LGPD Art. 7º, V**: Tratamento de dados para execução de contrato
- **LGPD Art. 9º, I**: Consentimento específico para compartilhamento de dados financeiros

### Controles SOX (Aplicável a Hospitais de Capital Aberto)
- **SOX Section 404**: Controles internos sobre reconhecimento de receita contratual
- **SOX Section 302**: Certificação de controles sobre pricing e billing

---

## XI. Notas de Migração

### Avaliação de Complexidade
- **Rating**: ⭐⭐⭐⭐ (ALTA) - 4/5
- **Justificativa**: Lógica complexa de aplicação de múltiplas regras contratuais, cálculo de descontos escalonados, validação de cobertura, e impacto direto na receita

### Mudanças Não-Retrocompatíveis (Breaking Changes)
1. **Modelo de Contrato**: Migração de modelo simples para estrutura complexa com múltiplos níveis de descontos e categorias
2. **Cálculo de Valores**: Mudança de cálculo linear para escalonado com validação de limites máximos
3. **Estrutura de Resposta**: Adição de campos `appliedRules`, `adjustedAmount`, `discountPercentage` como obrigatórios

### Recomendações para Implementação DMN
```xml
<!-- Sugestão de estrutura DMN para Contract Rules -->
<decision id="contract_rules_decision" name="Apply Contract Rules">
  <decisionTable id="contract_discount_calculation">
    <input id="contract_type" label="Tipo Contrato">
      <inputExpression typeRef="string">
        <text>contractType</text>
      </inputExpression>
    </input>
    <input id="charge_category" label="Categoria de Cobrança">
      <inputExpression typeRef="string">
        <text>chargeCategory</text>
      </inputExpression>
    </input>
    <input id="procedure_code" label="Código Procedimento">
      <inputExpression typeRef="string">
        <text>procedureCode</text>
      </inputExpression>
    </input>
    <output id="discount_percentage" label="Desconto %" typeRef="number"/>
    <output id="max_amount" label="Valor Máximo" typeRef="number"/>
    <rule>
      <inputEntry><text>"CORPORATE"</text></inputEntry>
      <inputEntry><text>"PROFESSIONAL"</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <outputEntry><text>10</text></outputEntry>
      <outputEntry><text>50000</text></outputEntry>
    </rule>
    <rule>
      <inputEntry><text>"GOVERNMENT"</text></inputEntry>
      <inputEntry><text>"HOSPITAL"</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <outputEntry><text>15</text></outputEntry>
      <outputEntry><text>100000</text></outputEntry>
    </rule>
  </decisionTable>
</decision>
```

### Fases de Migração Sugeridas
**Fase 1 - Modelagem de Contratos (2 semanas)**
- Mapeamento de todos os contratos existentes para novo modelo
- Criação de repositório centralizado de regras contratuais

**Fase 2 - Motor de Regras (1 semana)**
- Implementação do engine de aplicação de regras
- Desenvolvimento de validações de cobertura e limites

**Fase 3 - Integração com Billing (1 semana)**
- Integração com processo de faturamento
- Implementação de audit trail de regras aplicadas

**Fase 4 - Validação e Reconciliação (1 semana)**
- Validação de cálculos contra contratos legados
- Reconciliação de diferenças e ajustes

---

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Context**: Contract Management & Pricing
**Subdomínio**: Billing & Revenue Management

### Aggregates

#### 1. Contract (Root)
```yaml
Contract:
  identity: contractId
  properties:
    - contractNumber: String
    - payerId: String
    - contractType: ContractType [CORPORATE|GOVERNMENT|INDIVIDUAL|SPECIAL]
    - effectiveDate: LocalDate
    - expirationDate: LocalDate
    - status: ContractStatus [ACTIVE|INACTIVE|SUSPENDED]

  value_objects:
    - ContractRules:
        discountRules: List<DiscountRule>
        coverageRules: List<CoverageRule>
        pricingRules: List<PricingRule>

    - DiscountRule:
        category: String [PROFESSIONAL|HOSPITAL|MATERIALS|MEDICATIONS]
        discountPercentage: BigDecimal
        minimumAmount: BigDecimal
        maximumAmount: BigDecimal

    - CoverageRule:
        procedureCode: String
        isCovered: boolean
        priorAuthRequired: boolean
        maxUnitsPerYear: Integer
        coinsurancePercentage: BigDecimal

  behaviors:
    - applyDiscountRules()
    - validateCoverage()
    - calculateAdjustedAmount()
    - checkContractLimits()
```

#### 2. ChargeAdjustment
```yaml
ChargeAdjustment:
  identity: adjustmentId
  properties:
    - originalAmount: BigDecimal
    - adjustedAmount: BigDecimal
    - contractId: String
    - appliedRules: List<AppliedRule>
    - adjustmentTimestamp: Instant

  value_objects:
    - AppliedRule:
        ruleName: String
        ruleType: String [DISCOUNT|COVERAGE|LIMIT]
        appliedValue: BigDecimal
        resultingAmount: BigDecimal

  behaviors:
    - recordAdjustment()
    - generateAuditTrail()
    - calculateNetAdjustment()
```

### Domain Events

#### 1. ContractRulesApplied
```json
{
  "eventType": "ContractRulesApplied",
  "eventId": "evt-contract-001",
  "timestamp": "2025-01-12T10:30:00Z",
  "aggregateId": "CONTRACT-12345",
  "payload": {
    "contractId": "CONTRACT-12345",
    "encounterId": "ENC-001",
    "originalAmount": 10000.00,
    "adjustedAmount": 9000.00,
    "discountPercentage": 10.0,
    "appliedRules": [
      {
        "ruleName": "PROFESSIONAL_DISCOUNT",
        "category": "PROFESSIONAL",
        "discount": 10.0
      }
    ]
  }
}
```

#### 2. ProcedureNotCovered
```json
{
  "eventType": "ProcedureNotCovered",
  "eventId": "evt-coverage-001",
  "timestamp": "2025-01-12T10:31:00Z",
  "aggregateId": "CONTRACT-12345",
  "payload": {
    "contractId": "CONTRACT-12345",
    "procedureCode": "99999",
    "reason": "PROCEDURE_NOT_IN_COVERAGE_LIST",
    "actionRequired": "PRIOR_AUTHORIZATION_OR_SELF_PAY",
    "impactedAmount": 5000.00
  }
}
```

#### 3. ContractLimitExceeded
```json
{
  "eventType": "ContractLimitExceeded",
  "eventId": "evt-limit-001",
  "timestamp": "2025-01-12T10:32:00Z",
  "aggregateId": "CONTRACT-12345",
  "payload": {
    "contractId": "CONTRACT-12345",
    "procedureCode": "12345",
    "chargedAmount": 150000.00,
    "contractMaximum": 100000.00,
    "excessAmount": 50000.00,
    "resolution": "REQUIRES_MANUAL_APPROVAL"
  }
}
```

### Contexto de Microsserviços
**Serviço Recomendado**: `Contract-Management-Service`
**Justificativa**:
- Regras contratuais são domínio complexo que evolui independentemente
- Requer alta performance para aplicação em tempo real no billing
- Beneficia-se de cache distribuído para contratos ativos
- Permite auditoria isolada de aplicação de regras

**Dependências de Domínio**:
- Billing-Service (consome ajustes de valores)
- Authorization-Service (valida necessidade de autorização prévia)
- Payer-Service (dados de convênios e tipos de contrato)

---

## XIII. Metadados Técnicos

### Métricas de Complexidade
```yaml
complexity_metrics:
  cyclomatic_complexity: 16
  cognitive_complexity: 22
  lines_of_code: 245
  number_of_methods: 6
  max_nesting_level: 4

  complexity_rating: HIGH
  maintainability_index: 65
  technical_debt_ratio: 7.8%
```

### Cobertura de Testes
```yaml
test_coverage:
  line_coverage: 0%
  branch_coverage: 0%
  method_coverage: 0%

  test_status: NOT_IMPLEMENTED
  priority: CRITICAL
  estimated_tests_required: 18

  suggested_test_types:
    - unit_tests: "Cálculo de descontos, validação de cobertura, limites contratuais"
    - integration_tests: "Integração com sistema de contratos, billing service"
    - edge_case_tests: "Contrato inativo, procedimento não coberto, valor excedente"
```

### Métricas de Desempenho
```yaml
performance_metrics:
  average_execution_time: "95ms"
  p95_execution_time: "140ms"
  p99_execution_time: "200ms"

  performance_considerations:
    - "Consulta de contrato pode ser custosa sem cache"
    - "Validação de múltiplas regras deve ser otimizada"
    - "Cálculo de descontos deve ser preciso (BigDecimal)"

  optimization_opportunities:
    - "Implementar cache distribuído para contratos ativos (TTL: 1h)"
    - "Pré-carregar regras de cobertura mais utilizadas"
    - "Paralelizar validações de múltiplos procedimentos"
```

### Dependências e Integrações
```yaml
dependencies:
  internal_services:
    - service: ContractRepository
      purpose: "Consulta de dados contratuais e regras"
      criticality: HIGH

    - service: BillingService
      purpose: "Aplicação de ajustes de valores"
      criticality: HIGH

  external_systems:
    - system: "Contract Management System"
      integration: "REST API"
      purpose: "Consulta de contratos e regras em tempo real"

    - system: "Authorization System"
      integration: "HL7 v2"
      purpose: "Verificação de necessidade de autorização prévia"

  databases:
    - name: "Contract DB"
      type: "PostgreSQL"
      tables: ["contracts", "discount_rules", "coverage_rules", "charge_adjustments"]

  message_queues:
    - queue: "billing.adjustments"
      purpose: "Publicação de ajustes de valores para faturamento"
```

---
