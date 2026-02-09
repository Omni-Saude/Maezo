# RN-SagaCompensationService - Gerenciamento de Transações Distribuídas

**Caminho:** `src/main/java/com/hospital/revenuecycle/service/SagaCompensationService.java`

---

## I. Resumo Executivo

### Descrição Geral
SagaCompensationService implementa padrão Saga para gerenciar transações distribuídas no ciclo de receita, garantindo compensação (rollback) automática quando operações falham em sistemas externos (TASY, operadoras, accounting).

### Criticidade do Negócio
- **Consistência de Dados:** Garante que falhas não deixam dados inconsistentes entre sistemas
- **Auditoria:** Rastreamento completo de compensações executadas
- **Recovery Automático:** Circuit Breaker protege compensations de falhas em cascata
- **Compliance:** Auditoria de transações requerida por SOX e LGPD

### Dependências Críticas
```
SagaCompensationService
├── TasyClient (void duplicates, restore state)
├── DenialManagementClient (cancel appeals, restore denials)
├── RecoveryClient (cancel glosa recovery)
├── AccountingClient (reverse provisions)
└── CircuitBreakerCoordinator (protect external calls)
```

---

## II. Decisões Arquiteturais

### Padrões Implementados
```java
@Service
@RequiredArgsConstructor
// In-memory transaction tracking
private final Map<String, SagaTransaction> transactions = new ConcurrentHashMap<>();
private final Map<String, List<CompensationAction>> compensationLog = new ConcurrentHashMap<>();

// Circuit Breaker protection
private final CircuitBreakerCoordinator circuitBreakerCoordinator;

// Event publishing for monitoring
private final ApplicationEventPublisher eventPublisher;
```

**Rationale:**
- **ConcurrentHashMap:** Thread-safe para processamento paralelo de sagas
- **Circuit Breaker:** Protege compensações de falhas em cascata
- **Event Publishing:** Auditoria e monitoramento via Spring Events
- **LIFO Compensation:** Compensa na ordem inversa (Last-In-First-Out)

### Trade-offs
| Decisão | Pro | Contra | Mitigação |
|---------|-----|--------|-----------|
| In-memory state | Rápido, simples | Perda de estado em restart | **CRÍTICO:** Roadmap - persistir em PostgreSQL |
| Synchronous compensation | Simples rastreamento | Pode ser lento (múltiplas APIs) | Circuit Breaker + timeout |
| Event-based auditing | Desacoplado | Eventos podem ser perdidos | Usar message broker (Kafka) |

---

## III. Regras de Negócio Identificadas

### RN-SAG-01: Registro de Transação Saga
```java
public void registerTransaction(String transactionId, SagaType sagaType)
```

**Lógica:**
1. Cria `SagaTransaction` com:
   - `transactionId` único
   - `sagaType` (BILLING, DENIALS, COLLECTION, etc.)
   - `status = STARTED`
   - `startTime = LocalDateTime.now()`
   - `compensationActions = []` (lista vazia)
2. Armazena em `Map<transactionId, SagaTransaction>`

**Business Context:**
- **Início de Saga:** Cada processo distribuído registra saga antes de iniciar operações
- **Rastreabilidade:** Transaction ID permite correlacionar logs de múltiplos sistemas

**Exemplo:**
```java
// Início do processo de faturamento
sagaCompensationService.registerTransaction("BILL-2024-001234", SagaType.BILLING);

// Estado criado:
SagaTransaction {
  transactionId: "BILL-2024-001234",
  sagaType: BILLING,
  status: STARTED,
  startTime: "2024-01-15T10:30:00",
  compensationActions: []
}
```

---

### RN-SAG-02: Registro de Ação de Compensação
```java
public void recordCompensationAction(
    String transactionId,
    String actionName,
    Map<String, Object> compensationData)
```

**Lógica:**
1. Recupera `SagaTransaction` do Map
2. Cria `CompensationAction` com:
   - `actionName` (ex: "submit_claim")
   - `timestamp = LocalDateTime.now()`
   - `compensationData` (dados necessários para rollback)
   - `status = PENDING`
3. Adiciona à lista `transaction.compensationActions`

**Business Context:**
- **Forward Progress Tracking:** Registra cada operação forward para possível compensação
- **Rollback Data:** Armazena dados necessários para desfazer operação

**Exemplo:**
```java
// Após submeter claim ao TASY
Map<String, Object> data = Map.of(
    "claimId", "CLM-2024-001234",
    "tasyBatchId", "BATCH-20240115-001"
);
sagaCompensationService.recordCompensationAction(
    "BILL-2024-001234",
    "submit_claim",
    data
);

// Estado atualizado:
SagaTransaction {
  ...
  compensationActions: [
    {
      actionName: "submit_claim",
      timestamp: "2024-01-15T10:35:00",
      compensationData: {claimId: "CLM-2024-001234", ...},
      status: PENDING
    }
  ]
}
```

---

### RN-SAG-03: Execução de Compensação ⚠️ CRÍTICA
```java
public CompensationResult compensate(String transactionId, String failureReason)
```

**Lógica:**
1. Recupera `SagaTransaction` do Map
2. Valida se transação existe (se não: retorna failure)
3. Atualiza status: `STARTED → COMPENSATING`
4. **Executa compensações em ordem reversa (LIFO):**
   ```java
   for (int i = actions.size() - 1; i >= 0; i--) {
       executeCompensationAction(actions.get(i));
   }
   ```
5. Para cada compensação:
   - Try: executa compensação específica (baseada em `actionName`)
   - Success: `status = COMPLETED`, adiciona a `compensatedActions`
   - Failure: `status = FAILED`, adiciona a `failedActions`
6. Atualiza status final:
   - Todas success → `COMPENSATED`
   - Alguma failure → `COMPENSATION_FAILED`
7. Armazena em `compensationLog` para auditoria
8. Retorna `CompensationResult` com estatísticas

**Business Context:**
- **Rollback Distribuído:** Desfaz operações em múltiplos sistemas (TASY, operadora, accounting)
- **LIFO Order:** Compensa na ordem inversa para manter consistência
- **Partial Compensation:** Se alguma compensação falha, marca como `COMPENSATION_FAILED` mas continua tentando as demais

**Exemplo:**
```java
// Processo falhou após 3 operações
// compensationActions: [submit_claim, allocate_payment, create_provision]

sagaCompensationService.compensate("BILL-2024-001234", "TASY API timeout");

// Execução em ordem reversa:
// 1. Compensar "create_provision" → SUCCESS (reversed accounting entry)
// 2. Compensar "allocate_payment" → SUCCESS (reversed allocation)
// 3. Compensar "submit_claim" → SUCCESS (voided duplicate claim in TASY)

// Resultado:
CompensationResult {
  success: true,
  transactionId: "BILL-2024-001234",
  compensatedActions: ["create_provision", "allocate_payment", "submit_claim"],
  failedActions: [],
  totalActions: 3
}
```

---

### RN-SAG-04: Compensações Específicas

#### Compensate Submit Claim
```java
private void compensateSubmit(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `claimId` dos compensation data
2. Chama `tasyClient.voidDuplicateClaim(claimId)` via Circuit Breaker
3. Publica evento `SagaCompensationEvent` (audit)

**Business Context:**
- Claim submetido ao TASY deve ser anulado se processo falha posteriormente
- Evita duplicatas no sistema de faturamento

---

#### Compensate Appeal
```java
private void compensateAppeal(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `appealId` e `denialId`
2. Chama `denialClient.cancelAppeal(appealId)`
3. Chama `denialClient.restoreDenial(denialId, "PENDING")`

**Business Context:**
- Appeal iniciado mas processo falhou → cancela appeal
- Restora denial ao status PENDING para reprocessamento

---

#### Compensate Allocation
```java
private void compensateAllocation(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `allocationId` e `amount`
2. Reverte alocação de pagamento (operação interna)

**Business Context:**
- Pagamento alocado a uma conta deve ser desalocado se processo falha
- Operação interna (sem API externa)

---

#### Compensate Recovery
```java
private void compensateRecovery(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `recoveryId`
2. Chama `recoveryClient.cancelGlosaRecovery(recoveryId)`

**Business Context:**
- Glosa recovery iniciado mas falhou → cancela recovery
- Evita cobrança duplicada ao paciente/operadora

---

#### Compensate Provision
```java
private void compensateProvision(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `provisionId` e `amount`
2. Chama `accountingClient.reverseProvisionEntry(provisionId, amount)`

**Business Context:**
- Provisão contábil criada deve ser revertida se processo falha
- Garante consistência contábil (não deixa provisão órfã)

---

### RN-SAG-05: Marcação de Sucesso
```java
public void completeTransaction(String transactionId)
```

**Lógica:**
1. Recupera `SagaTransaction` do Map
2. Atualiza status: `STARTED → COMPLETED`
3. Define `endTime = LocalDateTime.now()`

**Business Context:**
- **Happy Path:** Processo completou com sucesso, nenhuma compensação necessária
- Mantém histórico de transações bem-sucedidas

---

## IV. Fluxo de Processo Detalhado

### Cenário 1: Saga Bem-Sucedida (Happy Path)
```
1. Inicia processo de faturamento
   ↓
2. registerTransaction("BILL-001", BILLING)
   ↓
3. Submete claim ao TASY
   ↓
4. recordCompensationAction("BILL-001", "submit_claim", {claimId: "CLM-001"})
   ↓
5. Aloca pagamento
   ↓
6. recordCompensationAction("BILL-001", "allocate_payment", {allocationId: "PAY-001"})
   ↓
7. Cria provisão contábil
   ↓
8. recordCompensationAction("BILL-001", "create_provision", {provisionId: "PROV-001"})
   ↓
9. Processo completa com sucesso
   ↓
10. completeTransaction("BILL-001")
    ↓
Status: COMPLETED (nenhuma compensação executada)
```

---

### Cenário 2: Saga com Falha (Compensação Necessária)
```
1. Inicia processo de faturamento
   ↓
2. registerTransaction("BILL-002", BILLING)
   ↓
3. Submete claim ao TASY → SUCCESS
   ↓
4. recordCompensationAction("BILL-002", "submit_claim", {claimId: "CLM-002"})
   ↓
5. Aloca pagamento → SUCCESS
   ↓
6. recordCompensationAction("BILL-002", "allocate_payment", {allocationId: "PAY-002"})
   ↓
7. Cria provisão contábil → FAILURE (AccountingClient timeout)
   ↓
8. Trigger compensação:
   compensate("BILL-002", "Accounting API timeout")
   ↓
9. Compensações em ordem reversa (LIFO):
   a) compensateAllocation() → SUCCESS (payment deallocated)
   b) compensateSubmit() → SUCCESS (claim voided in TASY)
   ↓
10. Status: COMPENSATED
    Resultado: 2/2 compensações bem-sucedidas
```

---

### Cenário 3: Compensação Parcial (Falha na Compensação)
```
1. compensate("BILL-003", "External API failure")
   ↓
2. Compensações em ordem reversa:
   a) compensateProvision() → SUCCESS
   b) compensateAllocation() → SUCCESS
   c) compensateSubmit() → FAILURE (TASY offline)
   ↓
3. Status: COMPENSATION_FAILED
   compensatedActions: ["compensate_provision", "compensate_allocation"]
   failedActions: ["compensate_submit"]
   ↓
4. Alerta enviado ao operations team:
   "Manual intervention required: Failed to void claim CLM-003 in TASY"
   ↓
5. Manual cleanup executado
```

---

## V. Validações e Constraints

### Validações de Negócio

**RN-VAL-01: Transaction Exists**
```java
if (transaction == null) {
    log.error("Cannot compensate - transaction not found: {}", transactionId);
    return CompensationResult.failure("Transaction not found");
}
```

**RN-VAL-02: LIFO Order**
```java
// Compensações DEVEM ser executadas em ordem reversa
for (int i = actions.size() - 1; i >= 0; i--) {
    executeCompensationAction(actions.get(i));
}
```

**RN-VAL-03: Idempotency**
```java
// Compensações devem ser idempotentes (executar 2x = mesmo resultado)
// Exemplo: voidDuplicateClaim() verifica se já anulado antes de anular
```

---

## VI. Cálculos e Algoritmos

### Algoritmo: LIFO Compensation
```java
public CompensationResult compensate(String transactionId, String failureReason) {
    SagaTransaction transaction = transactions.get(transactionId);
    transaction.setStatus(SagaStatus.COMPENSATING);

    List<CompensationAction> actions = transaction.getCompensationActions();
    List<String> compensatedActions = new ArrayList<>();
    List<String> failedCompensations = new ArrayList<>();

    // LIFO: Last-In-First-Out (ordem reversa)
    for (int i = actions.size() - 1; i >= 0; i--) {
        CompensationAction action = actions.get(i);

        try {
            executeCompensationAction(action);
            action.setStatus(CompensationStatus.COMPLETED);
            compensatedActions.add(action.getActionName());
        } catch (Exception e) {
            action.setStatus(CompensationStatus.FAILED);
            failedCompensations.add(action.getActionName());
        }
    }

    // Determina status final
    if (failedCompensations.isEmpty()) {
        transaction.setStatus(SagaStatus.COMPENSATED);
    } else {
        transaction.setStatus(SagaStatus.COMPENSATION_FAILED);
    }

    return CompensationResult.builder()
        .success(failedCompensations.isEmpty())
        .compensatedActions(compensatedActions)
        .failedActions(failedCompensations)
        .build();
}
```

---

## VII. Integrações de Sistema

### Integração com Circuit Breaker Coordinator
```java
private final CircuitBreakerCoordinator circuitBreakerCoordinator;

// Protege chamadas externas durante compensação
circuitBreakerCoordinator.executeVoid("tasy-client", () -> {
    tasyClient.voidDuplicateClaim(claimId);
});
```

**Benefício:** Se TASY estiver offline, circuit breaker abre e evita timeouts em cascata.

---

## VIII. Tratamento de Erros e Exceções

### Exception Handling
```java
try {
    executeCompensationAction(action);
    action.setStatus(CompensationStatus.COMPLETED);
    compensatedActions.add(action.getActionName());
    log.info("Compensation successful: action={}", action.getActionName());
} catch (Exception e) {
    log.error("Compensation failed: action={}, error={}", action.getActionName(), e.getMessage(), e);
    action.setStatus(CompensationStatus.FAILED);
    action.setErrorMessage(e.getMessage());
    failedCompensations.add(action.getActionName());
}
```

**Estratégia:**
- **Continue on failure:** Se uma compensação falha, continua executando as demais
- **Log all failures:** Todas as falhas são logadas para análise
- **Manual intervention:** Compensações falhadas requerem intervenção manual

---

## IX. Dados e Modelos

### Modelo: SagaTransaction
```java
@Data
@Builder
public static class SagaTransaction {
    private String transactionId;
    private SagaType sagaType;              // BILLING, DENIALS, COLLECTION, etc.
    private SagaStatus status;              // STARTED, COMPLETED, COMPENSATING, COMPENSATED, COMPENSATION_FAILED
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private List<CompensationAction> compensationActions;
}
```

---

### Modelo: CompensationAction
```java
@Data
@Builder
public static class CompensationAction {
    private String actionName;              // submit_claim, appeal_denial, etc.
    private LocalDateTime timestamp;
    private Map<String, Object> compensationData;  // Dados necessários para compensação
    private CompensationStatus status;      // PENDING, COMPLETED, FAILED
    private String errorMessage;            // Mensagem de erro se falhou
}
```

---

### Modelo: CompensationResult
```java
@Data
@Builder
public static class CompensationResult {
    private boolean success;
    private String transactionId;
    private List<String> compensatedActions;
    private List<String> failedActions;
    private int totalActions;
}
```

---

## X. Compliance e Regulamentações

### SOX (Sarbanes-Oxley) - Auditoria de Transações Financeiras
**Obrigação:** Rastreamento completo de transações financeiras e compensações.

**Implementação:**
```java
// Compensation log armazenado para auditoria
compensationLog.put(transactionId, new ArrayList<>(actions));

// Eventos publicados para audit trail
publishCompensationEvent("compensate_submit", claimId, "SUCCESS");
```

---

### LGPD - Art. 48 (Comunicação de Incidentes)
**Obrigação:** Comunicar falhas que afetem dados pessoais.

**Implementação:**
```java
if (!failedCompensations.isEmpty()) {
    log.error("Some compensations failed: transaction={}, failed={}",
             transactionId, failedCompensations);
    // Alertar Data Protection Officer se dados pessoais afetados
}
```

---

## XI. Camunda 7 → 8 Migration

### Impacto: **MÉDIO**
SagaCompensationService é chamado por processos Camunda, mas não depende diretamente da API do Camunda.

### Mudanças Necessárias

**Camunda 7 (Atual):**
```java
// Service Task chama método diretamente
#{sagaCompensationService.registerTransaction(execution.getVariable('transactionId'), 'BILLING')}
```

**Camunda 8 (Zeebe):**
```java
@ZeebeWorker(type = "register-saga-transaction")
public void registerTransaction(JobClient client, ActivatedJob job) {
    String transactionId = (String) job.getVariablesAsMap().get("transactionId");
    String sagaType = (String) job.getVariablesAsMap().get("sagaType");

    registerTransaction(transactionId, SagaType.valueOf(sagaType));

    client.newCompleteCommand(job.getKey()).send().join();
}
```

### Estimativa: 8 horas (criar Zeebe Workers para todos os métodos públicos)

---

## XII. DDD Bounded Context

### Context: **Transaction Management & Orchestration**

### Aggregates
```
Saga Transaction Aggregate Root
├── TransactionId
├── SagaType
├── Status (STARTED, COMPENSATING, COMPENSATED, COMPENSATION_FAILED)
├── CompensationActions Collection
│   ├── ActionName
│   ├── CompensationData
│   └── Status (PENDING, COMPLETED, FAILED)
└── Timeline (start, end timestamps)
```

### Domain Events
```java
public class SagaCompensationEvent {
    private String action;
    private String entityId;
    private String status;          // SUCCESS, FAILED
    private LocalDateTime timestamp;
    private String errorMessage;
}
```

---

## XIII. Performance e SLAs

### SLAs Definidos

| Operação | SLA Latência | Dependências |
|----------|--------------|--------------|
| registerTransaction | < 5ms | In-memory Map |
| recordCompensationAction | < 10ms | In-memory Map |
| compensate (3 actions) | < 5s | External APIs (TASY, Accounting) |
| compensate (10 actions) | < 15s | External APIs |

### Complexidade Ciclomática

| Método | CC | Classificação |
|--------|----|--------------|
| `compensate()` | 15 | HIGH |
| `executeCompensationAction()` | 8 | MODERATE |
| `recordCompensationAction()` | 4 | LOW |

**Média:** CC = 9.0 (MODERATE) ✓

---

### Melhorias Recomendadas

**1. Persistence (PostgreSQL)**
```sql
CREATE TABLE saga_transactions (
  transaction_id VARCHAR(100) PRIMARY KEY,
  saga_type VARCHAR(50),
  status VARCHAR(50),
  start_time TIMESTAMP,
  end_time TIMESTAMP
);

CREATE TABLE compensation_actions (
  id UUID PRIMARY KEY,
  transaction_id VARCHAR(100) REFERENCES saga_transactions(transaction_id),
  action_name VARCHAR(100),
  compensation_data JSONB,
  status VARCHAR(50),
  error_message TEXT,
  timestamp TIMESTAMP
);
```

**Benefício:** Survives application restarts, full audit trail.

---

**2. Async Compensation via Message Queue**
```java
@Async
public CompletableFuture<CompensationResult> compensateAsync(String transactionId) {
    return CompletableFuture.completedFuture(compensate(transactionId, "Async compensation"));
}
```

**Benefício:** Não bloqueia thread principal durante compensações lentas.

---

**3. Retry Logic para Compensações Falhadas**
```java
@Retryable(
    value = {TasyApiException.class},
    maxAttempts = 3,
    backoff = @Backoff(delay = 5000, multiplier = 2)
)
private void compensateSubmit(Map<String, Object> data) throws Exception {
    // Tenta até 3x com backoff exponencial (5s, 10s, 20s)
}
```

---

## Conclusão

SagaCompensationService implementa padrão **Saga crítico** para garantir consistência de dados em transações distribuídas. Proteção via Circuit Breaker evita falhas em cascata. Estado in-memory é **RISCO ALTO** (perda em restart). Compensações são executadas em ordem LIFO (Last-In-First-Out). Migração Camunda 8: 8h (criar Zeebe Workers). Próximas melhorias: PostgreSQL persistence (alta prioridade), async compensation via Kafka, retry logic para compensações falhadas.
