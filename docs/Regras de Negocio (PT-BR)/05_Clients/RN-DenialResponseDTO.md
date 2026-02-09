# RN-DenialResponseDTO - Resposta de Operações de Gerenciamento de Glosas

## Metadata
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/denial/dto/DenialResponseDTO.java`
- **Tipo**: Data Transfer Object (DTO)
- **Categoria**: 05_Clients - Denial Management Integration
- **Camunda DMN**: N/A
- **Complexidade**: Baixa
- **Versão**: 1.0.0

## Descrição

### Objetivo
DTO de resposta para operações do cliente de gerenciamento de glosas, utilizado para comunicar sucesso/falha de operações relacionadas a recursos e restauração de status de glosas (denials).

### Tecnologia
- **Framework**: Lombok
- **Validação**: Sem validações declarativas

## Estrutura de Dados

### Atributos

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `success` | boolean | Sim | Indicador de sucesso da operação |
| `message` | String | Não | Mensagem descritiva do resultado |
| `resourceId` | String | Não | ID do recurso afetado (appealId ou denialId) |
| `timestamp` | String | Não | Timestamp da operação (formato ISO-8601) |

### Annotations Lombok
- `@Data`: Gera getters, setters, toString, equals, hashCode
- `@Builder`: Implementa padrão Builder
- `@NoArgsConstructor`: Construtor sem argumentos
- `@AllArgsConstructor`: Construtor com todos argumentos

## Regras de Negócio

### RN-DRD-001: Indicação de Sucesso
- Campo `success` deve sempre ser preenchido
- `true`: Operação executada com sucesso
- `false`: Operação falhou

### RN-DRD-002: Mensagem Descritiva
- Campo `message` fornece detalhes do resultado
- **Exemplos de Sucesso**:
  - "Appeal cancelled successfully"
  - "Denial status restored to PENDING"

- **Exemplos de Falha**:
  - "Appeal not found"
  - "Invalid status for restoration"
  - "Denial already in target status"

### RN-DRD-003: Identificação do Recurso
- `resourceId` identifica qual recurso foi afetado
- Pode ser:
  - **appealId**: Para operações de cancelamento de recurso
  - **denialId**: Para operações de restauração de status
- Utilizado para rastreabilidade e auditoria

### RN-DRD-004: Timestamp ISO-8601
- Formato recomendado: `"2026-01-12T14:30:00Z"`
- Facilita parsing em diferentes sistemas
- Usado para auditoria e tracking de operações

## Relacionamentos

### Uso por Clientes
- **DenialManagementClient**: Poderia retornar este DTO (atualmente métodos void)
- **AppealOrchestrator**: Consumidor potencial das respostas
- **DenialCompensationService**: Processa respostas de compensação

### Relacionado a Entidades
- **Appeal**: Referenciado via `resourceId` (appealId)
- **Denial (Glosa)**: Referenciado via `resourceId` (denialId)

## Exemplos de Uso

### Caso 1: Resposta de Cancelamento de Recurso Bem-Sucedido
```java
DenialResponseDTO response = DenialResponseDTO.builder()
    .success(true)
    .message("Appeal cancelled successfully")
    .resourceId("APPEAL-12345")
    .timestamp("2026-01-12T14:30:00Z")
    .build();
```

### Caso 2: Resposta de Falha no Cancelamento
```java
DenialResponseDTO response = DenialResponseDTO.builder()
    .success(false)
    .message("Appeal not found in denial management system")
    .resourceId("APPEAL-99999")
    .timestamp("2026-01-12T14:35:00Z")
    .build();
```

### Caso 3: Resposta de Restauração de Status
```java
DenialResponseDTO response = DenialResponseDTO.builder()
    .success(true)
    .message("Denial status restored to PENDING")
    .resourceId("DENIAL-78901")
    .timestamp("2026-01-12T14:40:00Z")
    .build();
```

### Caso 4: Processamento de Resposta
```java
public void processDenialResponse(DenialResponseDTO response,
                                    OperationType operationType) {
    if (response.isSuccess()) {
        log.info("{} successful: {} - {}",
                 operationType,
                 response.getResourceId(),
                 response.getMessage());

        if (operationType == OperationType.CANCEL_APPEAL) {
            updateAppealStatus(response.getResourceId(),
                               AppealStatus.CANCELLED);
        } else if (operationType == OperationType.RESTORE_DENIAL) {
            logDenialRestoration(response.getResourceId(),
                                 response.getTimestamp());
        }
    } else {
        log.error("{} failed: {} - {}",
                  operationType,
                  response.getResourceId(),
                  response.getMessage());

        handleOperationFailure(response, operationType);
    }
}
```

## Validações

### Validações Recomendadas (não implementadas)
```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DenialResponseDTO {

    @NotNull
    private boolean success;

    @NotBlank(message = "Message is required")
    private String message;

    @Pattern(regexp = "(APPEAL|DENIAL)-\\d+",
             message = "Invalid resource ID format")
    private String resourceId;

    @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ss'Z'")
    private String timestamp;
}
```

## Serialização JSON

### Exemplo JSON (Success - Cancel Appeal)
```json
{
  "success": true,
  "message": "Appeal cancelled successfully",
  "resourceId": "APPEAL-12345",
  "timestamp": "2026-01-12T14:30:00Z"
}
```

### Exemplo JSON (Failure - Restore Denial)
```json
{
  "success": false,
  "message": "Invalid status for restoration: FINALIZED",
  "resourceId": "DENIAL-78901",
  "timestamp": "2026-01-12T14:35:00Z"
}
```

## Testes

### Cenários de Teste
1. **Builder completo**: Verifica criação com todos campos
2. **Builder parcial**: Testa criação com campos opcionais nulos
3. **Serialização JSON**: Valida conversão para/de JSON
4. **Igualdade**: Testa equals/hashCode

### Exemplo de Teste Unitário
```java
@Test
void testDenialResponseDTOBuilder_Success() {
    DenialResponseDTO response = DenialResponseDTO.builder()
        .success(true)
        .message("Appeal cancelled")
        .resourceId("APPEAL-001")
        .timestamp("2026-01-12T10:00:00Z")
        .build();

    assertThat(response.isSuccess()).isTrue();
    assertThat(response.getMessage()).isEqualTo("Appeal cancelled");
    assertThat(response.getResourceId()).isEqualTo("APPEAL-001");
}

@Test
void testDenialResponseDTOBuilder_Failure() {
    DenialResponseDTO response = DenialResponseDTO.builder()
        .success(false)
        .message("Resource not found")
        .resourceId("APPEAL-999")
        .timestamp("2026-01-12T10:05:00Z")
        .build();

    assertThat(response.isSuccess()).isFalse();
    assertThat(response.getMessage()).contains("not found");
}
```

## Padrões de Design

### Design Patterns Aplicados
1. **Data Transfer Object (DTO)**: Transferência de dados entre camadas
2. **Builder Pattern**: Construção fluente de objetos
3. **Value Object**: Imutável após construção (conceitual)

## Observações
- **Uso Potencial**: DTO está definido mas não é atualmente retornado por `DenialManagementClient` (métodos void)
- **Evolução Futura**: Deve ser usado quando os métodos do client retornarem resposta
- **Idempotência**: Response deve indicar se operação foi idempotente (ex: recurso já cancelado)

## Uso em Compensação Saga

### Exemplo de Compensação com Response
```java
public void compensateWithResponse(String appealId) {
    try {
        DenialResponseDTO response = denialClient.cancelAppealWithResponse(appealId);

        if (response.isSuccess()) {
            log.info("Compensation successful: {}", response.getMessage());
            sagaContext.markCompensated("APPEAL_CREATION");
        } else {
            if (response.getMessage().contains("not found")) {
                // Idempotente: considera sucesso se já foi cancelado
                log.warn("Resource not found (likely already cancelled): {}",
                         appealId);
                sagaContext.markCompensated("APPEAL_CREATION");
            } else {
                throw new CompensationFailedException(response.getMessage());
            }
        }
    } catch (Exception e) {
        log.error("Compensation failed: {}", e.getMessage());
        throw new CompensationFailedException("Failed to cancel appeal", e);
    }
}
```

## Melhorias Futuras
1. Adicionar validações declarativas (Bean Validation)
2. Usar `LocalDateTime` em vez de String para timestamp
3. Criar enum para tipos de operação
4. Adicionar campo para código de erro estruturado
5. Incluir campo para detalhes adicionais (Map<String, Object>)
6. Implementar imutabilidade real (campos final)
7. Adicionar indicador de idempotência

## Possível Enum para Tipos de Operação
```java
public enum DenialOperationType {
    CANCEL_APPEAL("Appeal Cancellation"),
    RESTORE_DENIAL("Denial Status Restoration"),
    UPDATE_APPEAL("Appeal Update"),
    CREATE_APPEAL("Appeal Creation");

    private final String description;

    DenialOperationType(String description) {
        this.description = description;
    }
}
```

## Dependências
```xml
<dependency>
    <groupId>org.projectlombok</groupId>
    <artifactId>lombok</artifactId>
    <scope>provided</scope>
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
```

## Referências
- [Martin Fowler - DTO Pattern](https://martinfowler.com/eaaCatalog/dataTransferObject.html)
- [ISO 8601 Date Format](https://en.wikipedia.org/wiki/ISO_8601)
- [Saga Pattern - Compensation](https://microservices.io/patterns/data/saga.html)

---
**Status**: ✅ Documentado
**Última Atualização**: 2026-01-12
**Próxima Revisão**: Sprint 7 (Integração e Testes End-to-End)
