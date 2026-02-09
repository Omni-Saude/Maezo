# RN-COMP-002: Compensação de Provisão de Glosa

**ID Técnico**: `CompensateProvisionDelegate`
**Padrão**: SAGA - Compensating Transaction
**Versão**: 1.0
**Data**: 2026-01-24

---

## I. Resumo Executivo

### 1.1. Objetivo da Regra

Desfazer operações de provisão contábil para glosas (reserva de contingência para possíveis glosas) quando o processamento de um SAGA falha após a etapa de provisão, restaurando balances financeiros e status contábil anterior.

### 1.2. Contexto de Negócio

O SAGA cria provisões (reservas contábeis) para cobrir possíveis glosas de faturas. Se etapas posteriores falham (submissão de cobrança), a compensação deve:
- Remover entrada de provisão da glosa
- Reverter lançamentos contábeis (journal entries)
- Restaurar balances em contas patrimoniais
- Cancelar integração com ERP
- Reverter registros de provisioning

### 1.3. Benefícios Esperados

- **Precisão Contábil**: Garantia de reversal correto de provision expenses
- **Consistência Patrimonial**: Restauração de balances em liability accounts
- **Auditoria Duplo-Débito**: Compliance com princípios contábeis
- **Rastreabilidade**: Trilha completa de provisões criadas e revertidas

---

## II. Definição da Regra de Negócio

### 2.1. Descrição Detalhada

**Descrição Executiva**:
Quando um SAGA falha em etapas de submissão ou posteriores, e uma provisão de glosa foi criada, o sistema deve compensar (reverter) a provisão através de:
1. Remoção de registro de provision
2. Reversão de journal entries contábeis (Dr Liability, Cr Expense)
3. Atualização de status da glosa
4. Restauração de balances em GL (General Ledger)
5. Cancelamento de integração ERP
6. Notificação de stakeholders
7. Auditoria completa

**Lógica de Execução**:

```
FUNÇÃO CompensarProvisao(provisionId, glosaId, provisionAmount, accountingPeriod):
  TRANSAÇÃO:
    # Passo 1: Deletar registro de provision
    DELETE glosa_provisions WHERE provision_id = ?

    # Passo 2: Reverter journal entries (duplicar com inverso)
    INSERT journal_entries (
      Dr: Provision_Liability_Account (2101),
      Cr: Provision_Expense_Account (6301),
      Amount: provisionAmount,
      Period: accountingPeriod,
      Type: REVERSAL
    )

    # Passo 3: Atualizar status de glosa
    UPDATE glosas
    SET status = 'PENDING_PROVISION',
        provisioned = false,
        last_modified = NOW()
    WHERE glosa_id = ?

    # Passo 4: Restaurar financial balances em GL
    UPDATE general_ledger
    SET balance = balance - ? (para liability)
    WHERE account_code = '2101'
      AND period = ?

    # Passo 5: Cancelar ERP integration
    POST /api/v1/provisions/{provisionId}/cancel

    # Passo 6: Notificar controllers
    NOTIFICAR(tipo=PROVISION_REVERSED, provision=provisionId, amount=provisionAmount)

    # Passo 7: Atualizar auditoria
    INSERT provision_audit_trail (
      provision_id, action='COMPENSATED', amount, period, timestamp
    )

    RETORNAR reversedAmount
  FIM_TRANSAÇÃO
```

### 2.2. Regras de Validação

| ID | Regra | Severidade | Ação |
|----|-------|------------|------|
| COMP-002-V1 | provisionId obrigatório | CRÍTICA | Rejeitar com erro MISSING_PARAMETER |
| COMP-002-V2 | glosaId obrigatório | CRÍTICA | Rejeitar com erro MISSING_PARAMETER |
| COMP-002-V3 | provisionAmount > 0 | CRÍTICA | Rejeitar com erro INVALID_AMOUNT |
| COMP-002-V4 | accountingPeriod válido | CRÍTICA | Validar formato YYYY-MM |
| COMP-002-V5 | Provision deve existir | CRÍTICA | Registrar como IDEMPOTENT se não existir |
| COMP-002-V6 | Glosa deve existir | CRÍTICA | Falhar se glosa não encontrada |
| COMP-002-V7 | Período não pode ser fechado | CRÍTICA | Falhar se período contábil fechado |

### 2.3. Condições e Exceções

**Condições de Entrada**:
- provisionId identificando provision válida
- glosaId da glosa relacionada
- provisionAmount em R$ (2 decimais)
- accountingPeriod em formato YYYY-MM (período aberto)

**Exceções de Negócio**:

1. **Provision Não Encontrada**
   - **Código**: PROVISION_NOT_FOUND
   - **Severidade**: AVISO (idempotente)
   - **Ação**: Retornar sucesso, registrar como já compensada
   - **Notificação**: Não requerida

2. **Glosa Não Encontrada**
   - **Código**: GLOSA_NOT_FOUND
   - **Severidade**: CRÍTICA
   - **Ação**: Falhar, escalar
   - **Notificação**: Equipe Financeira

3. **Período Contábil Fechado**
   - **Código**: ACCOUNTING_PERIOD_CLOSED
   - **Severidade**: CRÍTICA
   - **Ação**: Falhar, requer journal entry em período aberto
   - **Notificação**: Gestor Contábil

4. **Inconsistência de Balance**
   - **Código**: BALANCE_INCONSISTENCY
   - **Severidade**: CRÍTICA
   - **Ação**: Rollback, investigação
   - **Notificação**: Auditoria + CFO

5. **Falha ERP Integration**
   - **Código**: ERP_CANCELLATION_FAILED
   - **Severidade**: CRÍTICA
   - **Ação**: Rollback, escalação manual
   - **Notificação**: Equipe de Integração ERP

---

## III. Variáveis do Processo

### 3.1. Variáveis de Entrada

| Variável | Tipo | Obrigatório | Descrição | Validação |
|----------|------|-------------|-----------|-----------|
| `provisionId` | String | Sim | Identificador da provision | UUID válido |
| `glosaId` | String | Sim | Identificador da glosa | UUID válido |
| `provisionAmount` | Double | Sim | Valor de provision (R$) | > 0, até 2 decimais |
| `accountingPeriod` | String | Sim | Período contábil | Formato YYYY-MM |

**Exemplo de Dados de Entrada**:
```json
{
  "provisionId": "PROV-2026-001-456789",
  "glosaId": "GLOS-2026-001-123456",
  "provisionAmount": 12500.75,
  "accountingPeriod": "2026-01"
}
```

### 3.2. Variáveis de Saída

| Variável | Tipo | Descrição | Uso Posterior |
|----------|------|-----------|---------------|
| `compensationCompleted` | Boolean | Sucesso da compensação | Definir próximo gateway |
| `reversedAmount` | Double | Valor revertido (R$) | Auditoria financeira |
| `compensationTimestamp` | LocalDateTime | Momento da reversão | Trilha de auditoria |

**Exemplo de Dados de Saída**:
```json
{
  "compensationCompleted": true,
  "reversedAmount": 12500.75,
  "compensationTimestamp": "2026-01-24T10:31:15.456Z"
}
```

---

## IV. Operações Detalhadas

### 4.1. Operação 1: Deletar Registro de Provision

**SQL**:
```sql
DELETE FROM glosa_provisions
WHERE provision_id = ?
```

**Validação**:
- Confirmar que provision existe
- Registrar número de registros deletados (deve ser = 1)
- Se 0 registros: tratar como IDEMPOTENT

**Auditoria**:
```json
{
  "operation": "delete_provision_record",
  "table": "glosa_provisions",
  "provisionId": "PROV-...",
  "glosaId": "GLOS-...",
  "rowsDeleted": 1,
  "timestamp": "..."
}
```

### 4.2. Operação 2: Reverter Journal Entries Contábeis

**Estrutura de Reversão**:
```
Lançamento Original (quando provision foi criada):
  Dr: Provision Expense (6301)        = 12.500,75
  Cr: Provision Liability (2101)      = 12.500,75

Lançamento de Reversão (agora):
  Dr: Provision Liability (2101)      = 12.500,75
  Cr: Provision Expense (6301)        = 12.500,75
  (efeito: anula o lançamento original)
```

**SQL para Reversão**:
```sql
INSERT INTO journal_entries (
  debit_account,
  credit_account,
  amount,
  accounting_period,
  reference_id,
  description,
  entry_type,
  created_at
) VALUES (
  '2101',                              -- Provision Liability (Dr)
  '6301',                              -- Provision Expense (Cr)
  12500.75,
  '2026-01',
  'PROV-2026-001-456789',
  'Reversão de Provision - SAGA Compensation',
  'REVERSAL',
  NOW()
)
```

**Validação**:
- Dr = Cr (sempre)
- Período = período original de provision
- Referência vincula a provision específica
- Descrição clara de que é reversão

**Registro de Journal Entry**:
```json
{
  "journalEntryId": "JE-REV-COMP-...",
  "type": "REVERSAL",
  "debit": {
    "account": "2101-Provisao-Glosas",
    "description": "Provision for Disputed Claims",
    "amount": 12500.75
  },
  "credit": {
    "account": "6301-Despesa-Provisao",
    "description": "Provision Expense",
    "amount": 12500.75
  },
  "period": "2026-01",
  "referenceId": "PROV-2026-001-456789",
  "reversalOf": "JE-ORIG-...",
  "timestamp": "2026-01-24T10:31:15.456Z",
  "createdBy": "SAGA_COMPENSATION_SYSTEM"
}
```

### 4.3. Operação 3: Atualizar Status de Glosa

**SQL**:
```sql
UPDATE glosas
SET status = 'PENDING_PROVISION',
    provisioned = false,
    last_modified = NOW(),
    modified_by = 'SAGA_COMPENSATION'
WHERE glosa_id = ?
```

**Transição de Status**:
- Status anterior: 'PROVISIONED'
- Status novo: 'PENDING_PROVISION'
- Significado: Glosa necessita nova avaliação de provisioning

**Validação**:
- Glosa deve existir
- Status atual deve ser 'PROVISIONED'
- Provisioned flag deve ser true

### 4.4. Operação 4: Restaurar General Ledger Balances

**SQL** (para conta de Liability):
```sql
UPDATE general_ledger
SET balance = balance - ?,  -- Reduz liability
    last_updated = NOW()
WHERE account_code = '2101'   -- Provision Liability
  AND accounting_period = ?
```

**Lógica de Restauração**:
```
GL anterior: balance = 50.000 (liability)
Operação 4:  balance = 50.000 - 12.500,75 = 37.499,25
Resultado:   Balance reduzido (provision reversa)
```

**Validação Duplo-Débito**:
- Para cada Dr: deve existir Cr correspondente
- Somas de assets = somas de liabilities + equity
- Manter equação contábil: A = L + E

### 4.5. Operação 5: Cancelar ERP Integration

**API Call**:
```
POST /api/v1/provisions/{provisionId}/cancel
Content-Type: application/json

{
  "provisionId": "PROV-2026-001-456789",
  "glosaId": "GLOS-2026-001-123456",
  "reason": "SAGA_COMPENSATION",
  "timestamp": "2026-01-24T10:31:15.456Z"
}
```

**Resposta Esperada**:
```json
{
  "status": "CANCELLED",
  "provisionId": "PROV-2026-001-456789",
  "cancelledAt": "2026-01-24T10:31:16.789Z",
  "erpReference": "ERP-REF-..."
}
```

**Tratamento de Erro**:
- Se ERP indisponível: retry automático (3x com wait exponencial)
- Se falha persistente: registrar e escalar, continuar compensação
- Nota: DB foi atualizado, ERP será sincronizado depois

### 4.6. Operação 6: Notificar Financial Controllers

**Canais**:
- Kafka: `hospital.rcm.provision.reversed`
- Email: CFO se severity = CRÍTICA

**Payload**:
```json
{
  "eventType": "PROVISION_REVERSED",
  "provisionId": "PROV-2026-001-456789",
  "glosaId": "GLOS-2026-001-123456",
  "amount": 12500.75,
  "period": "2026-01",
  "reason": "SAGA compensation after submission failure",
  "timestamp": "2026-01-24T10:31:15.456Z",
  "severity": "INFO"
}
```

### 4.7. Operação 7: Atualizar Auditoria

**Audit Trail Record**:
```json
{
  "auditId": "AUDIT-PROV-...",
  "entityId": "PROV-2026-001-456789",
  "entityType": "provision",
  "action": "COMPENSATED",
  "amount": 12500.75,
  "actor": "SAGA_COMPENSATION_SYSTEM",
  "timestamp": "2026-01-24T10:31:15.456Z",
  "details": {
    "glosaId": "GLOS-2026-001-123456",
    "period": "2026-01",
    "status": "SUCCESS",
    "journalEntryCreated": "JE-REV-COMP-...",
    "executionTimeMs": 567
  }
}
```

---

## V. Padrão SAGA e Compensação

### 5.1. Posição no SAGA

```
SAGA: Ciclo de Receita Completo
│
├─ Step 1: Receber Pagamento
│  └─ Compensation: (Não há)
│
├─ Step 2: Alocar Pagamento
│  └─ Compensation: CompensateAllocationDelegate
│
├─ Step 3: Criar Provisão
│  └─ Compensation: CompensateProvisionDelegate [VOCÊ ESTÁ AQUI]
│     Reversa: DELETE provision, REVERSE journal entries
│
├─ Step 4: Submeter Cobrança
│  └─ Compensation: CompensateSubmitDelegate
│
└─ Step 5: Atualizar Status
   └─ Compensation: (Automática)
```

### 5.2. ADR-010 Compliance

**Conformidade**:
- ✓ Idempotência: provisionId reutilizável
- ✓ Duplo-Débito: Reversão cria lançamentos contrapostos
- ✓ Período Contábil: Mantém integridade de período
- ✓ Rastreabilidade: Cada reversão auditada
- ✓ Notificação Assíncrona: Eventos publicados via Kafka

**Idempotência**:
```
SE provisionId NÃO ENCONTRADO EM glosa_provisions:
  RETORNAR sucesso com status="ALREADY_COMPENSATED"
```

---

## VI. Fluxos de Processamento

### 6.1. Fluxo Principal - Compensação Bem-Sucedida

**Cenário**: SAGA falha na etapa de Submissão após provisão criada

**Pré-condições**:
- Provision foi registrada em glosa_provisions
- Journal entries foram criados (Dr 6301, Cr 2101)
- ERP foi atualizado com provision
- GL balances foram aumentados

**Fluxo**:
1. SAGA detecta falha em submissão
2. Inicia compensações em ordem inversa
3. CompensateProvisionDelegate acionado
4. Extrai variáveis (provisionId, glosaId, amount, period)
5. Inicia transação de banco de dados
6. Executa 7 operações em sequência
7. Valida integridade contábil após cada operação
8. Commit ao final
9. Publica evento PROVISION_REVERSED
10. Retorna sucesso = true

**Pós-condições**:
- glosa_provisions: deletado
- journal_entries: reversão criada
- glosas.status: PENDING_PROVISION
- GL balances: restaurados
- ERP: sincronizado
- audit_trail: registrado

**Tempo Esperado**: 300-600ms (inclui ERP call)
**Resultado**: Provision compensada, SAGA pode retentar

### 6.2. Fluxo Idempotente - Compensação Já Realizada

**Cenário**: Compensation é chamado novamente

**Fluxo**:
1. Recebe provisionId
2. Procura em glosa_provisions
3. Não encontra (já foi deletado)
4. **Ação Especial**: Retorna sucesso imediatamente
5. Auditoria: "COMPENSATION_ALREADY_APPLIED"
6. Não refaz operações

**Benefício**: Retry seguro

### 6.3. Fluxo de Erro - Período Contábil Fechado

**Cenário**: Período da provision foi fechado

**Fluxo**:
1. Tenta criar journal entry para período 2025-12
2. Recebe erro: PERIOD_CLOSED
3. **Ação**: Falha compensação
4. Log de erro detalhado
5. Notifica Gestor Contábil
6. Requer abertura de período especial ou documento administrativo

**Recuperação**: Manual - requer aprovação CFO

### 6.4. Fluxo de Falha ERP - Retry Automático

**Cenário**: ERP indisponível ao chamar API de cancellação

**Fluxo**:
1. Banco de dados foi atualizado com sucesso
2. Journal entries criados
3. Tenta POST para ERP /cancel
4. Timeout (ERP indisponível)
5. **Ação**: Registra erro, tenta retry (3x)
   - Retry 1: Wait 2s, POST novamente
   - Retry 2: Wait 4s, POST novamente
   - Retry 3: Wait 8s, POST novamente
6. Se 3x falham: Escala para manual, but compensação continua
7. Retorna sucesso parcial (DB OK, ERP sync pendente)
8. Background job sincroniza ERP depois

**Resultado**: Compensação bem-sucedida localmente, ERP sync async

---

## VII. Contabilidade e Journal Entries

### 7.1. Mapear de Contas (Plano de Contas Padrão)

| Código | Descrição | Tipo | Uso |
|--------|-----------|------|-----|
| 2101 | Provisão para Glosas | Liability | Cr quando provision criada, Dr quando reversada |
| 6301 | Despesa de Provisão | Expense | Dr quando provision criada, Cr quando reversada |
| 4101 | Receita Médica | Revenue | Não afetada por provision |

### 7.2. Duplo-Débito: Lançamento e Reversão

**Cenário Completo**:

**T1: Provision Criada** (CompensateProvisionDelegate NÃO executado)
```
Dr: Provision Expense (6301)  = 12.500,75
Cr: Provision Liability (2101) = 12.500,75
---
Efeito: Gasto de R$ 12.500,75 com reserva de liability
GL 2101 saldo = 12.500,75 (liability aumentada)
GL 6301 saldo = 12.500,75 (expense aumentada)
```

**T2: Compensation Executado** (RN-COMP-002)
```
Dr: Provision Liability (2101) = 12.500,75  (reduz liability)
Cr: Provision Expense (6301)   = 12.500,75  (reduz expense)
---
Efeito: Cancela o lançamento anterior
GL 2101 saldo = 0 (liability volta ao original)
GL 6301 saldo = 0 (expense volta ao original)
```

**Validação**:
- Ambos os lançamentos têm mesma referência: PROV-2026-001-456789
- Período é o mesmo
- Importa é simétrico

---

## VIII. Tratamento de Erros

### 8.1. Erros Específicos

| Código | Descrição | Severidade | Recuperação | Retry |
|--------|-----------|------------|-------------|-------|
| PROVISION_NOT_FOUND | Provision não existe | AVISO | Retornar sucesso (idempotente) | Não |
| GLOSA_NOT_FOUND | Glosa não existe | CRÍTICA | Falhar, escalar | Sim (3x) |
| PERIOD_CLOSED | Período contábil fechado | CRÍTICA | Falhar, requer manual | Não |
| BALANCE_INCONSISTENCY | GL balances inconsistentes | CRÍTICA | Rollback, falhar | Sim (3x) |
| ERP_CANCELLATION_FAILED | ERP indisponível | CRÍTICA | Retry async | Sim (3x async) |

### 8.2. Retry Strategy

**Transientes**:
- GLOSA_NOT_FOUND (pode ser race condition)
- BALANCE_INCONSISTENCY (lock na BD)
- ERP_CANCELLATION_FAILED (timeout)

**Permanentes**:
- PERIOD_CLOSED (requer ação manual)
- Constraint violations

**Configuração**:
```
MaxRetries: 3
WaitStrategy: Exponential (2s, 4s, 8s)
Timeout: 5s por tentativa
```

---

## IX. Conformidade Regulatória

### 9.1. Normas Aplicáveis

| Norma | Artigo | Requisito | Conformidade |
|-------|--------|-----------|-------------|
| Lei 6.404/76 | Art. 177 | Duplo-débito em contabilidade | Reversão simétrica |
| CPC 00 | - | Princípios contábeis | Provision reversal completa |
| CPC 25 | - | Provisões contábeis | Quando provision reversa |
| CFM 2.229/2019 | - | Retenção 5 anos | Audit trail 5 anos |
| LGPD | Art. 6 | Transparência | Logs estruturados |

### 9.2. Segregação de Funções

- **Execução**: SAGA automático
- **Validação**: Validação contábil automática
- **Auditoria**: Auditoria Interna (mensal)
- **Aprovação**: CFO (se manual intervention)

---

## X. Indicadores e Métricas

### 10.1. KPIs de Negócio

| KPI | Meta | Fórmula | Frequência |
|-----|------|---------|-----------|
| Taxa de Compensação Bem-Sucedida | ≥ 99% | (Sucesso / Total) × 100 | Diária |
| Tempo Médio de Compensação | ≤ 500ms | Avg(compensation_time_ms) | Diária |
| Integridade de GL | 100% | Validação Dr=Cr | Diária |
| Erros Contábeis Detectados | ≤ 0.05% | (Erros / Total) × 100 | Mensal |

### 10.2. Métricas Técnicas

**Prometheus**:
```
compensate_provision_total{status="success|failure"}
compensate_provision_duration_seconds (histogram)
compensate_provision_errors_total{error="..."}
compensate_provision_amount_total (counter)
journal_entries_reversal_total (counter)
```

---

## XI. Casos de Uso Detalhados

### 11.1. Caso 1: Falha em Submission Step

**Contexto**:
- Provision PROV-2026-001-456789 foi criada
- Valor: R$ 12.500,75
- Period: 2026-01
- Glosa: GLOS-2026-001-123456
- Submission falha por validação de payer

**Execução**:
1. SAGA dispara CompensateProvisionDelegate
2. Deleta provision de glosa_provisions
3. Cria reversão de journal entries
4. Muda glosa status = PENDING_PROVISION
5. Restaura GL balances
6. Cancela ERP provision
7. Notifica controllers
8. Auditoria registrada

**Resultado**: Provision revertida, SAGA pronto para retry

### 11.2. Caso 2: Período Contábil Fechado

**Cenário**: Período 2025-12 foi fechado desde então

**Fluxo**:
1. Tenta criar journal entry para 2025-12
2. Recebe PERIOD_CLOSED
3. Falha compensação
4. Notifica CFO
5. Requer aprovação para journal adjustment entry

**Resolução**: CFO aprova ajuste manual em período aberto (2026-01)

### 11.3. Caso 3: ERP Indisponível

**Cenário**: SAP ou ERP está em manutenção

**Fluxo**:
1. DB e GL atualizados com sucesso
2. Tenta POST /cancel para ERP
3. Timeout na primeira tentativa
4. Retry automático (2x mais)
5. Todas falham
6. **Ação**: Registra erro, continua com sucesso "partial"
7. Background job tentará sincronizar ERP depois

**Resultado**: Compensação local OK, ERP sync async

---

## XII. Monitoramento e Observabilidade

### 12.1. Logs Estruturados

```json
{
  "timestamp": "2026-01-24T10:31:15.456Z",
  "logLevel": "INFO",
  "event": "compensation_provision_completed",
  "processInstanceId": "PROC-2026-001",
  "provisionId": "PROV-2026-001-456789",
  "glosaId": "GLOS-2026-001-123456",
  "reversedAmount": 12500.75,
  "period": "2026-01",
  "journalEntryId": "JE-REV-COMP-...",
  "executionTimeMs": 567,
  "status": "SUCCESS",
  "actor": "SAGA_COMPENSATION_SYSTEM"
}
```

### 12.2. Alertas Críticos

- Taxa de erro > 1% → CRITICAL
- Tempo > 2s → WARNING
- GL integrity check falha → CRITICAL
- ERP sync falha > 30 min → WARNING

---

## XIII. Dependências

### 13.1. Dependências de Código

- `BaseDelegate`: Gerenciamento de variáveis
- `SagaCompensationService`: Registro de ações

### 13.2. Dependências Externas

| Sistema | Tipo | Dados | Frequência |
|---------|------|-------|-----------|
| PostgreSQL | BD | Provisions, GL, audit | Por transação |
| Kafka | Message Broker | Notificações | Assíncrono |
| ERP (SAP/Oracle) | Sistema Externo | Cancellation | Por compensação |

---

## XIV. Configuração

### 14.1. Parâmetros

```properties
compensation.provision.timeout.ms=10000
compensation.provision.max.retries=3
compensation.provision.kafka.topic=hospital.rcm.provision.reversed
compensation.provision.erp.timeout.ms=5000
```

### 14.2. Índices BD

```sql
CREATE INDEX idx_prov_id ON glosa_provisions(provision_id);
CREATE INDEX idx_prov_glosa_id ON glosa_provisions(glosa_id);
CREATE INDEX idx_je_reference ON journal_entries(reference_id);
CREATE INDEX idx_prov_audit_ts ON provision_audit_trail(timestamp DESC);
```

---

## XV. Próximas Etapas

Após CompensateProvisionDelegate:
- Se sucesso: Continua com próxima compensação (se houver)
- Se falha: Escala para manual review
- Glosa retorna a status PENDING_PROVISION para reavaliação

---

## XVI. Glossário

| Termo | Definição |
|-------|-----------|
| **Provision** | Reserva contábil para cobrir possíveis glosas |
| **Glosa** | Recusa total ou parcial de pagamento por payer |
| **Journal Entry** | Lançamento contábil em duplo-débito |
| **General Ledger** | Livro razão consolidado de todas as contas |
| **Reversão** | Lançamento oposto que anula anterior |
| **ERP** | Enterprise Resource Planning (SAP, Oracle, etc) |

---

**Aprovação**:
- **Autor**: Revenue Cycle Development Team
- **Revisor Técnico**: Arquiteto de Soluções
- **Aprovador**: CFO Faturamento
- **Data**: 2026-01-24
