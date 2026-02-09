# RN-BIL-005: Processamento de Pagamento e Cálculo de Balanço

**ID Técnico**: `ProcessPaymentDelegate`
**Processo BPMN**: SUB_08 - Processo de Arrecadação de Receita
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Registrar pagamento recebido de operadora de saúde, calcular balanço remanescente, classificar tipo de pagamento (integral, parcial ou glosa), e registrar em sistema financeiro para análise de glosas e decisões de cobrança.

### 1.2. Contexto de Negócio
Pagamentos de operadoras raramente correspondem ao valor integral da cobrança. Podem incluir descontos contratuais, glosas (negações de cobertura), ajustes administrativos ou ser parciais por indisponibilidade de fundos. Sistema deve rastrear cada pagamento, identificar glosas para análise, e calcular saldo remanescente para ações de cobrança complementares.

### 1.3. Benefícios Esperados
- **Precisão Financeira**: Rastreamento exato de receita realizada vs. esperada
- **Identificação de Glosas**: Segregação de valores negados para análise
- **Auditoria**: Registro completo de cada pagamento
- **Decisão Orientada por Dados**: Informações para retry, glosa ou write-off

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
Sistema deve validar dados de pagamento, recuperar informação original de cobrança, determinar se foi integral/parcial/glosa, calcular saldo remanescente, registrar em sistema financeiro e determinar próximas ações (cobrança de glosa, análise de parcialidade, encerramento).

**Lógica de Execução**:

1. **Validação de Dados de Pagamento**
   - Validar formato claimId
   - Validar valor do pagamento (positivo, formato)
   - Validar data do pagamento (não futura)

2. **Recuperação de Cobrança Original**
   ```
   claimInfo ← getDatabaseClaim(claimId)

   SE claimInfo não existe:
     LANÇAR ERRO "CLAIM_NOT_FOUND"

   claimAmount ← claimInfo.amount
   claimStatus ← claimInfo.status
   ```

3. **Validação de Elegibilidade para Pagamento**
   ```
   validStatusForPayment = [SUBMITTED, PENDING, PARTIALLY_PAID]

   SE claimStatus NÃO ESTÁ EM validStatusForPayment:
     LANÇAR ERRO "INVALID_CLAIM_STATUS"
   ```

4. **Cálculo de Detalhes de Pagamento**
   ```
   remainingBalance ← claimAmount - paymentAmount

   SE paymentAmount == claimAmount:
     paymentType ← "FULL"
     glosaAmount ← 0
     remainingBalance ← 0

   SENÃO SE paymentAmount == 0:
     paymentType ← "GLOSA"
     glosaAmount ← claimAmount
     remainingBalance ← claimAmount

   SENÃO SE paymentAmount < claimAmount:
     paymentType ← "PARTIAL"
     glosaAmount ← remainingBalance
     // remainingBalance já calculado acima

   SENÃO (paymentAmount > claimAmount):
     paymentType ← "FULL"
     glosaAmount ← 0
     remainingBalance ← 0
     LOG AVISO: "Overpayment: payment > claim"
   ```

5. **Atualização de Status de Cobrança**
   ```
   SE paymentType == "FULL":
     newStatus ← "PAID"
   SENÃO SE paymentType == "GLOSA":
     newStatus ← "DENIED"
   SENÃO:
     newStatus ← "PARTIALLY_PAID"

   updateDatabaseClaimStatus(claimId, newStatus, paymentAmount, paymentDate)
   ```

6. **Registro em Sistema Financeiro**
   - Criar registro de pagamento
   - Registrar glosa se aplicável
   - Atualizar ledger financeiro
   - Registrar em auditoria

7. **Saída de Variáveis**
   - paymentProcessed: true se sucesso
   - remainingBalance: saldo não pago
   - paymentType: FULL|PARTIAL|GLOSA
   - glosaAmount: valor negado

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-005-V1 | claimId deve estar em formato válido | CRÍTICA | Rejeitar com CLAIM_NOT_FOUND |
| BIL-005-V2 | Cobrança deve existir no banco de dados | CRÍTICA | Rejeitar com CLAIM_NOT_FOUND |
| BIL-005-V3 | Status deve permitir pagamento | CRÍTICA | Rejeitar com INVALID_CLAIM_STATUS |
| BIL-005-V4 | paymentAmount deve ser não-negativo | CRÍTICA | Rejeitar com INVALID_PAYMENT_AMOUNT |
| BIL-005-V5 | paymentDate não pode ser futura | CRÍTICA | Rejeitar com INVALID_PAYMENT_AMOUNT |
| BIL-005-V6 | paymentAmount não pode duplicar pagamento | CRÍTICA | Rejeitar com DUPLICATE_PAYMENT |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- claimId corresponde a cobrança já submetida
- paymentAmount >= 0
- paymentDate é válida (não futura)
- claimStatus permite pagamento

**Exceções de Negócio**:

1. **Cobrança Não Encontrada**
   - **Código**: CLAIM_NOT_FOUND
   - **Ação**: Rejeitar pagamento
   - **Próximo Passo**: Investigação de matching

2. **Status Inválido**
   - **Código**: INVALID_CLAIM_STATUS
   - **Ação**: Rejeitar pagamento
   - **Próximo Passo**: Verificação de histórico de cobrança

3. **Pagamento Duplicado**
   - **Código**: DUPLICATE_PAYMENT
   - **Ação**: Rejeitar pagamento
   - **Próximo Passo**: Análise de reconciliação

4. **Erro de Processamento**
   - **Código**: PAYMENT_PROCESSING_ERROR
   - **Ação**: Rollback de atualizações
   - **Próximo Passo**: Retry ou investigação

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `claimId` | String | Sim | Identificador da cobrança | Formato válido |
| `paymentAmount` | BigDecimal | Sim | Valor recebido da operadora | Não-negativo, até 2 decimais |
| `paymentDate` | LocalDate | Sim | Data que operadora processou pagamento | Não futura |

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `paymentProcessed` | Boolean | Se pagamento foi processado com sucesso | Condição de gateway |
| `remainingBalance` | BigDecimal | Saldo não pago (glosa + parcial) | Análise de cobrança |
| `paymentType` | String | FULL, PARTIAL, GLOSA | Rota para próximo passo |
| `glosaAmount` | BigDecimal | Valor de glosa (negação) | Análise de glosa |
| `paymentProcessedDate` | LocalDateTime | Timestamp de processamento | Auditoria |

---

## IV. Fórmulas e Cálculos

### 4.1. Cálculo de Balanço Remanescente

```
Entrada:
  claimAmount = valor original da cobrança
  paymentAmount = valor recebido

Cálculo:
  remainingBalance = claimAmount - paymentAmount

Validação:
  SE remainingBalance < 0:
    remainingBalance ← 0
    glosaAmount ← 0
  SENÃO:
    glosaAmount ← remainingBalance
```

### 4.2. Matriz de Classificação de Pagamento

```
┌──────────────────────────────────────────────────────┐
│ Classificação de Tipo de Pagamento                  │
├──────────────────────────────────────────────────────┤
│                                                      │
│ paymentAmount = claimAmount                        │
│   → FULL (Pagamento integral)                      │
│   → remainingBalance = 0                           │
│   → glosaAmount = 0                                │
│   → newStatus = PAID                               │
│                                                      │
│ paymentAmount = 0                                  │
│   → GLOSA (Negação completa)                       │
│   → remainingBalance = claimAmount                 │
│   → glosaAmount = claimAmount                      │
│   → newStatus = DENIED                             │
│                                                      │
│ 0 < paymentAmount < claimAmount                   │
│   → PARTIAL (Pagamento parcial com glosa)         │
│   → remainingBalance = claimAmount - paymentAmount │
│   → glosaAmount = remainingBalance                 │
│   → newStatus = PARTIALLY_PAID                     │
│                                                      │
│ paymentAmount > claimAmount                       │
│   → FULL (Caso excepcional: overpayment)          │
│   → remainingBalance = 0                           │
│   → glosaAmount = 0                                │
│   → newStatus = PAID                               │
│   → Nota: Log warning                              │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 4.3. Arredondamento Financeiro

```
Regra: Arredondar para 2 casas decimais (centavos)
Método: HALF_UP (meio para cima)

Exemplo:
  claimAmount = R$ 1.000,00
  paymentAmount = R$ 666,67
  remainingBalance = 1.000,00 - 666,67 = 333,33
  glosaAmount = 333,33
```

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| Banco de Dados de Cobrança | Consulta/Atualização | Dados de cobrança | JDBC/ORM |
| Sistema Financeiro | Escrita | Registro de pagamento | API/Message Queue |
| Glosa Management | Escrita | Registros de glosa | API/Database |
| Auditoria | Escrita | Log de pagamento | Message Queue |
| Receivables Aging | Atualização | Status atualizado | API/Database |

### 5.2. Dependências de Dados

**Dados Externos Requeridos**:
- Cadastro de cobrança com valores originais
- Status atual de cobrança
- Histórico de pagamentos anteriores (para duplicatas)
- Tabela de procedimentos (para análise)

**Frequência de Atualização**:
- Status de cobrança: Real-time
- Dados de pagamento: Real-time
- Histórico: Permanente

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Índice de Cobertura de Pagamento | % do valor submetido que foi pago | ≥ 85% | (Total Pago / Total Submetido) × 100 | Diária |
| Taxa de Glosa | % do valor submetido que foi negado | ≤ 15% | (Total Glosa / Total Submetido) × 100 | Semanal |
| Taxa de Pagamento Integral | % de cobranças com pagamento 100% | ≥ 75% | (Full / Total) × 100 | Diária |
| Taxa de Pagamento Parcial | % de cobranças com pagamento parcial | ≤ 20% | (Partial / Total) × 100 | Semanal |
| Dias para Recebimento | Dias entre submissão e pagamento | ≤ 30 | Média de (paymentDate - submissionDate) | Mensal |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Erros CLAIM_NOT_FOUND | Cobranças não encontradas | > 5% | Investigar matching |
| Erros DUPLICATE_PAYMENT | Tentativas de pagamento duplicado | > 1% | Revisar reconciliação |
| Tempo Processamento | Latência de processamento | > 500ms | Otimizar consultas |
| Taxa de Erro Geral | % pagamentos com erro | > 2% | Investigar infraestrutura |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Validação de dados de pagamento
2. Recuperação de cobrança original
3. Validação de elegibilidade
4. Cálculo de detalhes
5. Atualização de status
6. Criação de registro financeiro

**Informações Capturadas**:
```json
{
  "timestamp": "data_hora_processamento",
  "claimId": "identificador_cobranca",
  "claimAmount": valor_original,
  "paymentAmount": valor_recebido,
  "paymentDate": data_pagamento,
  "paymentType": "FULL|PARTIAL|GLOSA",
  "remainingBalance": saldo_remanescente,
  "glosaAmount": valor_negado,
  "newStatus": "status_atualizado",
  "processingTimeMs": tempo_processamento,
  "userId": "sistema"
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação de Dados | Preventivo | Por pagamento | Sistema |
| Verificação de Duplicata | Preventivo | Por pagamento | Sistema |
| Cálculo de Glosa | Detectivo | Por pagamento | Sistema |
| Reconciliação Diária | Detectivo | Diária | Financeiro |
| Revisão de Anomalias | Corretivo | Semanal | Gestão Financeira |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| CLAIM_NOT_FOUND | Cobrança não existe no banco | CRÍTICA | Investigar matching, reenviar cobrança |
| INVALID_CLAIM_STATUS | Status não permite pagamento | CRÍTICA | Revisar histórico de cobrança |
| INVALID_PAYMENT_AMOUNT | Valor inválido (negativo, futura) | CRÍTICA | Devolver ao remetente para correção |
| DUPLICATE_PAYMENT | Pagamento já recebido | CRÍTICA | Análise de reconciliação |
| PAYMENT_PROCESSING_ERROR | Erro ao registrar pagamento | CRÍTICA | Rollback, retry ou investigação |

### 8.2. Estratégia de Recuperação

**Para Erros Transientes** (erro do sistema):
- Retry automático até 3 vezes
- Intervalo: 1s, 2s, 4s
- Se continuar falhar: escalar para gestão

**Para Erros de Dados** (validação falha):
- Sem retry automático
- Registro do erro
- Notificação ao remetente
- Análise manual

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Pagamento Integral Bem-Sucedido

**Cenário**: Operadora paga 100% do valor da cobrança

**Pré-condições**:
- Cobrança foi submetida e pendente de pagamento
- Operadora recebe e processa
- Operadora envia pagamento integral

**Fluxo**:
1. Sistema recebe claimId, paymentAmount = claimAmount, paymentDate
2. Valida dados de pagamento
3. Recupera cobrança original (ex: R$ 1.500,00)
4. Valida status = SUBMITTED ✓
5. Calcula: remainingBalance = 1.500 - 1.500 = 0
6. Classifica: paymentType = FULL
7. Atualiza status: PAID
8. Registra pagamento em sistema financeiro
9. Retorna: paymentProcessed=true, paymentType=FULL, remainingBalance=0

**Pós-condições**:
- Cobrança marcada como PAID
- Receita realizada contabilizada
- Disponível para relatórios financeiros

**Resultado**: Sucesso, cobrança encerrada

### 9.2. Fluxo Alternativo - Pagamento Parcial com Glosa

**Cenário**: Operadora paga parcialmente por desacordo de cobertura

**Fluxo**:
1. Sistema recebe claimId, paymentAmount = R$ 1.000,00, paymentDate
2. Recupera cobrança = R$ 1.500,00
3. Calcula:
   - remainingBalance = 1.500 - 1.000 = R$ 500,00
   - glosaAmount = R$ 500,00
4. Classifica: paymentType = PARTIAL
5. Atualiza status: PARTIALLY_PAID
6. Registra pagamento de R$ 1.000,00
7. Registra glosa de R$ 500,00 para análise
8. Retorna: paymentProcessed=true, paymentType=PARTIAL, remainingBalance=500, glosaAmount=500

**Próximos Passos**:
- Glosa enviada para AnalyzeGlosaDelegate
- Cobrança acompanhada até resolução ou write-off

**Resultado**: Sucesso, glosa identificada para análise

### 9.3. Fluxo de Exceção - Glosa Integral (Negação Completa)

**Cenário**: Operadora nega cobertura completamente

**Fluxo**:
1. Sistema recebe claimId, paymentAmount = 0 (negação), paymentDate
2. Recupera cobrança = R$ 2.000,00
3. Calcula:
   - remainingBalance = 2.000 - 0 = R$ 2.000,00
   - glosaAmount = R$ 2.000,00
4. Classifica: paymentType = GLOSA
5. Atualiza status: DENIED
6. Não registra pagamento
7. Registra glosa completa para análise
8. Retorna: paymentProcessed=true, paymentType=GLOSA, remainingBalance=2000, glosaAmount=2000

**Próximos Passos**:
- Escalação para AnalyzeGlosaDelegate
- Análise de motivo da glosa
- Decisão: aceitar, apelar ou corrigir

**Resultado**: Sucesso, glosa integral registrada

### 9.4. Fluxo de Erro - Cobrança Não Encontrada

**Cenário**: Pagamento chega para cobrança que não existe no cadastro

**Fluxo**:
1. Sistema recebe claimId = "CLM-INVALID-001"
2. Valida dados de pagamento ✓
3. Tenta recuperar cobrança
4. Não encontra no banco de dados
5. Lança CLAIM_NOT_FOUND
6. Suspende pagamento
7. Notifica gestão para investigação de matching

**Próximos Passos**:
- Análise de mismatch
- Verificação de claimId correto
- Possível reenvio com claimId correto

**Resultado**: Erro, requer investigação

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS RN 395/2016 | Art. 5º | Registro de pagamento | Cada pagamento registrado com detalhes |
| ANS RN 395/2016 | Art. 7º | Transparência em valores | Glosas segregadas para análise |
| Lei 5.764/71 | Art. 112 | Controle de receita | Auditoria completa de pagamentos |
| LGPD Art. 16º | - | Segurança de dados financeiros | Criptografia e access control |
| LGPD Art. 18º | Inciso II | Acesso aos registros | Histórico de pagamentos consultável |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Recebimento de pagamento: Interface externa (ANS/sistema)
- Processamento: Sistema automático
- Auditoria: Sistema de auditoria
- Resolução de glosa: Gestão de Faturamento

**Retenção de Dados**:
- Registro de pagamento: Permanente
- Glosas: 5 anos (conforme legislação)
- Logs de auditoria: 5 anos
- Extratos financeiros: 5 anos

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para JobWorker |
| Transações | Controle manual | Zeebe management | Remover controle explícito |
| Variáveis | setVariable() | Zeebe API | Adaptar gestão |
| Idempotência | Manual | JobKey automático | Usar claimId |

### 11.2. Estratégia de Migração

**Fase 1 - Camunda 8 JobWorker**:
```java
@JobWorker(type = "process-payment")
public ProcessPaymentResponse handle(
    @Variable String claimId,
    @Variable BigDecimal paymentAmount,
    @Variable LocalDate paymentDate
) {
    // Validação
    validatePaymentData(claimId, paymentAmount, paymentDate);

    // Recuperação
    ClaimInfo claim = getClaimInformation(claimId);
    validateClaimEligibility(claimId, claim.getStatus());

    // Cálculo
    Map<String, Object> details = calculatePaymentDetails(
        claim.getAmount(), paymentAmount);

    // Atualização
    updateClaimPaymentStatus(claimId, paymentAmount,
        paymentDate, details);

    return new ProcessPaymentResponse(
        true,
        (BigDecimal) details.get("remainingBalance"),
        (String) details.get("paymentType"),
        (BigDecimal) details.get("glosaAmount"),
        LocalDateTime.now()
    );
}
```

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Revenue Collection (Arrecadação de Receita)
**Sub-domínio**: Payment Processing & Denial Management
**Responsabilidade**: Registrar pagamento e identificar glosas

### 12.2. Agregados e Entidades

```
PaymentRecord (Aggregate Root)
├── ClaimId (Value Object)
├── OriginalClaim (Entity Reference)
│   └── claimAmount: Money
├── Payment (Entity)
│   ├── paymentAmount: Money
│   ├── paymentDate: LocalDate
│   ├── paymentType: PaymentType
│   └── receivedFrom: InsuranceId
├── Denial (Entity - se aplicável)
│   ├── denialAmount: Money
│   ├── denialReason: String
│   └── denialDate: LocalDate
└── ClaimStatus (Value Object)
    └── PAID | PARTIALLY_PAID | DENIED
```

### 12.3. Domain Events

```
PaymentProcessedEvent
├── claimId: ClaimId
├── paymentAmount: Money
├── paymentDate: LocalDate
├── paymentType: PaymentType
├── remainingBalance: Money
└── timestamp: Instant

DenialRegisteredEvent
├── claimId: ClaimId
├── denialAmount: Money
├── denialReason: String
├── timestamp: Instant
└── requiresAnalysis: Boolean
```

### 12.4. Value Objects

**PaymentType**: FULL | PARTIAL | GLOSA

```java
enum PaymentType {
    FULL("Pagamento integral"),
    PARTIAL("Pagamento parcial com glosa"),
    GLOSA("Negação completa");
}
```

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `ProcessPaymentDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `processPayment` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | Template Method, Strategy |
| **Complexidade Ciclomática** | 8 (Moderada) |
| **Linhas de Código** | 287 |
| **Cobertura de Testes** | 94% |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- ClaimValidationUtils
- DataAccessStrategy (futuro)

**Serviços Integrados**:
- PaymentService (futuro)
- DenialManagementService (futuro)
- AuditService (futuro)

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 5s | Consultas BD + cálculos |
| Pool de Threads | 15 | Baseado em throughput |
| Cache TTL (Claims) | 30 min | Dados estáveis |
| Batch Processing | 100 | Máximo de pagamentos por batch |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "payment_processed",
  "claimId": "CLM-ENC-001-1234567890",
  "claimAmount": 1500.00,
  "paymentAmount": 1000.00,
  "paymentType": "PARTIAL",
  "remainingBalance": 500.00,
  "glosaAmount": 500.00,
  "newStatus": "PARTIALLY_PAID",
  "executionTimeMs": 120,
  "timestamp": "2025-01-12T11:00:00Z"
}
```

**Métricas Prometheus**:
- `payment_processing_duration_seconds` (Histogram)
- `payment_processed_total` (Counter)
- `payment_by_type_total` (Counter by type)
- `denial_amount_total` (Counter)
- `recovery_rate` (Gauge: paid/submitted)

### 13.5. Testes

**Cenários de Teste**:
1. ✅ Pagamento integral (100%)
2. ✅ Pagamento parcial com glosa
3. ✅ Glosa integral (0%)
4. ✅ Overpayment (>100%)
5. ✅ Cobrança não encontrada
6. ✅ Status inválido para pagamento
7. ✅ Duplicate payment detection
8. ✅ Arredondamento correto de valores
9. ✅ Idempotência com mesmo claimId

---

## XIV. Glossário de Termos

| Termo | Definição |
|-------|-----------|
| **Pagamento Integral (Full)** | Operadora paga 100% do valor da cobrança |
| **Pagamento Parcial (Partial)** | Operadora paga parte do valor, glosa o restante |
| **Glosa (Denial)** | Operadora nega cobertura, não paga |
| **Saldo Remanescente** | Valor não pago (glosa + parcial) |
| **Overpayment** | Operadora paga acima do valor cobrado |
| **Balanço Financeiro** | Diferença entre submetido e recebido |

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor de Faturamento
- **Data de Aprovação**: 2025-12-23
