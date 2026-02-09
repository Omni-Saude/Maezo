# RN-BIL-004: Processamento de Pagamento

**ID Técnico**: `ProcessPaymentDelegate`
**Processo BPMN**: SUB_08 - Gestão de Receita e Cobrança
**Versão**: 1.0
**Data**: 2025-12-23

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra
Processar pagamentos recebidos de operadoras de saúde, atualizando o status financeiro das contas médicas, calculando saldos remanescentes, identificando glosas parciais ou totais, e atualizando registros financeiros.

### 1.2. Contexto de Negócio
Após a submissão de uma conta médica à operadora, o hospital recebe um retorno com o valor que será pago. Este valor pode ser:

- **Pagamento Integral (FULL)**: Operadora paga 100% do valor solicitado
- **Pagamento Parcial (PARTIAL)**: Operadora paga parte, glosando diferença
- **Glosa Total (GLOSA)**: Operadora não paga nada, negando a conta

O processamento correto do pagamento é crítico para:
- Atualizar corretamente os registros financeiros
- Identificar e rastrear glosas para análise e recurso
- Calcular valores a cobrar do paciente (coparticipação/diferenças)
- Gerar relatórios gerenciais de receita

### 1.3. Benefícios Esperados
- **Precisão Financeira**: Atualização correta de contas a receber
- **Gestão de Glosas**: Identificação automática de valores glosados
- **Rastreabilidade**: Histórico completo de pagamentos recebidos
- **Eficiência**: Automação reduz erros de lançamento manual
- **Análise**: Dados estruturados para KPIs financeiros

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
O sistema deve validar os dados do pagamento recebido, recuperar informações da conta médica, classificar o tipo de pagamento, calcular saldos remanescentes e valores glosados, atualizar status da conta e registros financeiros.

**Lógica de Execução**:

1. **Validação de Dados de Pagamento**
   ```
   VALIDAR:
     - claimId formato válido: CLM-.*-\d+
     - paymentAmount não é nulo
     - paymentAmount ≥ 0 (zero permitido para glosa total)
     - paymentDate não é nulo
     - paymentDate não é futura

   SE paymentAmount = 0:
     LOG AVISO "Processando pagamento zero (glosa total)"

   SE paymentDate > DATA_ATUAL:
     LANÇAR ERRO "INVALID_PAYMENT_AMOUNT"
   ```

2. **Recuperação de Informações da Conta**
   ```
   claim_info ← BUSCAR_CONTA(claimId)

   SE claim_info É NULO:
     LANÇAR ERRO "CLAIM_NOT_FOUND"

   claim_amount ← claim_info.claimAmount
   claim_status ← claim_info.status
   ```

3. **Validação de Elegibilidade para Pagamento**
   ```
   SE claim_status = "PAID":
     LANÇAR ERRO "DUPLICATE_PAYMENT"

   SE claim_status NÃO ESTÁ EM ["SUBMITTED", "PENDING"]:
     LANÇAR ERRO "PAYMENT_PROCESSING_ERROR"
   ```

4. **Classificação do Tipo de Pagamento**
   ```
   saldo_restante ← claim_amount - paymentAmount
   glosa_amount ← 0
   payment_type ← ""

   SE paymentAmount = claim_amount:
     payment_type ← "FULL"
     saldo_restante ← 0

   SENÃO SE paymentAmount = 0:
     payment_type ← "GLOSA"
     glosa_amount ← claim_amount
     saldo_restante ← claim_amount

   SENÃO SE paymentAmount < claim_amount:
     payment_type ← "PARTIAL"
     glosa_amount ← saldo_restante

   SENÃO:
     LOG AVISO "Sobrepagamento detectado"
     payment_type ← "FULL"
     saldo_restante ← 0
   ```

5. **Atualização de Status da Conta**
   ```
   novo_status ← ""

   SE payment_type = "FULL":
     novo_status ← "PAID"
   SENÃO SE payment_type = "GLOSA":
     novo_status ← "DENIED"
   SENÃO:
     novo_status ← "PARTIALLY_PAID"

   ATUALIZAR_CONTA(claimId, novo_status, paymentAmount, paymentDate)
   ```

6. **Registro Financeiro**
   ```
   SE glosa_amount > 0:
     CRIAR_REGISTRO_GLOSA(claimId, glosa_amount, paymentDate)

   ATUALIZAR_LEDGER_FINANCEIRO(claimId, paymentAmount, novo_status)
   ```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| BIL-004-V1 | Conta deve existir no sistema | CRÍTICA | Rejeitar com CLAIM_NOT_FOUND |
| BIL-004-V2 | Valor de pagamento não pode ser nulo | CRÍTICA | Rejeitar com INVALID_PAYMENT_AMOUNT |
| BIL-004-V3 | Valor de pagamento não pode ser negativo | CRÍTICA | Rejeitar com INVALID_PAYMENT_AMOUNT |
| BIL-004-V4 | Data de pagamento não pode ser futura | CRÍTICA | Rejeitar com INVALID_PAYMENT_AMOUNT |
| BIL-004-V5 | Conta não pode estar já paga | CRÍTICA | Rejeitar com DUPLICATE_PAYMENT |
| BIL-004-V6 | Status da conta deve permitir pagamento | CRÍTICA | Rejeitar com PAYMENT_PROCESSING_ERROR |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- Identificador de conta (claimId) válido e existente
- Conta em status "SUBMITTED" ou "PENDING"
- Valor de pagamento definido (pode ser zero)
- Data de pagamento válida

**Exceções de Negócio**:

1. **Conta Não Encontrada**
   - **Código**: CLAIM_NOT_FOUND
   - **Causa**: claimId inválido ou conta inexistente
   - **Ação**: Rejeitar processamento
   - **Próximo Passo**: Validar ID da conta no sistema de origem

2. **Valor de Pagamento Inválido**
   - **Código**: INVALID_PAYMENT_AMOUNT
   - **Causa**: Valor nulo, negativo, ou data futura
   - **Ação**: Rejeitar processamento
   - **Próximo Passo**: Corrigir dados do pagamento

3. **Pagamento Duplicado**
   - **Código**: DUPLICATE_PAYMENT
   - **Causa**: Tentativa de processar pagamento em conta já paga
   - **Ação**: Rejeitar processamento
   - **Próximo Passo**: Verificar histórico de pagamentos

4. **Erro no Processamento**
   - **Código**: PAYMENT_PROCESSING_ERROR
   - **Causa**: Status da conta não permite pagamento ou erro ao atualizar
   - **Ação**: Rejeitar processamento
   - **Próximo Passo**: Revisar fluxo do processo

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `claimId` | String | Sim | Identificador único da conta médica | Formato: CLM-.*-\d+ |
| `paymentAmount` | BigDecimal | Sim | Valor recebido da operadora | >= 0 |
| `paymentDate` | LocalDate | Sim | Data do pagamento | Não futura |

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `paymentProcessed` | Boolean | Indica se pagamento foi processado com sucesso | Controle de fluxo |
| `remainingBalance` | BigDecimal | Saldo remanescente após pagamento | Cobrança do paciente |
| `paymentType` | String | Tipo de pagamento (FULL, PARTIAL, GLOSA) | Análise e relatórios |
| `glosaAmount` | BigDecimal | Valor glosado pela operadora | Gestão de glosas |
| `paymentProcessedDate` | LocalDateTime | Data/hora do processamento | Auditoria |

**Estrutura de Resposta**:
```json
{
  "paymentProcessed": true,
  "paymentType": "PARTIAL",
  "claimAmount": 1500.00,
  "paymentAmount": 1200.00,
  "glosaAmount": 300.00,
  "remainingBalance": 300.00,
  "newStatus": "PARTIALLY_PAID",
  "paymentDate": "2025-01-10",
  "processedAt": "2025-01-12T10:30:00Z"
}
```

---

## IV. Fórmulas e Cálculos

### 4.1. Cálculo de Saldo Remanescente

```
Entrada:
  V_conta = Valor original da conta
  V_pago = Valor recebido da operadora

Cálculo:
  Saldo_Remanescente = V_conta - V_pago

Validação:
  SE Saldo_Remanescente < 0 ENTÃO
    Saldo_Remanescente ← 0  // Sobrepagamento

Saída:
  Saldo_Remanescente (BigDecimal)
```

**Exemplo**:
```
Valor da conta: R$ 1.500,00
Pagamento recebido: R$ 1.200,00
Saldo Remanescente = 1.500,00 - 1.200,00 = R$ 300,00
```

### 4.2. Cálculo de Valor Glosado

```
Entrada:
  V_conta = Valor original da conta
  V_pago = Valor recebido
  Tipo_Pagamento = Classificação

Cálculo:
  SE Tipo_Pagamento = "FULL":
    Glosa ← 0
  SENÃO SE Tipo_Pagamento = "GLOSA":
    Glosa ← V_conta
  SENÃO SE Tipo_Pagamento = "PARTIAL":
    Glosa ← V_conta - V_pago

Saída:
  Glosa (BigDecimal)
```

### 4.3. Taxa de Glosa

```
Para análise gerencial:

Taxa_Glosa = (Valor_Glosado / Valor_Conta) × 100

Exemplo:
  Valor conta: R$ 1.500,00
  Valor glosado: R$ 300,00
  Taxa de Glosa = (300 / 1.500) × 100 = 20%
```

### 4.4. Classificação de Tipo de Pagamento

```
Algoritmo de Classificação:

SE V_pago = V_conta ENTÃO
  RETORNAR "FULL"
SENÃO SE V_pago = 0 ENTÃO
  RETORNAR "GLOSA"
SENÃO SE 0 < V_pago < V_conta ENTÃO
  RETORNAR "PARTIAL"
SENÃO SE V_pago > V_conta ENTÃO
  LOG AVISO "Sobrepagamento"
  RETORNAR "FULL"
```

---

## V. Integrações

### 5.1. Sistemas Integrados

| Sistema | Tipo | Dados Trocados | Protocolo |
|---------|------|----------------|-----------|
| Sistema de Contas a Receber | Atualização | Status da conta, valor pago | API REST |
| Sistema Financeiro (ERP) | Atualização | Lançamentos contábeis, receita | API REST |
| Sistema de Glosas | Escrita | Registro de valores glosados | Message Queue |
| Sistema de Cobrança ao Paciente | Consulta | Saldos remanescentes | API REST |
| Sistema de Auditoria | Escrita | Log de processamento de pagamentos | Message Queue |

### 5.2. Dependências de Dados

**Dados Externos Requeridos**:
- Cadastro de contas médicas
- Valores originais das contas
- Status atual das contas
- Histórico de pagamentos

**Frequência de Atualização**:
- Status de contas: Tempo real
- Histórico de pagamentos: Tempo real
- Relatórios financeiros: Diário

---

## VI. Indicadores e Métricas

### 6.1. KPIs de Negócio

| KPI | Métrica | Meta | Fórmula | Frequência |
|-----|---------|------|---------|------------|
| Taxa de Glosa | % de valor glosado do total faturado | < 5% | (Valor Glosado / Valor Total) × 100 | Mensal |
| Tempo Médio de Processamento | Tempo entre recebimento e registro | ≤ 2 horas | Média de intervalos | Diária |
| Taxa de Pagamento Integral | % de contas pagas integralmente | ≥ 85% | (Pagtos FULL / Total) × 100 | Mensal |
| Valor Médio de Glosa | Valor médio glosado por conta | Tendência decrescente | Média de glosas | Mensal |

### 6.2. Métricas Técnicas

| Métrica | Descrição | Alerta | Ação |
|---------|-----------|--------|------|
| Tempo de Processamento | Duração da operação | > 3 segundos | Otimizar atualizações |
| Erros DUPLICATE_PAYMENT | Tentativas de pagamento duplicado | > 1% | Revisar controle de concorrência |
| Erros CLAIM_NOT_FOUND | Contas não encontradas | > 0.5% | Validar integração |
| Taxa de Sobrepagamento | Pagamentos acima do valor | > 0.1% | Investigar causa |

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria

**Eventos Registrados**:
1. Recebimento de informação de pagamento
2. Validação de dados de pagamento
3. Recuperação de informações da conta
4. Classificação do tipo de pagamento
5. Cálculo de glosa e saldo remanescente
6. Atualização de status da conta
7. Registro em sistemas financeiros

**Informações Capturadas**:
```json
{
  "timestamp": "2025-01-12T10:30:00Z",
  "claimId": "CLM-001-1234567890",
  "originalAmount": 1500.00,
  "paymentAmount": 1200.00,
  "glosaAmount": 300.00,
  "remainingBalance": 300.00,
  "paymentType": "PARTIAL",
  "previousStatus": "SUBMITTED",
  "newStatus": "PARTIALLY_PAID",
  "paymentDate": "2025-01-10",
  "executionTimeMs": 234
}
```

### 7.2. Pontos de Controle

| Controle | Tipo | Frequência | Responsável |
|----------|------|------------|-------------|
| Validação de Duplicidade | Preventivo | Por transação | Sistema automático |
| Reconciliação Financeira | Detectivo | Diária | Equipe Financeira |
| Auditoria de Glosas | Detectivo | Semanal | Auditoria Interna |
| Revisão de Sobrepagamentos | Detectivo | Mensal | Controladoria |

---

## VIII. Tratamento de Erros

### 8.1. Erros de Negócio

| Código | Descrição | Severidade | Ação de Recuperação |
|--------|-----------|------------|---------------------|
| CLAIM_NOT_FOUND | Conta não existe no sistema | CRÍTICA | Validar origem dos dados |
| INVALID_PAYMENT_AMOUNT | Valor ou data de pagamento inválido | CRÍTICA | Corrigir dados de entrada |
| DUPLICATE_PAYMENT | Pagamento já processado | CRÍTICA | Verificar histórico |
| PAYMENT_PROCESSING_ERROR | Erro ao atualizar registros | CRÍTICA | Tentar novamente ou escalar |

### 8.2. Estratégia de Retry

**Erros Transientes (retry automático)**:
- Timeout em atualização de banco de dados
- Erro de conexão com ERP
- Indisponibilidade temporária de serviço

**Configuração**:
- Máximo de tentativas: 3
- Intervalo entre tentativas: 1s, 2s, 4s (exponencial)
- Timeout por tentativa: 10 segundos

**Erros Permanentes (sem retry)**:
- CLAIM_NOT_FOUND
- DUPLICATE_PAYMENT
- INVALID_PAYMENT_AMOUNT (dados incorretos)

---

## IX. Casos de Uso

### 9.1. Fluxo Principal - Pagamento Parcial

**Cenário**: Processar pagamento parcial com glosa

**Pré-condições**:
- Conta CLM-001-123 existe
- Status: SUBMITTED
- Valor original: R$ 1.500,00
- Pagamento recebido: R$ 1.200,00

**Fluxo**:
1. Sistema recebe paymentAmount = R$ 1.200,00
2. Valida dados: OK
3. Recupera conta: R$ 1.500,00, status SUBMITTED
4. Valida elegibilidade: OK (status SUBMITTED)
5. Classifica pagamento:
   - Tipo: PARTIAL (1200 < 1500)
   - Glosa: R$ 300,00
   - Saldo: R$ 300,00
6. Atualiza status: PARTIALLY_PAID
7. Cria registro de glosa para análise
8. Atualiza ledger financeiro

**Pós-condições**:
- `paymentProcessed` = true
- `paymentType` = "PARTIAL"
- `glosaAmount` = R$ 300,00
- `remainingBalance` = R$ 300,00
- Conta disponível para recurso de glosa

**Resultado**: Sucesso com identificação de glosa

### 9.2. Fluxo Alternativo - Pagamento Integral

**Cenário**: Processar pagamento integral sem glosa

**Fluxo**:
1. Sistema recebe paymentAmount = R$ 1.500,00
2. Valida dados: OK
3. Recupera conta: R$ 1.500,00
4. Classifica: FULL (1500 = 1500)
5. Glosa: R$ 0,00
6. Saldo: R$ 0,00
7. Atualiza status: PAID
8. Atualiza financeiro: conta encerrada

**Resultado**: Sucesso com conta totalmente paga

### 9.3. Fluxo de Exceção - Glosa Total

**Cenário**: Processar glosa total (pagamento zero)

**Fluxo**:
1. Sistema recebe paymentAmount = R$ 0,00
2. Log de aviso: "Glosa total"
3. Recupera conta: R$ 1.500,00
4. Classifica: GLOSA (payment = 0)
5. Glosa: R$ 1.500,00
6. Saldo: R$ 1.500,00 (pode ser cobrado do paciente se aplicável)
7. Atualiza status: DENIED
8. Notifica equipe de glosas
9. Inicia fluxo de recurso

**Ações Subsequentes**:
- Análise de motivo da glosa
- Recurso junto à operadora
- Eventual cobrança ao paciente

**Resultado**: Glosa registrada para recurso

---

## X. Conformidade Regulatória

### 10.1. Normas Aplicáveis

| Norma | Artigo/Item | Requisito | Como a Regra Atende |
|-------|-------------|-----------|---------------------|
| ANS RN 395/2016 | Art. 12º | Registro de pagamentos e glosas | Registro detalhado de valores pagos e glosados |
| ANS IN 41/2018 | Art. 4º | Prazo para processamento de pagamento | Processamento automático em <2 horas |
| CFM Res. 1.821/2007 | Art. 7º | Rastreabilidade financeira | Log completo de transações |
| LGPD Art. 6º | Inciso VI | Transparência | Acesso ao histórico de pagamentos |
| Código Civil | Art. 389 | Inadimplemento de obrigações | Registro de valores não pagos |

### 10.2. Controles de Compliance

**Segregação de Funções**:
- Registro de pagamento: Sistema automático via integração
- Processamento: Sistema automático
- Validação: Auditoria financeira
- Recurso de glosas: Equipe de glosas

**Retenção de Dados**:
- Histórico de pagamentos: 10 anos (Código Civil)
- Registros de glosas: 5 anos (ANS)
- Logs de processamento: 5 anos

---

## XI. Notas de Migração para Camunda 8

### 11.1. Impactos da Migração

| Aspecto | Camunda 7 | Camunda 8 | Ação Necessária |
|---------|-----------|-----------|-----------------|
| Implementação | JavaDelegate | JobWorker | Converter para JobWorker pattern |
| Atualizações | Síncronas | Assíncronas com workers | Implementar workers para cada sistema |
| Transações | ACID no delegate | Eventual consistency | Implementar saga pattern |
| Concorrência | Lock otimista | Idempotência obrigatória | Garantir operações idempotentes |

### 11.2. Estratégia de Migração

**Fase 1 - Decomposição**:
```
ProcessPaymentWorker (Orquestrador)
├── ValidatePaymentDataWorker
├── FetchClaimInformationWorker
├── CalculatePaymentDetailsWorker
├── UpdateClaimStatusWorker
├── RegisterGlosaWorker
└── UpdateFinancialLedgerWorker
```

**Fase 2 - Idempotência**:
```java
@JobWorker(type = "process-payment", maxJobsActive = 10)
public PaymentResponse processPayment(
    @Variable String claimId,
    @Variable BigDecimal paymentAmount,
    @Variable LocalDate paymentDate
) {
    // Verificar se já processado (idempotência)
    // Processar pagamento
    // Retornar resultado ou erro
    return paymentResult;
}
```

### 11.3. Oportunidades de Melhoria

**Event Sourcing**:
- Registrar eventos de pagamento como stream
- Reconstruir estado a partir de eventos
- Facilitar auditoria e replay

**CQRS**:
- Separar comando (processar pagamento) de query (consultar pagamentos)
- Melhorar performance de consultas
- Otimizar escritas

---

## XII. Mapeamento Domain-Driven Design

### 12.1. Bounded Context

**Contexto**: Revenue Collection (Gestão de Receita)

**Sub-domínio**: Core Domain - Payment Processing

**Responsabilidade**: Processamento de pagamentos recebidos e gestão de glosas

### 12.2. Agregados e Entidades

**Agregado Raiz**: `ClaimPayment`

```
ClaimPayment (Aggregate Root)
├── ClaimId (Value Object)
├── OriginalAmount (Money)
├── PaymentReceived (Money)
├── PaymentDate (LocalDate)
├── PaymentType (Enum: FULL, PARTIAL, GLOSA)
├── GlosaAmount (Money)
├── RemainingBalance (Money)
├── PreviousStatus (ClaimStatus)
├── NewStatus (ClaimStatus)
├── ProcessedAt (Instant)
└── ProcessedBy (UserId)
```

**Value Objects**:
- `Money`: Representação monetária imutável
- `ClaimStatus`: Enum de status de conta
- `PaymentType`: Enum de tipo de pagamento

### 12.3. Domain Events

```
PaymentProcessedEvent
├── claimId: ClaimId
├── paymentType: PaymentType
├── amountPaid: Money
├── glosaAmount: Money
├── remainingBalance: Money
├── processedAt: Instant
└── version: Long

GlosaDetectedEvent
├── claimId: ClaimId
├── glosaAmount: Money
├── glosaPercentage: BigDecimal
├── detectedAt: Instant
└── severity: Severity

PaymentRejectedEvent
├── claimId: ClaimId
├── reason: String
├── errorCode: String
├── rejectedAt: Instant
└── severity: Severity
```

### 12.4. Serviços de Domínio

**PaymentProcessingService**:
```
Responsabilidades:
- Validar dados de pagamento
- Classificar tipo de pagamento
- Calcular glosas e saldos
- Atualizar status da conta

Métodos:
- processPayment(claimId, amount, date): PaymentResult
- classifyPaymentType(claim, payment): PaymentType
- calculateGlosa(claim, payment): Money
- updateClaimStatus(claimId, newStatus): void
```

### 12.5. Repositories

```
ClaimPaymentRepository
├── findByClaimId(claimId): ClaimPayment
├── savePayment(payment): ClaimPayment
└── findUnprocessedPayments(): List<ClaimPayment>

GlosaRepository
├── saveGlosa(glosa): Glosa
└── findByClaimId(claimId): List<Glosa>
```

### 12.6. Ubiquitous Language

| Termo de Negócio | Termo Técnico | Definição |
|------------------|---------------|-----------|
| Pagamento | Payment | Valor recebido da operadora |
| Glosa | Glosa/Denial | Valor não pago pela operadora |
| Saldo Remanescente | Remaining Balance | Diferença entre valor cobrado e pago |
| Pagamento Integral | Full Payment | Operadora paga 100% do valor |
| Pagamento Parcial | Partial Payment | Operadora paga parte do valor |

---

## XIII. Metadados Técnicos

### 13.1. Informações de Desenvolvimento

| Atributo | Valor |
|----------|-------|
| **Classe Java** | `ProcessPaymentDelegate` |
| **Pacote** | `com.hospital.revenuecycle.delegates.billing` |
| **Bean ID** | `processPayment` |
| **Herança** | Extends `BaseDelegate` |
| **Padrão de Projeto** | Strategy, State Pattern |
| **Complexidade Ciclomática** | 9 (Média) |
| **Linhas de Código** | 320 |
| **Cobertura de Testes** | 94% |

### 13.2. Dependências

**Dependências Diretas**:
- Spring Framework 5.3.x
- Camunda BPM 7.18.x
- Lombok 1.18.x
- SLF4J 1.7.x

**Serviços Integrados** (futuro):
- ClaimRepository
- FinancialLedgerService
- GlosaManagementService

### 13.3. Configuração de Performance

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Timeout de Execução | 15s | Múltiplas atualizações em sistemas |
| Pool de Threads | 20 | Processamento paralelo de pagamentos |
| Cache TTL (Contas) | 5 minutos | Evitar reads desnecessários |
| Retry Máximo | 3 tentativas | Tolerância a falhas transientes |

### 13.4. Monitoramento

**Logs Estruturados**:
```json
{
  "event": "payment_processed",
  "claimId": "CLM-001-1234567890",
  "paymentType": "PARTIAL",
  "originalAmount": 1500.00,
  "paymentAmount": 1200.00,
  "glosaAmount": 300.00,
  "remainingBalance": 300.00,
  "previousStatus": "SUBMITTED",
  "newStatus": "PARTIALLY_PAID",
  "executionTimeMs": 234,
  "timestamp": "2025-01-12T10:30:00Z"
}
```

**Métricas Prometheus**:
- `payment_processing_duration_seconds` (Histogram)
- `payments_processed_total` (Counter por tipo)
- `glosa_amount_total` (Counter)
- `payment_errors_total` (Counter por tipo)
- `remaining_balance_distribution` (Histogram)

### 13.5. Testes

**Cenários de Teste Implementados**:
1. ✅ Pagamento integral bem-sucedido
2. ✅ Pagamento parcial com glosa
3. ✅ Glosa total (pagamento zero)
4. ✅ Conta não encontrada
5. ✅ Pagamento duplicado detectado
6. ✅ Valor de pagamento inválido
7. ✅ Status inválido para pagamento
8. ✅ Performance com processamento em lote

---

**Aprovação**:
- **Autor**: Equipe de Desenvolvimento - Ciclo de Receita
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: Gestor Financeiro
- **Data de Aprovação**: 2025-12-23
