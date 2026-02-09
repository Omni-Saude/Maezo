# RN-IdempotencyRepository

## Identificação
- **ID**: RN-IdempotencyRepository
- **Nome**: Repositório de Idempotência
- **Versão**: 1.0
- **Autor**: Revenue Cycle Development Team
- **Tipo**: Repository Interface / Infrastructure

## Descrição
Repositório JPA para gerenciamento de registros de idempotência, garantindo processamento exactly-once de operações críticas no ciclo de receita.

## Contexto de Negócio
Previne duplicação de operações críticas:
- Submissões duplicadas de contas médicas
- Pagamentos processados múltiplas vezes
- Notificações enviadas em duplicata
- Lançamentos contábeis duplicados

## Padrão de Idempotência

### ADR-007 Implementation
Baseado em Architecture Decision Record ADR-007 para implementação de padrão de idempotência em integrações críticas.

### Chave de Idempotência
Formato: `{operationName}:{entityId}:{timestamp}`

Exemplo: `SUBMIT_CLAIM:CLM-12345:2025-01-12T10:30:00Z`

## Métodos Principais

### findByIdempotencyKey
```java
Optional<IdempotencyRecord> findByIdempotencyKey(String idempotencyKey)
```

**Uso**: Verificar se operação já foi processada

### existsByIdempotencyKey
```java
boolean existsByIdempotencyKey(String idempotencyKey)
```

**Uso**: Check rápido de duplicação

### findByProcessInstanceId
```java
List<IdempotencyRecord> findByProcessInstanceId(String processInstanceId)
```

**Uso**: Listar todas operações de um processo Camunda

### findByProcessInstanceIdAndActivityId
```java
List<IdempotencyRecord> findByProcessInstanceIdAndActivityId(
    String processInstanceId, 
    String activityId
)
```

**Uso**: Operações específicas de uma atividade Camunda

## Operações de Limpeza

### findExpiredRecords
```java
@Query("SELECT ir FROM IdempotencyRecord ir WHERE ir.expiresAt < :now")
List<IdempotencyRecord> findExpiredRecords(@Param("now") LocalDateTime now)
```

### deleteExpiredRecords
```java
@Modifying
@Query("DELETE FROM IdempotencyRecord ir WHERE ir.expiresAt < :now")
int deleteExpiredRecords(@Param("now") LocalDateTime now)
```

**Uso**: Job agendado para limpeza de registros expirados

## Operações de Monitoramento

### findPendingOperations
```java
@Query("SELECT ir FROM IdempotencyRecord ir WHERE ir.status = 'PENDING' ORDER BY ir.createdAt DESC")
List<IdempotencyRecord> findPendingOperations()
```

**Uso**: Detectar operações travadas

### findFailedOperations
```java
@Query("SELECT ir FROM IdempotencyRecord ir WHERE ir.status = 'FAILED' ORDER BY ir.createdAt DESC")
List<IdempotencyRecord> findFailedOperations()
```

**Uso**: Análise de falhas e retry

### countByStatus
```java
long countByStatus(IdempotencyRecord.OperationStatus status)
```

**Status Enum**:
- `PENDING`: Operação em andamento
- `COMPLETED`: Operação concluída com sucesso
- `FAILED`: Operação falhou

## Queries Customizadas

### findRecentRecords
```java
@Query("SELECT ir FROM IdempotencyRecord ir WHERE ir.createdAt > :timestamp ORDER BY ir.createdAt DESC")
List<IdempotencyRecord> findRecentRecords(@Param("timestamp") LocalDateTime timestamp)
```

### findByOperationNameAndStatus
```java
List<IdempotencyRecord> findByOperationNameAndStatus(
    String operationName,
    IdempotencyRecord.OperationStatus status
)
```

### countByProcessInstanceId
```java
long countByProcessInstanceId(String processInstanceId)
```

## Modelo de Dados

### IdempotencyRecord Entity
```java
@Entity
class IdempotencyRecord {
    @Id
    private Long id;
    
    @Column(unique = true, nullable = false)
    private String idempotencyKey;
    
    private String processInstanceId;
    private String activityId;
    private String operationName;
    
    @Enumerated(EnumType.STRING)
    private OperationStatus status;
    
    @Column(columnDefinition = "TEXT")
    private String requestPayload;
    
    @Column(columnDefinition = "TEXT")
    private String responsePayload;
    
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    private LocalDateTime expiresAt;
    
    private String errorMessage;
}
```

## Índices

```sql
CREATE UNIQUE INDEX idx_idempotency_key ON idempotency_records(idempotency_key);
CREATE INDEX idx_process_instance ON idempotency_records(process_instance_id);
CREATE INDEX idx_process_activity ON idempotency_records(process_instance_id, activity_id);
CREATE INDEX idx_status ON idempotency_records(status);
CREATE INDEX idx_expires_at ON idempotency_records(expires_at);
CREATE INDEX idx_created_at ON idempotency_records(created_at);
```

## Fluxo de Uso

### 1. Verificação Pre-Operação
```java
Optional<IdempotencyRecord> existing = repository.findByIdempotencyKey(key);
if (existing.isPresent()) {
    if (existing.get().getStatus() == COMPLETED) {
        return existing.get().getResponsePayload(); // Return cached result
    }
    throw new DuplicateOperationException();
}
```

### 2. Registro de Operação
```java
IdempotencyRecord record = new IdempotencyRecord();
record.setIdempotencyKey(key);
record.setStatus(PENDING);
record.setRequestPayload(serializeRequest(request));
repository.save(record);
```

### 3. Atualização Pós-Operação
```java
record.setStatus(COMPLETED);
record.setResponsePayload(serializeResponse(response));
repository.save(record);
```

## Política de Retenção

### TTL (Time-To-Live)
- **Padrão**: 30 dias
- **Operações críticas**: 90 dias
- **Auditoria**: 365 dias

### Job de Limpeza
```java
@Scheduled(cron = "0 0 2 * * *") // 2 AM daily
public void cleanupExpiredRecords() {
    int deleted = repository.deleteExpiredRecords(LocalDateTime.now());
    logger.info("Deleted {} expired idempotency records", deleted);
}
```

## Conformidade

### LGPD/GDPR
- Dados sensíveis em payloads devem ser criptografados
- Right to erasure: limpeza de registros expirados
- Audit trail: preservação de logs de operações

### PCI-DSS
- Não armazenar dados de cartão em payloads
- Usar tokenização para referências de pagamento

## Referências
- ADR-007: Idempotency Pattern Implementation
- [Saga Compensation Pattern](../07_Architecture/saga-pattern.md)
- [Event Sourcing](../07_Architecture/event-sourcing.md)

## Histórico de Alterações
| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2025-12-23 | Revenue Cycle Team | Criação inicial baseada em ADR-007 |
