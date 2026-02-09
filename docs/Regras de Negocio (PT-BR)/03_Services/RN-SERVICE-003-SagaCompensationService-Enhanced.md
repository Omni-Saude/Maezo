# RN-SagaCompensationService - Gerenciamento Distribuído de Transações (Versão Ampliada)

**Caminho:** `src/main/java/com/hospital/revenuecycle/service/SagaCompensationService.java`

**Versão:** 1.0.0 (Completa com análise detalhada)

---

## I. Resumo Executivo

### Descrição Geral
SagaCompensationService implementa padrão Saga para gerenciar transações distribuídas em arquitetura orientada a eventos. Garante consistência eventual entre múltiplos sistemas (TASY ERP, operadoras, accounting, recovery) através de compensação automática (rollback) quando operações falham.

### Criticidade do Negócio
- **Integridade Transacional:** Evita estados inconsistentes entre sistemas
- **Auditoria Completa:** Rastreamento LIFO de todas as compensações
- **Resiliência:** Circuit Breaker protege de falhas em cascata
- **Compliance:** SOX e LGPD requerem auditoria de transações críticas

### Tipos de Saga Suportados
```java
enum SagaType {
    BILLING,              // Faturamento e submissão de claims
    DENIALS,              // Processamento de glosas
    COLLECTION,           // Cobrança (pacientes/operadoras)
    GLOSA_MANAGEMENT,     // Gestão completa de glosas
    PAYMENT_ALLOCATION    // Alocação de pagamentos
}
```

### Dependências Críticas
```
SagaCompensationService
├── TasyClient (void duplicate claims, TASY operations)
├── DenialManagementClient (cancel appeals, restore denials)
├── RecoveryClient (cancel glosa recovery)
├── AccountingClient (reverse provisions)
├── CircuitBreakerCoordinator (fault isolation)
└── ApplicationEventPublisher (audit trail)
```

---

## II. Decisões Arquiteturais

### Padrões Implementados

#### 1. Saga Pattern (Garcia-Molina & Salem, 1987)
```java
// Transaction state machine
SagaStatus: STARTED → COMPLETED
            STARTED → COMPENSATING → COMPENSATED
            STARTED → COMPENSATING → COMPENSATION_FAILED
```

**Rationale:** Transações distribuídas em microserviços sem transações ACID nativas.

#### 2. In-Memory Transaction Tracking
```java
private final Map<String, SagaTransaction> transactions = new ConcurrentHashMap<>();
private final Map<String, List<CompensationAction>> compensationLog = new ConcurrentHashMap<>();
```

**Rationale:**
- **Pro:** Rápido (< 10ms latência)
- **Con:** Perda de estado em restart
- **Mitigação:** Roadmap - persistência em PostgreSQL

#### 3. LIFO Compensation (Last-In-First-Out)
```java
for (int i = actions.size() - 1; i >= 0; i--) {
    executeCompensationAction(actions.get(i));
}
```

**Racional:** Garante reversão na ordem oposta - mantém integridade relacional.

#### 4. Circuit Breaker Protection
```java
circuitBreakerCoordinator.executeVoid("tasy-client", () -> {
    tasyClient.voidDuplicateClaim(claimId);
});
```

**Racional:** Evita timeouts em cascata quando serviço externo está fora.

#### 5. Event-Based Auditing
```java
eventPublisher.publishEvent(
    new SagaCompensationEvent(action, entityId, status, timestamp, errorMessage)
);
```

**Racional:** Desacoplado - permite listeners (Kafka, audit logs, dashboards).

---

## III. Regras de Negócio Identificadas

### RN-SAG-01: Registro de Transação Saga

```java
public void registerTransaction(String transactionId, SagaType sagaType)
```

**Lógica:**
1. Cria novo `SagaTransaction` com:
   - `transactionId`: ID único (ex: "BILL-2024-001234")
   - `sagaType`: Tipo de saga (BILLING, DENIALS, etc.)
   - `status`: STARTED
   - `startTime`: LocalDateTime.now()
   - `compensationActions`: [] (vazio)

2. Armazena em ConcurrentHashMap (thread-safe)

**Business Context:**
- Início de qualquer processo distribuído
- Permite rastreabilidade cruzada de sistemas

**Exemplo:**
```java
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
   - Valida se existe (loga warning se não)

2. Cria `CompensationAction`:
   - `actionName`: Tipo de ação (submit_claim, appeal_denial, allocate_payment, etc.)
   - `timestamp`: LocalDateTime.now()
   - `compensationData`: Map com dados necessários para compensation
   - `status`: PENDING

3. Adiciona à lista `transaction.compensationActions`

**Business Context:**
- Registra cada passo forward para possível rollback
- Armazena dados necessários para desfazer operação
- Exemplo: Após submeter claim em TASY, registra `claimId` para posterior void

**Exemplo:**
```java
// Após submeter claim ao TASY com sucesso
Map<String, Object> compensationData = Map.of(
    "claimId", "CLM-2024-001234",
    "tasyBatchId", "BATCH-20240115-001",
    "submitDate", "2024-01-15T10:35:00"
);

sagaCompensationService.recordCompensationAction(
    "BILL-2024-001234",
    "submit_claim",
    compensationData
);

// Resultado: CompensationAction adicionada à lista
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

### RN-SAG-03: Execução de Compensação (CRÍTICA)

```java
public CompensationResult compensate(String transactionId, String failureReason)
```

**Lógica Detalhada:**

1. **Valida Transação Existe**
   - Se não encontra: retorna `CompensationResult.failure("Transaction not found")`

2. **Muda Status para COMPENSATING**
   - Indica que rollback está em progresso
   - Importante para monitoramento

3. **Executa Compensações em Ordem LIFO**
   ```java
   List<CompensationAction> actions = transaction.getCompensationActions();
   for (int i = actions.size() - 1; i >= 0; i--) {  // Último primeiro!
       CompensationAction action = actions.get(i);
       try {
           executeCompensationAction(action);
           action.setStatus(CompensationStatus.COMPLETED);
           compensatedActions.add(action.getActionName());
       } catch (Exception e) {
           action.setStatus(CompensationStatus.FAILED);
           action.setErrorMessage(e.getMessage());
           failedCompensations.add(action.getActionName());
       }
   }
   ```

4. **Determina Status Final**
   - Se `failedCompensations.isEmpty()`: status = COMPENSATED
   - Se alguma falha: status = COMPENSATION_FAILED

5. **Persiste em compensationLog**
   - Para auditoria e reprocessamento
   - Permite replay manual se necessário

6. **Retorna CompensationResult**
   - Estatísticas (total ações, compensadas, falhadas)
   - Lista de ações falhadas (requer intervenção)

**Exemplo:**
```java
// Processo falhou após 3 operações bem-sucedidas
// compensationActions: [submit_claim, allocate_payment, create_provision]

CompensationResult result = sagaCompensationService.compensate(
    "BILL-2024-001234",
    "Create provision failed - AccountingClient timeout"
);

// Execução em ordem reversa (LIFO):
// 1. compensate("create_provision") → SUCCESS
// 2. compensate("allocate_payment") → SUCCESS
// 3. compensate("submit_claim") → SUCCESS

// Resultado:
CompensationResult {
  success: true,
  transactionId: "BILL-2024-001234",
  compensatedActions: ["create_provision", "allocate_payment", "submit_claim"],
  failedActions: [],
  totalActions: 3
}

// Status da saga: COMPENSATED
```

---

### RN-SAG-04: Compensações Específicas

#### 4.1 Compensate Submit Claim
```java
private void compensateSubmit(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `claimId` de compensation data
2. Chama `tasyClient.voidDuplicateClaim(claimId)` via Circuit Breaker
3. Publica evento para auditoria

**Business Context:**
- Claim submetido ao TASY deve ser anulado se saga falha
- Evita duplicatas no faturamento
- Tasy handles duplicata internally

**Exemplo:**
```java
Map<String, Object> data = Map.of(
    "claimId", "CLM-2024-001234",
    "tasyBatchId", "BATCH-001"
);

compensateSubmit(data);
// Resultado: Claim CLM-2024-001234 anulado em TASY
```

---

#### 4.2 Compensate Appeal
```java
private void compensateAppeal(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `appealId` e `denialId`
2. Chama `denialClient.cancelAppeal(appealId)`
3. Chama `denialClient.restoreDenial(denialId, "PENDING")`

**Business Context:**
- Appeal iniciado mas saga falhou
- Cancela appeal e restora glosa ao status PENDING
- Permite reprocessamento posterior

**Exemplo:**
```java
Map<String, Object> data = Map.of(
    "appealId", "APPEAL-2024-001",
    "denialId", "DENIAL-2024-001",
    "glosaCode", "06"
);

compensateAppeal(data);
// Resultado: Appeal cancelado, glosa volta a PENDING
```

---

#### 4.3 Compensate Payment Allocation
```java
private void compensateAllocation(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `allocationId` e `amount`
2. Reverte alocação (operação interna, sem chamada externa)
3. Publica evento

**Business Context:**
- Pagamento alocado a um account deve ser desalocado
- Operação interna (não chama API externa)
- Mantém histórico de reversão

**Exemplo:**
```java
Map<String, Object> data = Map.of(
    "allocationId", "ALLOC-2024-001",
    "amount", "1500.00",
    "accountId", "ACC-001"
);

compensateAllocation(data);
// Resultado: Alocação desfeita, saldo retorna ao account
```

---

#### 4.4 Compensate Glosa Recovery
```java
private void compensateRecovery(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `recoveryId`
2. Chama `recoveryClient.cancelGlosaRecovery(recoveryId)`

**Business Context:**
- Recovery iniciado mas saga falhou
- Cancela recovery antes que chegue ao paciente/operadora
- Evita cobrança duplicada

**Exemplo:**
```java
Map<String, Object> data = Map.of(
    "recoveryId", "REC-2024-001",
    "glosaId", "GLOSA-001",
    "amount", "500.00"
);

compensateRecovery(data);
// Resultado: Recovery cancelado, glosa não é cobrada
```

---

#### 4.5 Compensate Provision
```java
private void compensateProvision(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `provisionId` e `amount`
2. Chama `accountingClient.reverseProvisionEntry(provisionId, amount)`

**Business Context:**
- Provisão contábil criada deve ser revertida
- Garante consistência do balanço
- Lançamentos contábeis reversos

**Exemplo:**
```java
Map<String, Object> data = Map.of(
    "provisionId", "PROV-2024-001",
    "amount", "4000.00",
    "glosaCode", "09"
);

compensateProvision(data);
// Resultado: Provisão revertida, P&L ajustado
```

---

#### 4.6 Compensate Billing Calculation
```java
private void compensateCalculate(Map<String, Object> data) throws Exception
```

**Ação:**
1. Recupera `calculationId`
2. Invalida cálculo de faturamento (operação interna em TASY)
3. Publica evento

**Business Context:**
- Cálculo de billing executado mas saga falhou
- Invalida para reprocessamento posterior
- Operação interna em TASY

---

### RN-SAG-05: Marcação de Sucesso

```java
public void completeTransaction(String transactionId)
```

**Lógica:**
1. Recupera `SagaTransaction`
2. Atualiza status: STARTED → COMPLETED
3. Define `endTime = LocalDateTime.now()`

**Business Context:**
- Saga completou com sucesso (happy path)
- Nenhuma compensação necessária
- Mantém histórico de transações bem-sucedidas

**Exemplo:**
```java
sagaCompensationService.completeTransaction("BILL-2024-001234");

// Resultado:
SagaTransaction {
  transactionId: "BILL-2024-001234",
  status: COMPLETED,
  startTime: "2024-01-15T10:30:00",
  endTime: "2024-01-15T10:35:30",
  compensationActions: [3 ações registradas mas não executadas]
}
```

---

### RN-SAG-06: Histórico de Compensação

```java
public List<CompensationAction> getCompensationHistory(String transactionId)
```

**Retorna:**
- Lista de ações de compensação executadas
- Útil para auditoria e troubleshooting
- Vazio se saga ainda não foi compensada

---

## IV. Fluxo de Processo Detalhado

### Cenário 1: Saga Bem-Sucedida (Happy Path)

```
Pré-condição: Processamento de faturamento normal

1. initiateBillingProcess("BILL-2024-001234")
   ↓
2. registerTransaction("BILL-2024-001234", BILLING)
   → Status: STARTED
   ↓
3. submitClaimToTasy("CLM-001")
   ↓ SUCCESS
4. recordCompensationAction(..., "submit_claim", {claimId: "CLM-001"})
   → Ação 1 registrada
   ↓
5. allocatePayment("PAY-001", 5000.00)
   ↓ SUCCESS
6. recordCompensationAction(..., "allocate_payment", {allocationId: "PAY-001"})
   → Ação 2 registrada
   ↓
7. createProvision("PROV-001", 4000.00)
   ↓ SUCCESS
8. recordCompensationAction(..., "create_provision", {provisionId: "PROV-001"})
   → Ação 3 registrada
   ↓
9. processCompleted()
   ↓
10. completeTransaction("BILL-2024-001234")
    → Status: COMPLETED
    → Nenhuma compensação executada
    → compensationActions armazenadas para auditoria

Resultado:
✓ Faturamento processado com sucesso
✓ 3 ações registradas
✓ Nenhuma compensação necessária
✓ Audit trail completa
```

---

### Cenário 2: Saga com Falha - Compensação Bem-Sucedida

```
Pré-condição: Falha em criar provisão (AccountingClient timeout)

1. registerTransaction("BILL-2024-002", BILLING)
   → Status: STARTED
   ↓
2. submitClaimToTasy("CLM-002") → SUCCESS
   recordCompensationAction(..., "submit_claim", ...)
   ↓
3. allocatePayment("PAY-002", 5000.00) → SUCCESS
   recordCompensationAction(..., "allocate_payment", ...)
   ↓
4. createProvision("PROV-002", 4000.00) → FAILURE (AccountingClient timeout)
   ⚠ Exception propagated
   ↓
5. compensate("BILL-2024-002", "Accounting API timeout")
   → Status: COMPENSATING
   → Executa compensações em LIFO (último primeiro):

   LOOP (i = 1; i >= 0; i--):

   Iteração 1 (i=1):
   ├─ action = "allocate_payment"
   ├─ compensateAllocation({allocationId: "PAY-002", ...})
   ├─ ✓ SUCCESS
   ├─ action.status = COMPLETED
   └─ compensatedActions.add("allocate_payment")

   Iteração 2 (i=0):
   ├─ action = "submit_claim"
   ├─ compensateSubmit({claimId: "CLM-002", ...})
   ├─ circuitBreaker.executeVoid("tasy-client", () → {
   │   tasyClient.voidDuplicateClaim("CLM-002")
   │ })
   ├─ ✓ SUCCESS
   ├─ action.status = COMPLETED
   └─ compensatedActions.add("submit_claim")

   Final:
   failedCompensations.isEmpty() → true
   → Status: COMPENSATED

Resultado:
CompensationResult {
  success: true,
  transactionId: "BILL-2024-002",
  compensatedActions: ["allocate_payment", "submit_claim"],
  failedActions: [],
  totalActions: 2
}

✓ Ambas compensações bem-sucedidas
✓ Saga marcada como COMPENSATED
✓ Dados consistentes (claim anulado, pagamento desalocado)
✓ Audit trail completa
```

---

### Cenário 3: Saga com Compensação Parcial (Falha em Compensação)

```
Pré-condição: Falha ao reverter provision (TASY offline)

1. compensate("BILL-2024-003", "External API failure")
   → Status: COMPENSATING
   → LIFO execution:

   Iteração 1 (i=2):
   ├─ action = "create_provision"
   ├─ compensateProvision({provisionId: "PROV-003", ...})
   ├─ circuitBreaker.executeVoid("accounting-client", ...)
   ├─ ✓ SUCCESS (accounting online)
   └─ action.status = COMPLETED

   Iteração 2 (i=1):
   ├─ action = "allocate_payment"
   ├─ compensateAllocation(...)
   ├─ ✓ SUCCESS
   └─ action.status = COMPLETED

   Iteração 3 (i=0):
   ├─ action = "submit_claim"
   ├─ compensateSubmit({claimId: "CLM-003", ...})
   ├─ circuitBreaker.executeVoid("tasy-client", ...)
   ├─ ✗ FAILURE (TASY offline, circuit breaker open)
   ├─ Exception: "Service unavailable"
   ├─ action.status = FAILED
   ├─ action.errorMessage = "Service unavailable"
   └─ failedCompensations.add("submit_claim")

   Final:
   failedCompensations.isEmpty() → false
   → Status: COMPENSATION_FAILED

Resultado:
CompensationResult {
  success: false,
  transactionId: "BILL-2024-003",
  compensatedActions: ["create_provision", "allocate_payment"],
  failedActions: ["submit_claim"],
  totalActions: 3
}

⚠ Compensação PARCIAL:
  - Provisão revertida ✓
  - Pagamento desalocado ✓
  - Claim NOT anulado em TASY ✗ (CRÍTICO)

Manual Action Required:
→ Operations team alerta: "CLM-003 precisa ser anulado manualmente em TASY"
→ Escalação: Aguarda TASY ficar online, então retry compensation
→ Ou: Manual cleanup no TASY
```

---

## V. Validações e Constraints

### RN-VAL-01: Transaction Exists
```java
SagaTransaction transaction = transactions.get(transactionId);
if (transaction == null) {
    logger.error("Cannot compensate - transaction not found: {}", transactionId);
    return CompensationResult.failure("Transaction not found");
}
```

**Validação:** Transação deve existir para compensação.

### RN-VAL-02: LIFO Order (Crítico)
```java
for (int i = actions.size() - 1; i >= 0; i--) {
    executeCompensationAction(actions.get(i));
}
```

**Validação:** Compensações DEVEM ser em ordem reversa.

### RN-VAL-03: Idempotency
```java
// Cada compensação deve ser idempotente:
// executar 2x = mesmo resultado

// Exemplo: voidDuplicateClaim()
// - 1ª execução: anula claim
// - 2ª execução: claim já anulado, retorna sucesso (não erro)
```

**Validação:** Compensações podem ser retentadas com segurança.

---

## VI. Integração com Circuit Breaker

```java
circuitBreakerCoordinator.executeVoid("tasy-client", () -> {
    tasyClient.voidDuplicateClaim(claimId);
});
```

**Estados do Circuit Breaker:**

| Estado | Comportamento |
|--------|--------------|
| CLOSED | Chamada passa normalmente |
| OPEN | Chamada falha imediatamente (sem tentar) |
| HALF_OPEN | Testa se serviço recuperou |

**Benefício:** Se TASY offline, não tenta 10x - abre circuit e informa rapidamente.

---

## VII. Event Publishing para Auditoria

```java
private void publishCompensationEvent(String action, String entityId, String status, String errorMessage) {
    SagaCompensationEvent event = new SagaCompensationEvent(
        action, entityId, status, LocalDateTime.now(), errorMessage
    );
    eventPublisher.publishEvent(event);
}
```

**Fluxo:**
- Evento publicado para cada compensação
- Listeners podem:
  - Escrever em Kafka (audit trail persistente)
  - Enviar para dashboard de monitoramento
  - Alertar via email/Slack se FAILED

---

## VIII. Dados e Modelos

### SagaTransaction
```java
@Data
@Builder
public static class SagaTransaction {
    private String transactionId;                           // Único ID
    private SagaType sagaType;                              // BILLING, DENIALS, etc.
    private SagaStatus status;                              // STARTED, COMPENSATING, etc.
    private LocalDateTime startTime;                        // Quando iniciou
    private LocalDateTime endTime;                          // Quando finalizou
    private List<CompensationAction> compensationActions;  // Ações executadas
}
```

### CompensationAction
```java
@Data
@Builder
public static class CompensationAction {
    private String actionName;                              // submit_claim, appeal_denial, etc.
    private LocalDateTime timestamp;                        // Quando foi registrada
    private Map<String, Object> compensationData;          // Dados para rollback
    private CompensationStatus status;                      // PENDING, COMPLETED, FAILED
    private String errorMessage;                            // Se falhou
}
```

### CompensationResult
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

## IX. Compliance e Regulamentações

### SOX (Sarbanes-Oxley)
**Obrigação:** Auditoria completa de transações financeiras.

**Implementação:**
```java
compensationLog.put(transactionId, new ArrayList<>(actions));
publishCompensationEvent(...);  // Para listeners
```

### LGPD - Art. 48 (Comunicação de Incidentes)
**Obrigação:** Alertar sobre falhas que afetem dados pessoais.

**Implementação:**
```java
if (!failedCompensations.isEmpty()) {
    log.error("LGPD Alert: Compensation failed - data integrity risk");
    // Alertar Data Protection Officer
}
```

---

## X. Roadmap de Melhorias

### 1. Persistência em PostgreSQL (Alta Prioridade)
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
    transaction_id VARCHAR(100) REFERENCES saga_transactions,
    action_name VARCHAR(100),
    compensation_data JSONB,
    status VARCHAR(50),
    error_message TEXT,
    timestamp TIMESTAMP
);
```

**Benefício:** Sobrevive a restarts, full audit trail.

### 2. Async Compensation (Kafka)
```java
@Async
public CompletableFuture<CompensationResult> compensateAsync(String transactionId) {
    return CompletableFuture.completedFuture(compensate(transactionId, "Async"));
}
```

**Benefício:** Não bloqueia thread principal.

### 3. Retry Logic com Exponential Backoff
```java
@Retryable(value = {Exception.class}, maxAttempts = 3, backoff = @Backoff(delay = 5000))
private void compensateSubmit(Map<String, Object> data) throws Exception { }
```

**Benefício:** Recuperação automática de falhas transitórias.

---

## Conclusão

SagaCompensationService implementa padrão Saga crítico para consistência em transações distribuídas. Execução LIFO garante rollback ordenado. Circuit Breaker evita falhas em cascata. Event Publishing permite auditoria descentralizada. Estado em-memory é RISCO ALTO - migração para PostgreSQL é prioritária. Compensações são idempotentes e tolerantes a falhas parciais. Integração com múltiplos sistemas (TASY, Accounting, Denial Management) via clientes bem-definidos. Próximas melhorias: PostgreSQL persistence (crítica), async compensation via Kafka, retry logic automático, dashboard de monitoramento de sagas.
