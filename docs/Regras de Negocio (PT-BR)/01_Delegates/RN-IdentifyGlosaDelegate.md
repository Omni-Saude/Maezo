# RN-IdentifyGlosaDelegate

**Camunda Delegate:** `identifyGlosa`
**Categoria:** Gestão de Glosas (Negações) - Identificação
**Arquivo:** `IdentifyGlosaDelegate.java`

## Descrição

Identifica glosas (negações de cobrança) comparando pagamento recebido vs. valor esperado. Este é o **ponto de entrada** do processo de gestão de glosas, responsável por detectar quando uma operadora pagou menos que o esperado ou negou completamente uma cobrança.

## Dados de Entrada (Input)

| Variável | Tipo | Obrigatório | Descrição |
|----------|------|-------------|-----------|
| `claimId` | String | Sim | Identificador único da cobrança |
| `paymentReceived` | BigDecimal/Double | Sim | Valor efetivamente recebido da operadora |
| `expectedAmount` | BigDecimal/Double | Sim | Valor esperado para pagamento |

**Nota:** Suporta múltiplos tipos numéricos (BigDecimal, Double, Integer, Long, String) para flexibilidade de integração.

## Dados de Saída (Output)

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `glosaIdentified` | Boolean | `true` se glosa foi identificada |
| `glosaAmount` | BigDecimal | Valor da glosa (diferença entre esperado e recebido) |
| `glosaType` | String | Tipo de glosa classificada |

**Escopo das Variáveis:** PROCESS (disponíveis para todo o processo de gestão de glosas)

## Regras de Negócio

### Fórmula de Cálculo da Glosa

```
glosaAmount = expectedAmount - paymentReceived
```

**Exemplo:**
- Expected: R$ 1.000,00
- Received: R$ 700,00
- Glosa: R$ 300,00

### Tolerância para Arredondamento

**Threshold:** 1% do valor esperado

```
tolerance = expectedAmount × 0.01
```

**Aplicação:**
- Se `|glosaAmount| ≤ tolerance`: Considerado dentro da tolerância (não é glosa)
- Se `|glosaAmount| > tolerance`: Glosa identificada

**Justificativa:** Evita falsos positivos causados por diferenças de arredondamento ou ajustes contratuais pequenos.

### Classificação de Glosas

#### 1. NO_GLOSA
**Condição:** Diferença dentro da tolerância de 1%
**Exemplo:** Expected: R$ 1.000, Received: R$ 995 → Diferença de 0,5% → NO_GLOSA

#### 2. FULL_DENIAL
**Condição:** `paymentReceived = 0`
**Significado:** Operadora negou completamente a cobrança
**Exemplo:** Expected: R$ 1.000, Received: R$ 0 → FULL_DENIAL

#### 3. OVERPAYMENT
**Condição:** `paymentReceived > expectedAmount` (além da tolerância)
**Significado:** Operadora pagou mais que o esperado
**Exemplo:** Expected: R$ 1.000, Received: R$ 1.100 → OVERPAYMENT
**Ação:** Investigar e possivelmente reembolsar diferença

#### 4. PARTIAL_DENIAL
**Condição:** `paymentReceived < 50% × expectedAmount`
**Significado:** Negação significativa - menos de metade paga
**Exemplo:** Expected: R$ 1.000, Received: R$ 400 → PARTIAL_DENIAL
**Criticidade:** Alta - requer análise detalhada

#### 5. UNDERPAYMENT
**Condição:** `50% × expectedAmount ≤ paymentReceived < expectedAmount` (além da tolerância)
**Significado:** Pagamento parcial - mais de metade paga
**Exemplo:** Expected: R$ 1.000, Received: R$ 800 → UNDERPAYMENT
**Criticidade:** Média - pode ser ajuste contratual

## Validações

### Validação de Valores

```java
// Claim ID não pode ser nulo ou vazio
if (claimId == null || claimId.trim().isEmpty()) {
    throw new BpmnError("INVALID_CLAIM_DATA", "Claim ID is required");
}

// Pagamento recebido não pode ser negativo
if (paymentReceived < 0) {
    throw new BpmnError("INVALID_AMOUNT",
        "Payment received cannot be negative");
}

// Valor esperado deve ser positivo
if (expectedAmount <= 0) {
    throw new BpmnError("INVALID_AMOUNT",
        "Expected amount must be positive");
}
```

## Exceções e Erros BPMN

### INVALID_CLAIM_DATA
**Quando:** Claim ID ausente ou inválido
**Mensagem:** "Claim ID is required"

### INVALID_AMOUNT
**Quando:**
- Pagamento recebido negativo
- Valor esperado zero ou negativo
- Tipo de dado não suportado
- String não conversível para número

**Mensagens:**
- "Payment received cannot be negative: {value}"
- "Expected amount must be positive: {value}"
- "Amount variable '{name}' is required"
- "Amount variable '{name}' cannot be parsed: {value}"
- "Amount variable '{name}' has unsupported type: {type}"

## Exemplo de Fluxo

### Cenário 1: Glosa Identificada (UNDERPAYMENT)

```
Input:
  claimId: "CLM-12345"
  expectedAmount: 1000.00
  paymentReceived: 750.00

Processing:
  1. Calcular glosa: 1000 - 750 = 250
  2. Calcular tolerância: 1000 × 0.01 = 10
  3. Verificar: |250| > 10 → Fora da tolerância
  4. Classificar: 750 / 1000 = 75% → > 50% → UNDERPAYMENT

Output:
  glosaIdentified: true
  glosaAmount: 250.00
  glosaType: "UNDERPAYMENT"
```

### Cenário 2: Dentro da Tolerância (NO_GLOSA)

```
Input:
  claimId: "CLM-67890"
  expectedAmount: 1000.00
  paymentReceived: 995.00

Processing:
  1. Calcular glosa: 1000 - 995 = 5
  2. Calcular tolerância: 1000 × 0.01 = 10
  3. Verificar: |5| ≤ 10 → Dentro da tolerância

Output:
  glosaIdentified: false
  glosaAmount: 5.00
  glosaType: "NO_GLOSA"
```

### Cenário 3: Negação Total (FULL_DENIAL)

```
Input:
  claimId: "CLM-11111"
  expectedAmount: 5000.00
  paymentReceived: 0.00

Processing:
  1. Calcular glosa: 5000 - 0 = 5000
  2. Verificar: paymentReceived = 0 → Negação total

Output:
  glosaIdentified: true
  glosaAmount: 5000.00
  glosaType: "FULL_DENIAL"
```

## Conversão de Tipos

O delegate aceita múltiplos tipos numéricos e os converte para BigDecimal:

```java
Object value = execution.getVariable("paymentReceived");

if (value instanceof BigDecimal) → Uso direto
if (value instanceof Double) → BigDecimal.valueOf()
if (value instanceof Integer) → BigDecimal.valueOf()
if (value instanceof Long) → BigDecimal.valueOf()
if (value instanceof String) → new BigDecimal(string)
```

## Idempotência

**requiresIdempotency():** `false`

Identificação é operação **read-only** e naturalmente idempotente - pode ser executada múltiplas vezes sem efeitos colaterais.

## Auditoria e Logging

### Eventos Logados

**INFO:**
- Início da identificação: `"Starting glosa identification for claim: {businessKey}"`
- Resultado positivo: `"Glosa identified for claim {}: Type={}, Amount={}, Expected={}, Received={}"`
- Resultado negativo: `"No glosa identified for claim {}: Expected={}, Received={}, Difference={}"`

**WARN:**
- Quando glosa é identificada (requer atenção)

## KPIs e Métricas

### Métricas Operacionais
- **Taxa de Glosa**: % de cobranças com glosa identificada
- **Valor Médio de Glosa**: Por tipo e por operadora
- **Distribuição por Tipo**: Contagem de cada tipo de glosa

### Métricas Financeiras
- **Valor Total de Glosas**: Por período
- **Taxa de Glosa Financeira**: (Total Glosas / Total Cobrado) × 100%
- **Impacto por Operadora**: Valor de glosas por payer

### Indicadores de Qualidade
- **Falsos Positivos**: Glosas identificadas mas depois validadas
- **Tempo Médio de Detecção**: Entre pagamento e identificação

## Integração no Processo BPMN

### Variáveis de Roteamento

O delegate define variáveis que podem ser usadas em gateways:

```xml
<sequenceFlow id="flow1" sourceRef="identifyGlosa" targetRef="gateway1" />

<exclusiveGateway id="gateway1" name="Glosa identificada?" />

<sequenceFlow id="flow2" sourceRef="gateway1" targetRef="analyzeGlosa">
  <conditionExpression xsi:type="tFormalExpression">
    ${glosaIdentified == true}
  </conditionExpression>
</sequenceFlow>

<sequenceFlow id="flow3" sourceRef="gateway1" targetRef="endEvent">
  <conditionExpression xsi:type="tFormalExpression">
    ${glosaIdentified == false}
  </conditionExpression>
</sequenceFlow>
```

## Considerações Importantes

1. **Sensibilidade**: Ajuste de tolerância de 1% equilibra detecção vs. falsos positivos
2. **Performance**: Operação leve e rápida - apenas cálculos matemáticos
3. **Precisão**: Uso de BigDecimal garante precisão monetária
4. **Flexibilidade**: Aceita múltiplos tipos de entrada para facilitar integrações
5. **Auditoria**: Todas as decisões são logadas para rastreabilidade

## Evolução Futura

Possíveis melhorias:
- Tolerância configurável por operadora
- Machine learning para detecção de padrões anômalos
- Análise histórica para ajuste automático de threshold
- Integração com sistema de alertas em tempo real

## Versionamento

- **Versão Atual:** 1.0
- **Última Atualização:** 2025-12-23
- **Autor:** Revenue Cycle Development Team
