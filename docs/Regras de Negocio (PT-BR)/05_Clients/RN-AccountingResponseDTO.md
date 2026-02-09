# RN-AccountingResponseDTO - Resposta de Operações Contábeis

## Metadata
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/accounting/dto/AccountingResponseDTO.java`
- **Tipo**: Data Transfer Object (DTO)
- **Categoria**: 05_Clients - Accounting Integration
- **Camunda DMN**: N/A
- **Complexidade**: Baixa
- **Versão**: 1.0.0

## Descrição

### Objetivo
DTO de resposta para operações do cliente de contabilidade, utilizado para comunicar sucesso/falha de operações relacionadas ao sistema contábil.

### Tecnologia
- **Framework**: Lombok
- **Validação**: Sem validações declarativas

## Estrutura de Dados

### Atributos

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `success` | boolean | Sim | Indicador de sucesso da operação |
| `message` | String | Não | Mensagem descritiva do resultado |
| `provisionId` | String | Não | Identificador da provisão estornada |
| `amountReversed` | BigDecimal | Não | Valor que foi estornado |
| `timestamp` | String | Não | Timestamp da operação (formato ISO-8601) |

### Annotations Lombok
- `@Data`: Gera getters, setters, toString, equals, hashCode
- `@Builder`: Implementa padrão Builder
- `@NoArgsConstructor`: Construtor sem argumentos
- `@AllArgsConstructor`: Construtor com todos argumentos

## Regras de Negócio

### RN-ACRD-001: Indicação de Sucesso
- Campo `success` deve sempre ser preenchido
- `true`: Operação executada com sucesso
- `false`: Operação falhou

### RN-ACRD-002: Mensagem Descritiva
- Campo `message` fornece detalhes do resultado
- Exemplos:
  - "Provision reversed successfully"
  - "Provision not found"
  - "Invalid reversal amount"

### RN-ACRD-003: Identificação da Provisão
- `provisionId` identifica qual provisão foi afetada
- Utilizado para rastreabilidade e auditoria

### RN-ACRD-004: Valor Estornado
- `amountReversed` registra o valor monetário estornado
- Usado para reconciliação contábil

### RN-ACRD-005: Timestamp ISO-8601
- Formato recomendado: `"2026-01-12T14:30:00Z"`
- Facilita parsing em diferentes sistemas

## Relacionamentos

### Uso por Clientes
- **AccountingClient**: Poderia retornar este DTO (atualmente método void)
- **FinancialProvisionService**: Consumidor potencial das respostas

### Relacionado a Entidades
- **Provisão Financeira**: Referenciada via `provisionId`

## Exemplos de Uso

### Caso 1: Resposta de Estorno Bem-Sucedido
```java
AccountingResponseDTO response = AccountingResponseDTO.builder()
    .success(true)
    .message("Provision reversed successfully")
    .provisionId("PROV-12345")
    .amountReversed(new BigDecimal("1500.00"))
    .timestamp("2026-01-12T14:30:00Z")
    .build();
```

### Caso 2: Resposta de Falha
```java
AccountingResponseDTO response = AccountingResponseDTO.builder()
    .success(false)
    .message("Provision not found in accounting system")
    .provisionId("PROV-99999")
    .amountReversed(BigDecimal.ZERO)
    .timestamp("2026-01-12T14:35:00Z")
    .build();
```

### Caso 3: Processamento de Resposta
```java
public void processAccountingResponse(AccountingResponseDTO response) {
    if (response.isSuccess()) {
        log.info("Accounting reversal successful: {} - Amount: {}",
                 response.getProvisionId(),
                 response.getAmountReversed());
        updateProvisionStatus(response.getProvisionId(), "REVERSED");
    } else {
        log.error("Accounting reversal failed: {} - {}",
                  response.getProvisionId(),
                  response.getMessage());
        handleAccountingFailure(response);
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
public class AccountingResponseDTO {

    @NotNull
    private boolean success;

    @NotBlank(message = "Message is required")
    private String message;

    @Pattern(regexp = "PROV-\\d+", message = "Invalid provision ID format")
    private String provisionId;

    @DecimalMin(value = "0.0", inclusive = true)
    private BigDecimal amountReversed;

    @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ss'Z'")
    private String timestamp;
}
```

## Serialização JSON

### Exemplo JSON (Success)
```json
{
  "success": true,
  "message": "Provision reversed successfully",
  "provisionId": "PROV-12345",
  "amountReversed": 1500.00,
  "timestamp": "2026-01-12T14:30:00Z"
}
```

### Exemplo JSON (Failure)
```json
{
  "success": false,
  "message": "Insufficient balance in provision account",
  "provisionId": "PROV-12345",
  "amountReversed": 0.00,
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
void testAccountingResponseDTOBuilder() {
    AccountingResponseDTO response = AccountingResponseDTO.builder()
        .success(true)
        .message("Test message")
        .provisionId("PROV-001")
        .amountReversed(new BigDecimal("100.00"))
        .timestamp("2026-01-12T10:00:00Z")
        .build();

    assertThat(response.isSuccess()).isTrue();
    assertThat(response.getMessage()).isEqualTo("Test message");
    assertThat(response.getProvisionId()).isEqualTo("PROV-001");
    assertThat(response.getAmountReversed()).isEqualByComparingTo("100.00");
}
```

## Padrões de Design

### Design Patterns Aplicados
1. **Data Transfer Object (DTO)**: Transferência de dados entre camadas
2. **Builder Pattern**: Construção fluente de objetos
3. **Value Object**: Imutável após construção (conceitual)

## Observações
- **Uso Potencial**: DTO está definido mas não é atualmente retornado por `AccountingClient` (método void)
- **Evolução Futura**: Pode ser usado quando `AccountingClient.reverseProvisionEntry()` retornar resposta

## Melhorias Futuras
1. Adicionar validações declarativas (Bean Validation)
2. Usar `LocalDateTime` em vez de String para timestamp
3. Criar enum para tipos de mensagem
4. Implementar imutabilidade real (campos final)
5. Adicionar campo para código de erro estruturado

## Dependências
```xml
<dependency>
    <groupId>org.projectlombok</groupId>
    <artifactId>lombok</artifactId>
    <scope>provided</scope>
</dependency>
```

## Referências
- [Martin Fowler - DTO Pattern](https://martinfowler.com/eaaCatalog/dataTransferObject.html)
- [ISO 8601 Date Format](https://en.wikipedia.org/wiki/ISO_8601)

---
**Status**: ✅ Documentado
**Última Atualização**: 2026-01-12
**Próxima Revisão**: Sprint 7 (Integração e Testes End-to-End)
