# RN-COMP-001: Compensação de Alocação de Pagamento

**ID Técnico**: `CompensateAllocationDelegate`
**Padrão**: SAGA - Compensating Transaction
**Versão**: 1.0
**Data**: 2026-01-24

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra

Desfazer operações de alocação de pagamento (mapping entre pagamentos e faturas) quando o processamento de um SAGA falha após a etapa de alocação, restaurando o estado financeiro anterior.

### 1.2. Contexto de Negócio

O SAGA de processamento de receitas aloca pagamentos recebidos contra faturas em aberto. Se etapas posteriores falham (validação, provisão, submissão), a compensação deve:
- Reverter entradas de alocação no banco de dados
- Retornar valores alocados ao status de não-alocados
- Restaurar balances em contas a receber
- Cancelar operações automáticas de matching

### 1.3. Benefícios Esperados

- **Integridade Financeira**: Garantia de reversão completa de alocações falhadas
- **Consistência de Dados**: Reconciliação automática de valores não-alocados
- **Auditoria Completa**: Trilha de todas as reversões com timestamps
- **Recuperabilidade**: Permitir retry seguro do processo sem duplicação

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
Quando um SAGA falha na etapa de alocação ou em etapas posteriores, o sistema deve compensar (reverter) a alocação de pagamento através de:
1. Remoção de registros de alocação
2. Restauração de saldo não-alocado
3. Reversão de status de faturas
4. Cancelamento de matching automático
5. Ajuste de balances de contas a receber
6. Criação de lançamentos de reversão contábil
7. Notificação de stakeholders
8. Auditoria completa

**Lógica de Execução**:

```
FUNÇÃO CompensarAlocacao(allocationId, paymentId, allocatedAmount, invoiceIds):
  TRANSAÇÃO:
    # Passo 1: Deletar entradas de alocação
    DELETE payment_allocations WHERE allocation_id = ?

    # Passo 2: Restaurar saldo não-alocado
    UPDATE payments
    SET unallocated_amount = unallocated_amount + ?
    WHERE payment_id = ?

    # Passo 3: Reverter alocação em faturas
    UPDATE invoices
    SET allocated_amount = allocated_amount - ?,
        status = 'PENDING'
    WHERE invoice_id IN (?)

    # Passo 4: Cancelar matching automático
    DELETE automatic_matching WHERE allocation_id = ?

    # Passo 5: Atualizar AR balances
    UPDATE account_receivables
    SET balance = balance - ?
    WHERE invoice_id IN (?)

    # Passo 6: Criar lançamentos de reversão (Contábil)
    INSERT journal_entries (
      dr: allocated_receivables_account,
      cr: payment_clearing_account,
      amount: ?,
      reference: allocation_id
    )

    # Passo 7: Notificar controllers
    NOTIFICAR(tipo=ALLOCATION_REVERSED, allocation=allocationId, amount=allocatedAmount)

    # Passo 8: Atualizar auditoria
    INSERT allocation_audit_trail (
      allocation_id, action='COMPENSATED', amount, timestamp
    )

    RETORNAR reversedAmount
  FIM_TRANSAÇÃO
```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| COMP-001-V1 | allocationId obrigatório | CRÍTICA | Rejeitar com erro MISSING_PARAMETER |
| COMP-001-V2 | paymentId obrigatório | CRÍTICA | Rejeitar com erro MISSING_PARAMETER |
| COMP-001-V3 | allocatedAmount > 0 | CRÍTICA | Rejeitar com erro INVALID_AMOUNT |
| COMP-001-V4 | Alocação deve existir | CRÍTICA | Registrar como IDEMPOTENT, retornar sucesso |
| COMP-001-V5 | Pagamento deve existir | CRÍTICA | Falhar se pagamento não encontrado |
| COMP-001-V6 | Faturas devem existir | AVISO | Processar com faturas válidas, log das inválidas |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- allocationId identificando alocação válida
- paymentId do pagamento alocado
- allocatedAmount em moeda brasileira (2 casas decimais)
- invoiceIds lista de faturas afetadas (pode estar vazia)

**Exceções de Negócio**:

1. **Alocação Não Encontrada**
   - **Código**: ALLOCATION_NOT_FOUND
   - **Severidade**: AVISO (idempotente)
   - **Ação**: Registrar como compensação já realizada, retornar sucesso
   - **Notificação**: Não requerida

2. **Pagamento Não Encontrado**
   - **Código**: PAYMENT_NOT_FOUND
   - **Severidade**: CRÍTICA
   - **Ação**: Falhar compensação, escalar para análise
   - **Notificação**: Equipe Financeira

3. **Inconsistência de Saldo**
   - **Código**: BALANCE_MISMATCH
   - **Severidade**: CRÍTICA
   - **Ação**: Reverifıcar estado, falhar se não resolver
   - **Notificação**: Equipe Financeira + Auditoria

4. **Falha ao Deletar Registros**
   - **Código**: DATABASE_DELETE_ERROR
   - **Severidade**: CRÍTICA
   - **Ação**: Rollback completo, retry automático
   - **Estratégia Retry**: Exponencial (2s, 4s, 8s)

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `allocationId` | String | Sim | Identificador único da alocação | UUID válido |
| `paymentId` | String | Sim | Identificador do pagamento | UUID válido |
| `allocatedAmount` | Double | Sim | Valor a reverter (em R$) | > 0, até 2 decimais |
| `invoiceIds` | List<String> | Não | IDs das faturas alocadas | Lista vazia se nenhuma |

**Exemplo de Dados de Entrada**:
```json
{
  "allocationId": "ALLOC-2026-001-123456",
  "paymentId": "PAY-2026-001-987654",
  "allocatedAmount": 5000.50,
  "invoiceIds": ["INV-001-2026", "INV-002-2026"]
}
```

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `compensationCompleted` | Boolean | Sucesso da compensação | Definir próximo gateway |
| `reversedAmount` | Double | Valor revertido (R$) | Auditoria financeira |
| `compensationTimestamp` | LocalDateTime | Momento exato da reversão | Trilha de auditoria |
| `unallocatedBalance` | Double | Saldo restaurado ao pagamento | Verificação de integridade |

**Exemplo de Dados de Saída**:
```json
{
  "compensationCompleted": true,
  "reversedAmount": 5000.50,
  "compensationTimestamp": "2026-01-24T10:30:45.123Z",
  "unallocatedBalance": 5000.50
}
```

---

## IV. Operações Detalhadas

### 4.1. Operação 1: Deletar Entradas de Alocação

**SQL**:
```sql
DELETE FROM payment_allocations
WHERE allocation_id = ?
```

**Validação**:
- Confirmar que alocação existe antes de deletar
- Registrar número de registros deletados (deve ser >= 1)
- Se 0 registros deletados, tratar como IDEMPOTENT

**Auditoria**:
```json
{
  "operation": "delete_allocation_entries",
  "table": "payment_allocations",
  "allocationId": "ALLOC-...",
  "rowsDeleted": 1,
  "timestamp": "..."
}
```

### 4.2. Operação 2: Restaurar Saldo Não-Alocado

**SQL**:
```sql
UPDATE payments
SET unallocated_amount = unallocated_amount + ?,
    last_modified = NOW(),
    modified_by = 'SAGA_COMPENSATION'
WHERE payment_id = ?
```

**Cálculo**:
```
novo_unallocated = unallocated_amount_anterior + allocatedAmount
```

**Validação**:
- Após UPDATE, verificar: `novo_unallocated + allocated_amount = total_payment`
- Se inconsistência, registrar erro BALANCE_MISMATCH

### 4.3. Operação 3: Reverter Alocações em Faturas

**SQL**:
```sql
UPDATE invoices
SET allocated_amount = allocated_amount - ?,
    status = 'PENDING',
    last_modified = NOW(),
    modified_by = 'SAGA_COMPENSATION'
WHERE invoice_id IN (?)
```

**Lógica de Status**:
- Se `allocated_amount` ficar = 0 → status = 'PENDING'
- Se `allocated_amount` > 0 → status = 'PARTIALLY_ALLOCATED'
- Nunca permitir `allocated_amount` negativo

### 4.4. Operação 4: Cancelar Matching Automático

**SQL**:
```sql
DELETE FROM automatic_matching
WHERE allocation_id = ?
   OR invoice_id IN (?)
```

**Contexto**:
- Matching automático é a associação automática entre pagamentos e faturas
- Se foi cancelada a alocação, o matching fica inválido
- Permite retry manual do matching

### 4.5. Operação 5: Atualizar Account Receivables

**SQL**:
```sql
UPDATE account_receivables
SET balance = balance - ?,
    last_reconciliation = NOW()
WHERE invoice_id IN (?)
```

**Validação Contábil**:
- AR balance deve reduzir pelo valor alocado
- Manter integridade: `AR.balance = INV.amount - INV.allocated_amount`

### 4.6. Operação 6: Criar Lançamentos de Reversão Contábil

**Estrutura de Lançamento**:
```
Entrada: Reversão de Alocação
├─ Débito: Contas a Receber Alocadas (401 ou similar)
│  Valor: allocatedAmount
├─ Crédito: Clearing de Pagamentos (110 ou similar)
│  Valor: allocatedAmount
└─ Referência: allocationId

Validação:
  Débito = Crédito (SEMPRE)
  Data contábil = data de compensação
  Período contábil = período aberto/corrente
```

**Journal Entry Record**:
```json
{
  "journalEntryId": "JE-COMP-...",
  "type": "ALLOCATION_REVERSAL",
  "debit": {
    "account": "401-Contas-a-Receber-Alocadas",
    "amount": 5000.50
  },
  "credit": {
    "account": "110-Clearing-Pagamentos",
    "amount": 5000.50
  },
  "reference": "ALLOC-2026-001-123456",
  "description": "Reversão de Alocação - SAGA Compensation",
  "timestamp": "2026-01-24T10:30:45.123Z"
}
```

### 4.7. Operação 7: Notificar Financial Controllers

**Canais**:
- Kafka topic: `hospital.rcm.allocation.reversed` (mensagem assíncrona)
- Email: Automático para gestor financeiro (se severity = CRÍTICA)

**Payload de Notificação**:
```json
{
  "eventType": "ALLOCATION_REVERSED",
  "allocationId": "ALLOC-2026-001-123456",
  "paymentId": "PAY-2026-001-987654",
  "amount": 5000.50,
  "invoiceIds": ["INV-001-2026", "INV-002-2026"],
  "reason": "SAGA compensation after failure in provision step",
  "timestamp": "2026-01-24T10:30:45.123Z",
  "severity": "INFO"
}
```

### 4.8. Operação 8: Atualizar Auditoria

**Audit Trail Record**:
```json
{
  "auditId": "AUDIT-COMP-...",
  "entityId": "ALLOC-2026-001-123456",
  "entityType": "payment_allocation",
  "action": "COMPENSATED",
  "amount": 5000.50,
  "actor": "SAGA_COMPENSATION_SYSTEM",
  "timestamp": "2026-01-24T10:30:45.123Z",
  "details": {
    "paymentId": "PAY-2026-001-987654",
    "invoicesAffected": 2,
    "status": "SUCCESS",
    "executionTimeMs": 234
  }
}
```

---

## V. Padrão SAGA e Compensação

### 5.1. Posição no SAGA

```
SAGA: Ciclo de Receita Completo
│
├─ Step 1: Receber Pagamento ✓ (sem compensação)
│
├─ Step 2: Alocar Pagamento
│  └─ Compensation: CompensateAllocationDelegate [VOCÊ ESTÁ AQUI]
│     Reversa: DELETE alocações, RESTORE saldos
│
├─ Step 3: Criar Provisão
│  └─ Compensation: CompensateProvisionDelegate
│     Reversa: DELETE provision, REVERSE journal entries
│
├─ Step 4: Submeter Cobrança
│  └─ Compensation: CompensateSubmitDelegate
│     Reversa: CANCEL submission, DELETE EDI transaction
│
└─ Step 5: Atualizar Status
   └─ Compensation: (Automática via status rollback)
```

### 5.2. ADR-010: Transações Distribuídas

**Conformidade com ADR-010**:
- ✓ Idempotência: allocationId deve ser único e reutilizável
- ✓ Isolamento: Operações isoladas em transação
- ✓ Ordenação: Compensações em ordem inversa
- ✓ Rastreabilidade: Cada operação registrada em auditoria
- ✓ Notification: Eventos publicados de forma assíncrona

**Idempotência**:
```
SE allocationId NÃO ENCONTRADO EM payment_allocations:
  RETORNAR sucesso com status="ALREADY_COMPENSATED"
  (não é erro, já foi compensado)
```

---

## VI. Fluxos de Processamento

### 6.1. Fluxo Principal - Compensação Bem-Sucedida

**Cenário**: SAGA falha na etapa 3 (Provision), necessita compensar alocação

**Pré-condições**:
- Alocação foi realizada com sucesso
- Saldos foram atualizados
- Journal entries foram criados

**Fluxo**:
1. SAGA detecta falha na etapa de Provision
2. Dispara CompensateAllocationDelegate
3. Extrai variáveis de entrada (allocationId, paymentId, amount, invoiceIds)
4. Inicia transação de banco de dados
5. Executa 8 operações de reversão em sequência
6. Valida integridade após cada operação
7. Commit de transação ao final
8. Publica evento ALLOCATION_REVERSED
9. Retorna com sucesso = true

**Pós-condições**:
- payment_allocations: deletado
- payments.unallocated_amount: restaurado
- invoices: status = PENDING, allocated_amount = 0
- journal_entries: lançamento de reversão criado
- audit_trail: registro de compensação
- Notificações enviadas

**Tempo Esperado**: 200-400ms
**Resultado**: Compensação bem-sucedida, SAGA pode ser retryado

### 6.2. Fluxo Idempotente - Compensação Já Realizada

**Cenário**: Compensation é chamado novamente para mesma alocação

**Fluxo**:
1. Recebe allocationId
2. Procura em payment_allocations
3. Não encontra (já foi deletado)
4. **Ação Especial**: Retorna sucesso imediatamente
5. Registra em auditoria: "COMPENSATION_ALREADY_APPLIED"
6. Não tenta refazer operações

**Benefício**: Permite retry seguro do SAGA sem duplicação

### 6.3. Fluxo de Erro - Falha em Operação de Database

**Cenário**: DELETE falha com constraint violation

**Fluxo**:
1. Execute operação 1 (DELETE)
2. Recebe erro: FOREIGN_KEY_CONSTRAINT_VIOLATION
3. Rollback automático de transação
4. Log do erro com contexto completo
5. Dispara retry automático (configurável)
   - Tentativa 1: Wait 2s, retry
   - Tentativa 2: Wait 4s, retry
   - Tentativa 3: Wait 8s, retry
   - Após 3 falhas: Escalar para manual review
6. Se retry bem-sucedido: continua normalmente
7. Se falha persistente: notifica equipe técnica

**Recuperação Manual**:
- Script SQL para análise de inconsistência
- Documentação de what went wrong
- Passo-a-passo para correção manual

### 6.4. Fluxo Parcial - Algumas Faturas Inválidas

**Cenário**: invoiceIds contém faturas que não existem

**Fluxo**:
1. Recebe invoiceIds = ["INV-001", "INV-999"]
2. Executa operações normalmente
3. Na operação 3 (UPDATE invoices):
   - INV-001: atualiza com sucesso
   - INV-999: não encontrada (UPDATE afeta 0 linhas)
4. **Ação**: Log de warning para INV-999
5. Continua com sucesso (not all-or-nothing)
6. Auditoria registra invoices afetadas vs não encontradas
7. Notificação inclui lista de discrepâncias

---

## VII. Controles e Auditoria

### 7.1. Trilha de Auditoria Detalhada

**Eventos Registrados**:
1. Início de compensação (entrada)
2. Cada operação SQL executada
3. Resultado de cada operação (sucesso/falha)
4. Validações intermediárias
5. Transição de estado
6. Notificações enviadas
7. Fim de compensação (saída)

**Retenção de Dados**:
- Logs: 1 ano
- Audit trail: 5 anos (CFM)
- Journal entries: Permanente
- Notificações: 1 ano

### 7.2. Idempotência e Rastreabilidade

**Chave de Idempotência**:
```
chaveIdempotencia = SHA256(
  "COMPENSATE_ALLOCATION" +
  allocationId +
  paymentId +
  allocatedAmount
)
```

**Verificação**:
- Se chave existe em idempotency_registry com status SUCCESS → retornar sucesso
- Se chave existe com status FAILED → retentar
- Se chave não existe → executar e registrar

### 7.3. Pontos de Controle

| Controle | Tipo | Frequência | Verificação |
|----------|------|-----------|-------------|
| Integridade de Saldos | Preventivo | Por transação | balance_check() |
| Reconciliação de AR | Detectivo | Diária | Query soma vs banco |
| Audit Trail Completude | Detectivo | Mensal | Verificar gaps |
| Notificações Entregues | Detectivo | Semanal | Confirmar acknowledgment |

---

## VIII. Tratamento de Erros

### 8.1. Erros Específicos e Recuperação

| Código | Descrição | Severidade | Recuperação | Retry |
|--------|-----------|------------|-------------|-------|
| ALLOCATION_NOT_FOUND | Alocação não existe | AVISO | Retornar sucesso (idempotente) | Não |
| PAYMENT_NOT_FOUND | Pagamento não existe | CRÍTICA | Falhar, escalar | Sim (3x) |
| BALANCE_MISMATCH | Saldos inconsistentes | CRÍTICA | Rollback, falhar | Sim (3x) |
| DATABASE_ERROR | Erro SQL genérico | CRÍTICA | Rollback, falhar | Sim (3x) |
| NOTIFICATION_FAILED | Kafka indisponível | AVISO | Log, continuar | Sim (async) |

### 8.2. Estratégia de Retry

**Erros Transientes** (retry automático):
- PAYMENT_NOT_FOUND (pode ser race condition)
- DATABASE_ERROR (timeout ou lock)
- NOTIFICATION_FAILED (Kafka indisponível)

**Configuração**:
```
MaxRetries: 3
WaitStrategy: Exponential (2s, 4s, 8s)
Timeout per attempt: 5s
Total timeout: 15s
```

**Erros Permanentes** (sem retry):
- BALANCE_MISMATCH (requer investigação)
- Constraint violations persistentes

---

## IX. Conformidade Regulatória

### 9.1. Normas Aplicáveis

| Norma | Artigo | Requisito | Conformidade |
|-------|--------|-----------|-------------|
| CFM Resolução 2.229/2019 | - | Manutenção de registros financeiros por 5 anos | Audit trail 5 anos |
| LGPD Art. 6º | Inciso VI | Transparência em processamento | Logs estruturados |
| Lei 6.404/76 | Art. 177 | Integridade contábil | Journal entries duplo-débito |
| CPC 00 | - | Princípios contábeis geralmente aceitos | Reversão simétrica |

### 9.2. Segregação de Funções

- **Execução**: SAGA automático
- **Aprovação**: Não requerida (compensação automática)
- **Auditoria**: Auditoria Interna (mensal)
- **Investigação**: CFO em caso de discrepância

---

## X. Indicadores e Métricas

### 10.1. KPIs de Negócio

| KPI | Meta | Fórmula | Frequência |
|-----|------|---------|-----------|
| Taxa de Compensação Bem-Sucedida | ≥ 99.5% | (Sucesso / Total) × 100 | Diária |
| Tempo Médio de Compensação | ≤ 300ms | Avg(compensation_time_ms) | Diária |
| Taxa de Idempotência | ≥ 95% | (Reutilizações / Total) × 100 | Semanal |
| Erros de Integridade Detectados | ≤ 0.1% | (Mismatches / Total) × 100 | Mensal |

### 10.2. Métricas Técnicas

**Prometheus Metrics**:
```
# Contador de compensações
compensate_allocation_total{status="success|failure"}

# Histórico de duração
compensate_allocation_duration_seconds (histogram)

# Erros por tipo
compensate_allocation_errors_total{error="PAYMENT_NOT_FOUND|..."}

# Valores compensados
compensate_allocation_amount_total (counter)
```

**Alertas**:
- Taxa de erro > 1% em 5 min → CRITICAL
- Tempo médio > 1s → WARNING
- Mais de 10 idempotências em 1h → INVESTIGATE

---

## XI. Dependências e Integrações

### 11.1. Dependências de Código

**Classe Base**:
- `BaseDelegate`: Gerenciamento de variáveis, tratamento de erros

**Serviços**:
- `SagaCompensationService`: Registra ação de compensação no SAGA

**Entidades de Domínio**:
- `Payment`: Pagamento recebido
- `Invoice`: Fatura em aberto
- `PaymentAllocation`: Mapeamento entre pagamento e fatura

### 11.2. Dependências Externas

| Sistema | Tipo | Dados | Frequência |
|---------|------|-------|-----------|
| PostgreSQL | BD Principal | Tabelas de pagamentos e alocações | Por transação |
| Kafka | Message Broker | Notificação de reversão | Assíncrono |
| ERP (opcional) | Sistema Externo | Reversão de journal entries | Se integrado |

---

## XII. Configuração e Performance

### 12.1. Parâmetros de Configuração

```properties
# Timeout
compensation.allocation.timeout.ms=10000

# Retry
compensation.allocation.max.retries=3
compensation.allocation.retry.initial.wait.ms=2000
compensation.allocation.retry.multiplier=2.0

# Notificação
compensation.allocation.kafka.topic=hospital.rcm.allocation.reversed
compensation.allocation.notification.async=true
```

### 12.2. Otimizações

**Índices de Database**:
```sql
-- Para DELETE rápido
CREATE INDEX idx_payment_alloc_id ON payment_allocations(allocation_id);

-- Para UPDATE rápido
CREATE INDEX idx_invoices_id ON invoices(invoice_id);

-- Para queries de auditoria
CREATE INDEX idx_alloc_audit_timestamp ON allocation_audit_trail(timestamp DESC);
```

**Batch Processing**:
- Se múltiplas compensações simultâneas: considerar batch delete
- Mas manter transação por compensação (isolamento)

---

## XIII. Casos de Uso Detalhados

### 13.1. Caso 1: Falha em Step 3 (Provision)

**Contexto**:
- Alocação foi criada: ALLOC-2026-001-123456
- Pagamento PAY-2026-001-987654 foi alocado R$ 5.000
- Faturas INV-001-2026 e INV-002-2026 foram atualizadas
- Provision falha por validação de cobertura

**Execução**:
1. CompensateAllocationDelegate é acionado
2. Deleta ALLOC-2026-001-123456
3. Aumenta payment.unallocated_amount de 0 para 5.000
4. Reseta invoices status = PENDING, allocated = 0
5. Cancela matching automático
6. Cria journal entry de reversão
7. Notifica: "Alocação revertida, SAGA pode retentar"

**Resultado**: Alocação restaurada, pronto para novo tentativa

### 13.2. Caso 2: Compensação Chamada Novamente

**Contexto**:
- Primeira tentativa sucedeu
- Timeout causou acionamento novamente do SAGA
- CompensateAllocationDelegate é chamado novamente

**Execução**:
1. Procura ALLOC-2026-001-123456 em payment_allocations
2. Não encontra (já foi deletado na primeira vez)
3. **Ação Especial**: Retorna sucesso imediatamente
4. Auditoria registra: "COMPENSATION_ALREADY_APPLIED"

**Resultado**: Nenhuma ação, retorna sucesso (idempotente)

### 13.3. Caso 3: Falha com Dados Parciais

**Contexto**:
- allocationId existe e será deletado
- Uma das invoices (INV-999) não existe mais
- Pode ter sido deletada por outro processo

**Execução**:
1. Deleta allocation: sucesso
2. Atualiza payment.unallocated_amount: sucesso
3. Tenta atualizar INV-001: sucesso
4. Tenta atualizar INV-999: não encontrada
5. UPDATE afeta 0 linhas (não é erro SQL)
6. Log de warning registrado
7. Continua com operações subsequentes
8. Auditoria nota: "2 faturas afetadas, 1 não encontrada"

**Resultado**: Compensação parcial bem-sucedida, investigar INV-999

---

## XIV. Monitoramento e Observabilidade

### 14.1. Logs Estruturados

```json
{
  "timestamp": "2026-01-24T10:30:45.123Z",
  "logLevel": "INFO",
  "event": "compensation_allocation_completed",
  "processInstanceId": "PROC-2026-001",
  "allocationId": "ALLOC-2026-001-123456",
  "paymentId": "PAY-2026-001-987654",
  "reversedAmount": 5000.50,
  "invoicesCount": 2,
  "executionTimeMs": 234,
  "status": "SUCCESS",
  "actor": "SAGA_COMPENSATION_SYSTEM"
}
```

### 14.2. Dashboards Grafana

**Dashboard: Allocation Compensation**
- Taxa de sucesso (%)
- Tempo médio (ms)
- Volume por hora
- Erros por tipo
- Alertas ativos

---

## XV. Próximas Etapas no SAGA

Após completar CompensateAllocationDelegate com sucesso:

1. **Se compensação bem-sucedida**:
   - Volta para etapa anterior do SAGA
   - Permite retry automático
   - Ou escalação para análise manual

2. **Próximas compensações** (se necessário):
   - CompensateProvisionDelegate (se provision foi criada)
   - CompensateSubmitDelegate (se submission foi enviada)

---

## XVI. Versão e Histórico

| Versão | Data | Autor | Alterações |
|--------|------|-------|-----------|
| 1.0 | 2026-01-24 | Revenue Cycle Team | Criação inicial, documentação completa |

---

## XVII. Glossário

| Termo | Definição |
|-------|-----------|
| **Alocação** | Mapeamento entre pagamento recebido e faturas em aberto |
| **Compensação** | Reversão de operação em SAGA distribuído |
| **Idempotência** | Propriedade de retorno seguro mesmo se executado múltiplas vezes |
| **Journal Entry** | Lançamento contábil em débito/crédito |
| **Account Receivables** | Contas a Receber, saldos em aberto |
| **SAGA** | Padrão de transação distribuída com compensação |

---

**Aprovação**:
- **Autor**: Revenue Cycle Development Team
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador de Negócio**: CFO Faturamento
- **Data de Aprovação**: 2026-01-24
