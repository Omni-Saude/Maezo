# RN-IdempotencyRecord: Registro de Idempotência

## 📋 Metadados
- **ID**: RN-IdempotencyRecord
- **Categoria**: Models > Idempotency
- **Versão**: 1.0
- **Última Atualização**: 2025-12-23
- **Arquivo**: `IdempotencyRecord.java`
- **Localização**: `com.hospital.revenuecycle.model`
- **Tabela**: `idempotency_records`

---

## 🎯 Visão Geral

Entidade JPA que armazena registros de idempotência para prevenir execução duplicada de operações críticas. Implementa o padrão Idempotency Key baseado em ADR-007.

### Problema Resolvido

**Cenário**: Cliente envia requisição → Timeout de rede → Cliente retenta → Operação executada 2x

**Solução**: Idempotency Key garante que operação execute apenas uma vez, mesmo com múltiplas tentativas.

---

## 🗃️ Estrutura da Entidade

### Campos Principais

| Campo | Tipo | Descrição | Exemplo |
|-------|------|-----------|---------|
| `id` | Long | PK auto-increment | `12345` |
| `idempotencyKey` | String(255) | Chave única de idempotência | `proc-123_submit-claim_abc123` |
| `processInstanceId` | String(64) | Camunda Process Instance ID | `a3f2e1d4-5c6b-7a8b-9c0d-1e2f3a4b5c6d` |
| `activityId` | String(255) | BPMN Activity ID | `Task_SubmitClaim` |
| `operationName` | String(100) | Nome da operação | `submit_claim`, `process_payment` |
| `status` | Enum | Status da operação | `PENDING`, `SUCCESS`, `FAILED` |
| `resultData` | TEXT (JSON) | Resultado serializado | `{"claimId": "CLM-001", "status": "approved"}` |
| `errorMessage` | TEXT | Mensagem de erro | `Connection timeout to portal` |
| `retryCount` | Integer | Contador de retentativas | `0`, `1`, `2` |
| `createdAt` | LocalDateTime | Timestamp de criação | `2025-12-23T10:30:00` |
| `updatedAt` | LocalDateTime | Timestamp de atualização | `2025-12-23T10:31:15` |
| `expiresAt` | LocalDateTime | Timestamp de expiração | `2025-12-24T10:30:00` (24h TTL) |

### Índices

```sql
CREATE UNIQUE INDEX idx_idempotency_key ON idempotency_records(idempotency_key);
CREATE INDEX idx_process_instance ON idempotency_records(process_instance_id);
CREATE INDEX idx_created_at ON idempotency_records(created_at);
CREATE INDEX idx_expires_at ON idempotency_records(expires_at);
```

---

## 🔑 Geração de Idempotency Key

### Composição da Chave

```
idempotencyKey = hash(processInstanceId + activityId + operationName + inputHash)
```

### Exemplo de Geração

```java
String processInstanceId = "a3f2e1d4-5c6b-7a8b-9c0d-1e2f3a4b5c6d";
String activityId = "Task_SubmitClaim";
String operationName = "submit_claim";
String inputHash = DigestUtils.md5Hex(JSON.serialize(inputParams));

String idempotencyKey = String.format("%s_%s_%s_%s",
    processInstanceId,
    activityId,
    operationName,
    inputHash);

// Result: "a3f2e1d4_Task_SubmitClaim_submit_claim_7a8b9c0d"
```

---

## 🔄 Estados da Operação

```
┌─────────────────────────────────────────────────────────────┐
│                 Operation Lifecycle                         │
└─────────────────────────────────────────────────────────────┘

┌──────────┐
│ PENDING  │  ◄───── Operation started, in progress
└────┬─────┘
     │
     ├─────► SUCCESS  ◄─────┬──── Operation completed
     │                      │     Result cached
     └─────► FAILED   ◄─────┘     Error recorded
```

### Status: PENDING

- Operação em andamento
- Primeira execução ou retry em progresso
- Retries ainda permitidos

### Status: SUCCESS

- Operação completada com sucesso
- `resultData` contém resultado serializado
- Próximas tentativas retornam resultado cached

### Status: FAILED

- Operação falhou após todas as retentativas
- `errorMessage` contém descrição do erro
- Próximas tentativas podem resultar em novo PENDING

---

## ⏱️ Time-to-Live (TTL)

### Estratégia de Expiração

```java
LocalDateTime expiresAt = LocalDateTime.now().plusHours(24);
```

**Default**: 24 horas

### Limpeza Automática

```java
@Scheduled(cron = "0 0 * * * *") // Every hour
public void cleanupExpiredRecords() {
    idempotencyRepository.deleteByExpiresAtBefore(LocalDateTime.now());
}
```

---

## 🔧 Métodos Principais

### isExpired()

```java
public boolean isExpired() {
    return LocalDateTime.now().isAfter(expiresAt);
}
```

### canRetry(maxRetries)

```java
public boolean canRetry(int maxRetries) {
    return retryCount < maxRetries;
}
```

### incrementRetryCount()

```java
public void incrementRetryCount() {
    this.retryCount++;
    this.updatedAt = LocalDateTime.now();
}
```

### markSuccess(result)

```java
public void markSuccess(String result) {
    this.status = OperationStatus.SUCCESS;
    this.resultData = result;
    this.errorMessage = null;
    this.updatedAt = LocalDateTime.now();
}
```

### markFailed(error)

```java
public void markFailed(String error) {
    this.status = OperationStatus.FAILED;
    this.errorMessage = error;
    this.updatedAt = LocalDateTime.now();
}
```

---

## 🧪 Exemplo de Uso

### Service Implementation

```java
@Service
public class IdempotentClaimSubmissionService {

    @Autowired
    private IdempotencyRecordRepository idempotencyRepo;

    @Autowired
    private ClaimSubmissionService claimService;

    public ClaimSubmissionResult submitClaim(
            String processInstanceId,
            String activityId,
            ClaimData claimData) {

        // 1. Generate idempotency key
        String idempotencyKey = generateKey(
            processInstanceId, activityId, "submit_claim", claimData);

        // 2. Check for existing record
        Optional<IdempotencyRecord> existing =
            idempotencyRepo.findByIdempotencyKey(idempotencyKey);

        if (existing.isPresent()) {
            IdempotencyRecord record = existing.get();

            if (record.getStatus() == OperationStatus.SUCCESS) {
                // Return cached result
                return deserialize(record.getResultData());
            }

            if (record.getStatus() == OperationStatus.PENDING) {
                // Operation still in progress
                throw new OperationInProgressException();
            }

            if (!record.canRetry(3)) {
                // Max retries exhausted
                throw new MaxRetriesExceededException();
            }

            // Increment retry count
            record.incrementRetryCount();
            idempotencyRepo.save(record);
        }

        // 3. Create new record
        IdempotencyRecord record = IdempotencyRecord.builder()
            .idempotencyKey(idempotencyKey)
            .processInstanceId(processInstanceId)
            .activityId(activityId)
            .operationName("submit_claim")
            .status(OperationStatus.PENDING)
            .expiresAt(LocalDateTime.now().plusHours(24))
            .build();

        idempotencyRepo.save(record);

        try {
            // 4. Execute operation
            ClaimSubmissionResult result = claimService.submit(claimData);

            // 5. Mark success
            record.markSuccess(serialize(result));
            idempotencyRepo.save(record);

            return result;

        } catch (Exception e) {
            // 6. Mark failed
            record.markFailed(e.getMessage());
            idempotencyRepo.save(record);
            throw e;
        }
    }
}
```

---

## 📊 Queries Comuns

### Buscar por Chave

```java
Optional<IdempotencyRecord> findByIdempotencyKey(String key);
```

### Buscar por Process Instance

```java
List<IdempotencyRecord> findByProcessInstanceId(String processInstanceId);
```

### Limpar Expirados

```java
@Modifying
@Query("DELETE FROM IdempotencyRecord r WHERE r.expiresAt < :now")
void deleteByExpiresAtBefore(@Param("now") LocalDateTime now);
```

### Operações Pendentes

```java
List<IdempotencyRecord> findByStatusAndCreatedAtBefore(
    OperationStatus status, LocalDateTime cutoff);
```

---

## 🎯 Boas Práticas

### ✅ DO

1. **Sempre gerar chave única** baseada em inputs
2. **Definir TTL apropriado** (não muito curto, não muito longo)
3. **Serializar resultados** em formato estável (JSON)
4. **Implementar cleanup scheduled** para registros expirados
5. **Logar tentativas de retry** para debugging

### ❌ DON'T

1. ❌ Não usar timestamp como parte da chave (não é idempotente)
2. ❌ Não armazenar dados sensíveis não-criptografados
3. ❌ Não manter registros SUCCESS indefinidamente
4. ❌ Não ignorar status PENDING (pode causar race condition)
5. ❌ Não usar chaves muito longas (> 255 chars)

---

## 📚 Referências

- **ADR-007**: Idempotency Pattern Implementation
- **Pattern**: Idempotency Key Pattern
- **RFC 7231**: HTTP Idempotency
- **Database**: PostgreSQL with UNIQUE constraint

---

**Status**: ✅ PRODUCTION READY
**JPA Entity**: ✅ Validated
**Migrations**: ✅ Included
**Indexes**: ✅ Optimized
