# RN-CollectionRequest - Requisição de Submissão para Cobrança

## Metadata
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/collection/dto/CollectionRequest.java`
- **Tipo**: Data Transfer Object (DTO)
- **Categoria**: 05_Clients - Collection Agency Integration
- **Camunda DMN**: N/A
- **Complexidade**: Baixa
- **Versão**: 1.0

## Descrição

### Objetivo
DTO de requisição para submeter conta inadimplente à agência de cobrança externa, contendo todos os dados necessários para criação de caso de cobrança.

### Tecnologia
- **Framework**: Lombok
- **Validação**: Sem validações declarativas (recomendado adicionar)
- **Serialização**: Jackson (JSON)

## Estrutura de Dados

### Atributos

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `accountNumber` | String | Sim | Número da conta hospitalar |
| `patientId` | String | Sim | Identificador único do paciente |
| `patientName` | String | Sim | Nome completo do paciente |
| `balanceOwed` | BigDecimal | Sim | Saldo devedor total |
| `lastPaymentDate` | LocalDate | Não | Data do último pagamento |
| `daysPastDue` | Integer | Sim | Dias de atraso |
| `contactPhone` | String | Sim | Telefone de contato |
| `contactEmail` | String | Não | Email de contato |

### Annotations Lombok
- `@Data`: Gera getters, setters, toString, equals, hashCode
- `@Builder`: Implementa padrão Builder
- `@NoArgsConstructor`: Construtor sem argumentos
- `@AllArgsConstructor`: Construtor com todos argumentos

## Regras de Negócio

### RN-CR-001: Identificação da Conta
- `accountNumber` deve ser único e existente no sistema
- Formato típico: "ACC-XXXXXX"

### RN-CR-002: Identificação do Paciente
- `patientId` deve referenciar paciente válido
- `patientName` deve corresponder ao nome no cadastro
- **PII**: Dados sensíveis (LGPD)

### RN-CR-003: Saldo Devedor
- `balanceOwed` deve ser maior que zero
- Valor típico para cobrança externa: > R$ 500,00
- Precisão de 2 casas decimais

### RN-CR-004: Dias de Atraso
- `daysPastDue` indica tempo desde vencimento original
- Threshold típico para cobrança externa: >= 90 dias

### RN-CR-005: Dados de Contato
- `contactPhone` obrigatório para tentativas de contato
- `contactEmail` opcional mas recomendado
- Validação de formato recomendada

## Validações Recomendadas

### Bean Validation (não implementado)
```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CollectionRequest {

    @NotBlank(message = "Account number is required")
    @Pattern(regexp = "ACC-\\d{6}", message = "Invalid account number format")
    private String accountNumber;

    @NotBlank(message = "Patient ID is required")
    private String patientId;

    @NotBlank(message = "Patient name is required")
    @Size(min = 2, max = 200)
    private String patientName;

    @NotNull(message = "Balance owed is required")
    @DecimalMin(value = "0.01", message = "Balance must be positive")
    private BigDecimal balanceOwed;

    @PastOrPresent(message = "Last payment date cannot be in future")
    private LocalDate lastPaymentDate;

    @NotNull(message = "Days past due is required")
    @Min(value = 1, message = "Days past due must be at least 1")
    private Integer daysPastDue;

    @NotBlank(message = "Contact phone is required")
    @Pattern(regexp = "\\d{10,11}", message = "Invalid phone format")
    private String contactPhone;

    @Email(message = "Invalid email format")
    private String contactEmail;
}
```

## Relacionamentos

### Utilizado Por
- **CollectionAgencyClient**: Envia este DTO via POST request
- **CollectionService**: Constrói DTO a partir de entidade Account

### Relacionado a Entidades
- **Account**: Fonte dos dados financeiros
- **Patient**: Fonte dos dados de contato

## Exemplos de Uso

### Caso 1: Criar Request de Submissão para Cobrança
```java
CollectionRequest request = CollectionRequest.builder()
    .accountNumber("ACC-123456")
    .patientId("PAT-789")
    .patientName("João da Silva")
    .balanceOwed(new BigDecimal("5000.00"))
    .lastPaymentDate(LocalDate.of(2025, 10, 15))
    .daysPastDue(90)
    .contactPhone("11987654321")
    .contactEmail("joao.silva@email.com")
    .build();

CollectionResponse response = collectionClient.submitToCollection(request);
```

### Caso 2: Construir a Partir de Entidade Account
```java
public CollectionRequest toCollectionRequest(Account account) {
    return CollectionRequest.builder()
        .accountNumber(account.getAccountNumber())
        .patientId(account.getPatient().getId())
        .patientName(account.getPatient().getFullName())
        .balanceOwed(account.getBalance())
        .lastPaymentDate(account.getLastPaymentDate())
        .daysPastDue(calculateDaysPastDue(account))
        .contactPhone(account.getPatient().getPhoneNumber())
        .contactEmail(account.getPatient().getEmail())
        .build();
}

private Integer calculateDaysPastDue(Account account) {
    return (int) ChronoUnit.DAYS.between(
        account.getOriginalDueDate(),
        LocalDate.now()
    );
}
```

### Caso 3: Validação Antes de Envio
```java
public void submitIfEligible(Account account) {
    if (!isEligibleForCollection(account)) {
        throw new IllegalStateException("Account not eligible for collection");
    }

    CollectionRequest request = toCollectionRequest(account);
    validateRequest(request);

    CollectionResponse response = collectionClient.submitToCollection(request);
    processResponse(account, response);
}

private void validateRequest(CollectionRequest request) {
    if (request.getBalanceOwed().compareTo(MIN_BALANCE) < 0) {
        throw new ValidationException("Balance too low for collection");
    }
    if (request.getDaysPastDue() < MIN_DAYS_PAST_DUE) {
        throw new ValidationException("Not enough days past due");
    }
}
```

## Serialização JSON

### Exemplo JSON
```json
{
  "accountNumber": "ACC-123456",
  "patientId": "PAT-789",
  "patientName": "João da Silva",
  "balanceOwed": 5000.00,
  "lastPaymentDate": "2025-10-15",
  "daysPastDue": 90,
  "contactPhone": "11987654321",
  "contactEmail": "joao.silva@email.com"
}
```

### Configuração Jackson (se necessário)
```java
@JsonFormat(pattern = "yyyy-MM-dd")
private LocalDate lastPaymentDate;

@JsonProperty("balance_owed")  // Snake case para API externa
private BigDecimal balanceOwed;
```

## Testes

### Cenários de Teste
1. **Builder completo**: Verifica criação com todos campos
2. **Campos obrigatórios**: Testa validação de campos required
3. **Valores inválidos**: Valida saldo negativo, dias inválidos
4. **Serialização JSON**: Verifica conversão para JSON
5. **Masking de PII**: Valida que dados sensíveis não vazam em logs

### Exemplo de Teste Unitário
```java
@Test
void testCollectionRequestBuilder() {
    CollectionRequest request = CollectionRequest.builder()
        .accountNumber("ACC-123456")
        .patientId("PAT-789")
        .patientName("João da Silva")
        .balanceOwed(new BigDecimal("5000.00"))
        .daysPastDue(90)
        .contactPhone("11987654321")
        .build();

    assertThat(request.getAccountNumber()).isEqualTo("ACC-123456");
    assertThat(request.getBalanceOwed()).isEqualByComparingTo("5000.00");
    assertThat(request.getDaysPastDue()).isEqualTo(90);
}
```

### Teste de Validação
```java
@Test
void testValidation_NegativeBalance_ThrowsException() {
    CollectionRequest request = CollectionRequest.builder()
        .balanceOwed(new BigDecimal("-100.00"))
        .build();

    Set<ConstraintViolation<CollectionRequest>> violations =
        validator.validate(request);

    assertThat(violations).isNotEmpty();
    assertThat(violations).anyMatch(v ->
        v.getMessage().contains("Balance must be positive"));
}
```

## Segurança e LGPD

### Dados Sensíveis (PII)
- `patientName`: Nome completo (PII)
- `contactPhone`: Telefone (PII)
- `contactEmail`: Email (PII)

### Proteção de Dados
```java
@Override
public String toString() {
    return "CollectionRequest{" +
           "accountNumber='" + accountNumber + '\'' +
           ", patientId='" + patientId + '\'' +
           ", patientName='***'" +  // Masked
           ", balanceOwed=" + balanceOwed +
           ", daysPastDue=" + daysPastDue +
           ", contactPhone='***'" +  // Masked
           ", contactEmail='***'" +   // Masked
           '}';
}
```

### Consentimento LGPD
- Paciente deve consentir com compartilhamento de dados para cobrança
- Registrar consentimento antes de submeter
- Permitir revogação de consentimento

## Padrões de Design

### Design Patterns Aplicados
1. **Data Transfer Object (DTO)**: Transferência de dados entre sistemas
2. **Builder Pattern**: Construção fluente e segura
3. **Value Object**: Imutável após construção (conceitual)

## Melhorias Futuras
1. Adicionar validações declarativas (Bean Validation)
2. Implementar masking automático de PII em logs
3. Adicionar campo para observações adicionais
4. Criar enum para tipos de conta
5. Adicionar histórico de tentativas de cobrança interna
6. Implementar criptografia para dados sensíveis em trânsito

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
<dependency>
    <groupId>javax.validation</groupId>
    <artifactId>validation-api</artifactId>
</dependency>
```

## Referências
- [Martin Fowler - DTO Pattern](https://martinfowler.com/eaaCatalog/dataTransferObject.html)
- [LGPD - Lei Geral de Proteção de Dados](https://www.gov.br/lgpd)
- [Bean Validation Specification](https://beanvalidation.org/)

---
**Status**: ✅ Documentado
**Última Atualização**: 2026-01-12
**Próxima Revisão**: Sprint 7 (Integração e Testes End-to-End)
