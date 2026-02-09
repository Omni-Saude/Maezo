# RN-GLOSA-005: Identificação de Glosas por Comparação de Pagamento

## I. Identificação da Regra

**Código**: RN-GLOSA-005
**Nome**: Identificação de Glosas por Comparação de Pagamento
**Versão**: 1.0.0
**Módulo**: Gestão de Glosas
**Processo de Negócio**: Identificação e Classificação de Negações
**Data de Criação**: 2026-01-12
**Última Atualização**: 2026-01-12
**Autor**: Equipe de Revenue Cycle

## II. Definição e Propósito

### Definição
Define o processo automatizado de identificação de glosas através da comparação entre valor de pagamento recebido e valor esperado, incluindo cálculo de diferenças, aplicação de tolerâncias e classificação de tipos de glosa.

### Propósito
Garantir detecção precisa e imediata de todas as discrepâncias de pagamento, minimizando perdas financeiras através de identificação tempestiva e classificação correta para processos subsequentes de recuperação.

### Escopo
Aplica-se a todos os pagamentos recebidos de operadoras de saúde, públicas e privadas, com threshold de tolerância de 1% para compensar erros de arredondamento.

## III. Descrição da Lógica de Negócio

### Fluxo Principal

1. **Extração e Validação de Valores**
   - Sistema recupera ID da conta, valor recebido e valor esperado
   - Sistema converte valores para BigDecimal padronizado
   - Sistema valida tipos de dados e domínios permitidos

2. **Cálculo de Diferença**
   - Sistema calcula: `glosa_amount = valor_esperado - valor_recebido`
   - Sistema aplica precisão decimal para cálculos monetários

3. **Aplicação de Tolerância de Arredondamento**
   - Sistema calcula tolerância: `tolerância = valor_esperado × 1%`
   - Sistema verifica se diferença absoluta está dentro da tolerância
   - Sistema evita falsos positivos por centavos de diferença

4. **Determinação de Ocorrência de Glosa**
   - SE diferença > tolerância E diferença > 0 ENTÃO glosa identificada
   - Sistema marca `glosaIdentified = true/false`

5. **Classificação do Tipo de Glosa**
   - Sistema classifica baseado em padrão de pagamento:
     - Pagamento zero → FULL_DENIAL (negação total)
     - Pagamento > esperado → OVERPAYMENT (sobrepagamento)
     - Pagamento < 50% → PARTIAL_DENIAL (negação parcial significativa)
     - Pagamento 50-100% → UNDERPAYMENT (subpagamento)
     - Dentro de tolerância → NO_GLOSA

6. **Registro de Resultados**
   - Sistema define variáveis de processo: glosaIdentified, glosaAmount, glosaType
   - Sistema registra decisão em log estruturado com todos os valores

### Regras de Decisão

**RD-001: Cálculo de Tolerância**
```
tolerância_permitida = valor_esperado × 0.01  // 1%
diferença_absoluta = ABS(valor_esperado - valor_recebido)
dentro_tolerância = diferença_absoluta ≤ tolerância_permitida
```

**RD-002: Classificação de Tipo de Glosa**
```
tipo_glosa = CASO
  QUANDO dentro_tolerância ENTÃO "NO_GLOSA"
  QUANDO valor_recebido = 0 ENTÃO "FULL_DENIAL"
  QUANDO valor_recebido > valor_esperado ENTÃO "OVERPAYMENT"
  QUANDO (valor_recebido / valor_esperado) < 0.50 ENTÃO "PARTIAL_DENIAL"
  QUANDO (valor_recebido / valor_esperado) ≥ 0.50 ENTÃO "UNDERPAYMENT"
FIM CASO
```

**RD-003: Identificação de Glosa**
```
glosa_identificada = NÃO dentro_tolerância E diferença > 0
```

## IV. Variáveis e Parâmetros

### Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| claimId | String | Sim | Identificador único da conta |
| paymentReceived | BigDecimal | Sim | Valor efetivamente pago pela operadora |
| expectedAmount | BigDecimal | Sim | Valor esperado conforme faturamento |

### Variáveis de Saída
| Nome | Tipo | Descrição |
|------|------|-----------|
| glosaIdentified | Boolean | Indica se glosa foi identificada |
| glosaAmount | BigDecimal | Valor monetário da glosa (diferença) |
| glosaType | String | Tipo de glosa classificado |

### Parâmetros de Configuração
| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| TOLERANCE_PERCENTAGE | 0.01 (1%) | Percentual de tolerância para arredondamento |
| PARTIAL_DENIAL_THRESHOLD | 0.50 (50%) | Limite para classificar negação parcial |

## V. Cálculos e Fórmulas

### Cálculo Principal de Glosa
```
glosa_amount = expected_amount - payment_received
```

### Cálculo de Tolerância
```
tolerance = expected_amount × TOLERANCE_PERCENTAGE
tolerance_absolute = expected_amount × 0.01
```

### Cálculo de Percentual de Pagamento
```
payment_percentage = (payment_received / expected_amount) × 100
```

### Classificação por Percentual
```
classification = CASO
  QUANDO payment_percentage = 0% ENTÃO "FULL_DENIAL"
  QUANDO payment_percentage < 50% ENTÃO "PARTIAL_DENIAL"
  QUANDO payment_percentage < 100% ENTÃO "UNDERPAYMENT"
  QUANDO payment_percentage ≥ 100% ENTÃO "OVERPAYMENT"
FIM CASO
```

## VI. Validações e Restrições

### Validações de Entrada
- **VLD-001**: ID da conta não pode ser nulo ou vazio
- **VLD-002**: Valor recebido deve ser ≥ 0
- **VLD-003**: Valor esperado deve ser > 0
- **VLD-004**: Valores devem ser conversíveis para BigDecimal

### Restrições de Negócio
- **RST-001**: Identificação é operação read-only (não altera dados de origem)
- **RST-002**: Cálculos devem usar precisão decimal apropriada para valores monetários
- **RST-003**: Tolerância de 1% é fixa para todos os tipos de conta

## VII. Exceções e Tratamento de Erros

### Códigos de Erro BPMN
| Código | Descrição | Tratamento |
|--------|-----------|------------|
| INVALID_CLAIM_DATA | Dados da conta inválidos | Interrompe fluxo, solicita correção |
| INVALID_AMOUNT | Valor monetário inválido | Interrompe fluxo, registra erro |

### Cenários de Exceção
**EXC-001**: Valor esperado zero ou negativo → Erro INVALID_AMOUNT
**EXC-002**: Valor recebido negativo → Erro INVALID_AMOUNT
**EXC-003**: Tipo de dado incompatível → Tenta conversão, falha se impossível

## VIII. Integrações de Sistemas

### Sistemas Integrados
| Sistema | Tipo | Dados Trocados |
|---------|------|----------------|
| Sistema de Pagamentos | Entrada | Valor recebido de operadora |
| Sistema de Faturamento | Entrada | Valor esperado conforme conta |
| Workflow Orchestrator | Saída | Resultado de identificação para roteamento |

## IX. Indicadores de Performance (KPIs)

| KPI | Métrica | Meta | Descrição |
|-----|---------|------|-----------|
| Taxa de Detecção | % | 100% | Percentual de glosas reais detectadas |
| Falsos Positivos | % | < 0.1% | Glosas identificadas mas inexistentes |
| Tempo de Identificação | ms | < 100ms | Latência do processo de identificação |
| Acurácia de Classificação | % | 98% | Correção na classificação de tipo |

## X. Conformidade Regulatória

**ANS - Resolução Normativa 395/2016**
- Art. 17: Transparência em negações de pagamento
- Conformidade: Sistema registra todas as diferenças identificadas

**TISS - Padrão TISS 4.0**
- Seção 2.3: Demonstrativo de Retorno de Guia
- Conformidade: Sistema classifica conforme padrão TISS

**CPC 48 - Instrumentos Financeiros**
- Reconhecimento de receita e ajustes
- Conformidade: Sistema identifica discrepâncias tempestivamente

## XI. Notas de Migração

### Migração Camunda 7 → Camunda 8

**Complexidade**: 6/10 (Média)

**Impactos**:
1. **Variáveis BigDecimal**: Camunda 8 requer serialização JSON → usar Double ou String
2. **Idempotência**: Já naturalmente idempotente (read-only)
3. **Erros BPMN**: Converter para exceções de job Zeebe

**Esforço**: 8-12 horas

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Nome**: Identificação de Glosas (Glosa Detection)

### Agregados
- **Agregado Principal**: Comparação de Pagamento
- **Entidades**: Comparação (raiz), Resultado de Identificação
- **Value Objects**: Valor Monetário, Tipo de Glosa, Tolerância

### Eventos de Domínio
| Evento | Descrição | Dados |
|--------|-----------|-------|
| GlosaIdentificada | Glosa foi detectada | claimId, amount, type, timestamp |
| PagamentoValidado | Pagamento dentro da tolerância | claimId, expectedAmount, receivedAmount |
| SobrepagamentoDetectado | Operadora pagou valor excedente | claimId, overpaymentAmount |

### Linguagem Ubíqua
- **Glosa**: Diferença não justificada entre esperado e recebido
- **Tolerância**: Margem aceitável para arredondamento (1%)
- **Negação Total**: Nenhum pagamento efetuado
- **Subpagamento**: Pagamento parcial acima de 50%

## XIII. Metadados Técnicos

### Informações de Implementação
| Atributo | Valor |
|----------|-------|
| Classe Java | `IdentifyGlosaDelegate` |
| Bean Spring | `identifyGlosa` |
| Camunda Task Type | Service Task |
| Idempotência | Não requerida (naturalmente idempotente) |
| Escopo de Variáveis | PROCESS |

### Estatísticas de Código
| Métrica | Valor |
|---------|-------|
| Linhas de Código | 225 |
| Complexidade Ciclomática | 5/10 |
| Cobertura de Testes | 90% |

### Performance
| Métrica | Esperado | Crítico |
|---------|----------|---------|
| Tempo de Execução | 30-80ms | > 200ms |
| Uso de Memória | < 10MB | > 50MB |
| Throughput | 1000 identificações/min | < 200/min |

### Tags de Busca
`glosa`, `identificação`, `comparação`, `pagamento`, `tolerância`, `classificação`, `negação`, `detection`, `payment-reconciliation`

---

**Próxima Revisão**: 2026-04-12
**Criticidade**: ALTA
