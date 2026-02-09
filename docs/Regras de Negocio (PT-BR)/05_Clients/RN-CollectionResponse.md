# RN-CollectionResponse - Resposta de Submissão para Cobrança

## Metadata
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/collection/dto/CollectionResponse.java`
- **Tipo**: Data Transfer Object (DTO)
- **Categoria**: 05_Clients - Collection Agency Integration
- **Camunda DMN**: N/A
- **Complexidade**: Baixa
- **Versão**: 1.0

## Descrição

### Objetivo
DTO de resposta da agência de cobrança após submissão de conta, contendo identificador do caso criado, status de aceitação e informações de processamento.

### Tecnologia
- **Framework**: Lombok
- **Serialização**: Jackson (JSON)
- **Date/Time**: Java Time API (LocalDateTime)

## Estrutura de Dados

### Atributos

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `collectionCaseId` | String | Sim | ID único do caso de cobrança criado |
| `status` | String | Sim | Status do caso ("ACCEPTED", "REJECTED", etc.) |
| `submittedAt` | LocalDateTime | Sim | Timestamp de submissão |
| `message` | String | Não | Mensagem descritiva do resultado |
| `accepted` | boolean | Sim | Indicador se foi aceito pela agência |

### Annotations Lombok
- `@Data`: Gera getters, setters, toString, equals, hashCode
- `@Builder`: Implementa padrão Builder
- `@NoArgsConstructor`: Construtor sem argumentos
- `@AllArgsConstructor`: Construtor com todos argumentos

## Regras de Negócio

### RN-CRP-001: Identificação do Caso
- `collectionCaseId` é gerado pela agência de cobrança
- Deve ser armazenado para rastreamento futuro
- Formato típico: "CASE-XXXXXX" ou UUID

### RN-CRP-002: Status do Caso
**Valores Possíveis**:
- `ACCEPTED`: Conta aceita para cobrança
- `REJECTED`: Conta rejeitada (saldo baixo, dados incompletos)
- `PENDING_REVIEW`: Aguardando revisão manual
- `ON_HOLD`: Em espera por informações adicionais

### RN-CRP-003: Aceitação da Conta
- `accepted = true`: Caso criado com sucesso
  - Atualizar status da conta para "SENT_TO_COLLECTION"
  - Armazenar `collectionCaseId` para tracking
  - Iniciar acompanhamento de cobrança externa

- `accepted = false`: Conta rejeitada
  - Analisar `message` para razão da rejeição
  - Corrigir problemas e tentar novamente
  - Considerar cobrança interna alternativa

### RN-CRP-004: Timestamp de Submissão
- `submittedAt` registra momento exato da submissão
- Usado para SLA e auditoria
- Formato ISO-8601 (UTC recomendado)

### RN-CRP-005: Mensagem Descritiva
- `message` fornece detalhes adicionais
- Exemplos:
  - "Account accepted for collection"
  - "Rejected: Balance below minimum threshold"
  - "Pending: Missing contact information"

## Relacionamentos

### Retornado Por
- **CollectionAgencyClient**: Retorna este DTO após `submitToCollection()`

### Processado Por
- **CollectionService**: Processa resposta e atualiza Account
- **AccountStatusService**: Atualiza status da conta baseado em `accepted`

### Relacionado a Entidades
- **Account**: Status atualizado baseado nesta resposta
- **CollectionCase**: Nova entidade criada se `accepted = true`

## Exemplos de Uso

### Caso 1: Processar Resposta de Aceitação
```java
public void processCollectionResponse(Account account,
                                       CollectionResponse response) {
    if (response.isAccepted()) {
        log.info("Account {} accepted for collection. Case ID: {}",
                 account.getAccountNumber(),
                 response.getCollectionCaseId());

        account.setStatus(AccountStatus.SENT_TO_COLLECTION);
        account.setCollectionCaseId(response.getCollectionCaseId());
        account.setCollectionSubmittedAt(response.getSubmittedAt());
        accountRepository.save(account);

        createCollectionCase(account, response);
        notifyCollectionTeam(account, response);
    } else {
        log.warn("Account {} rejected by collection agency: {}",
                 account.getAccountNumber(),
                 response.getMessage());

        handleRejection(account, response);
    }
}
```

### Caso 2: Criar Entidade CollectionCase
```java
private void createCollectionCase(Account account,
                                    CollectionResponse response) {
    CollectionCase collectionCase = CollectionCase.builder()
        .caseId(response.getCollectionCaseId())
        .accountNumber(account.getAccountNumber())
        .status(response.getStatus())
        .submittedAt(response.getSubmittedAt())
        .balanceAtSubmission(account.getBalance())
        .agencyName("Primary Collection Agency")
        .build();

    collectionCaseRepository.save(collectionCase);
}
```

### Caso 3: Tratamento de Rejeição
```java
private void handleRejection(Account account, CollectionResponse response) {
    RejectionReason reason = parseRejectionMessage(response.getMessage());

    switch (reason) {
        case BALANCE_TOO_LOW:
            account.setStatus(AccountStatus.INTERNAL_COLLECTION);
            scheduleInternalFollowUp(account);
            break;

        case MISSING_CONTACT_INFO:
            account.setStatus(AccountStatus.PENDING_CONTACT_INFO);
            requestContactUpdate(account);
            break;

        case DUPLICATE_SUBMISSION:
            log.warn("Account already in collection: {}",
                     account.getAccountNumber());
            break;

        default:
            account.setStatus(AccountStatus.REVIEW_REQUIRED);
            createManualReviewTask(account, response);
    }

    accountRepository.save(account);
}
```

## Serialização JSON

### Exemplo JSON (Accepted)
```json
{
  "collectionCaseId": "CASE-789456",
  "status": "ACCEPTED",
  "submittedAt": "2026-01-12T14:30:00",
  "message": "Account accepted for collection",
  "accepted": true
}
```

### Exemplo JSON (Rejected)
```json
{
  "collectionCaseId": null,
  "status": "REJECTED",
  "submittedAt": "2026-01-12T14:35:00",
  "message": "Rejected: Balance below minimum threshold ($500.00)",
  "accepted": false
}
```

### Configuração Jackson
```java
@JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ss")
private LocalDateTime submittedAt;

@JsonProperty("case_id")  // Se API externa usa snake_case
private String collectionCaseId;
```

## Testes

### Cenários de Teste
1. **Resposta de aceitação**: Verifica processamento de caso aceito
2. **Resposta de rejeição**: Valida tratamento de rejeição
3. **Deserialização JSON**: Testa parsing do JSON da API
4. **Builder pattern**: Verifica construção correta do objeto

### Exemplo de Teste Unitário
```java
@Test
void testCollectionResponseAccepted() {
    CollectionResponse response = CollectionResponse.builder()
        .collectionCaseId("CASE-12345")
        .status("ACCEPTED")
        .submittedAt(LocalDateTime.now())
        .message("Account accepted")
        .accepted(true)
        .build();

    assertThat(response.isAccepted()).isTrue();
    assertThat(response.getCollectionCaseId()).isEqualTo("CASE-12345");
    assertThat(response.getStatus()).isEqualTo("ACCEPTED");
}
```

### Teste de Integração
```java
@Test
void testProcessCollectionResponse_Accepted() {
    Account account = createTestAccount();
    CollectionResponse response = createAcceptedResponse();

    collectionService.processCollectionResponse(account, response);

    Account updated = accountRepository.findById(account.getId()).orElseThrow();
    assertThat(updated.getStatus()).isEqualTo(AccountStatus.SENT_TO_COLLECTION);
    assertThat(updated.getCollectionCaseId()).isEqualTo(response.getCollectionCaseId());

    CollectionCase collectionCase =
        collectionCaseRepository.findByCaseId(response.getCollectionCaseId());
    assertThat(collectionCase).isNotNull();
}
```

## Padrões de Design

### Design Patterns Aplicados
1. **Data Transfer Object (DTO)**: Transferência de dados entre sistemas
2. **Builder Pattern**: Construção fluente de objetos
3. **Value Object**: Imutável após construção (conceitual)

## Enumerações Relacionadas (Recomendadas)

### CollectionStatus Enum
```java
public enum CollectionStatus {
    ACCEPTED("Account accepted for collection"),
    REJECTED("Account rejected"),
    PENDING_REVIEW("Awaiting manual review"),
    ON_HOLD("On hold - additional information required"),
    PROCESSING("Processing submission");

    private final String description;

    CollectionStatus(String description) {
        this.description = description;
    }

    public String getDescription() {
        return description;
    }
}
```

## Logging e Auditoria

### Eventos a Logar
```java
@Slf4j
public class CollectionResponseProcessor {

    public void process(CollectionResponse response) {
        log.info("Processing collection response: caseId={}, status={}, accepted={}",
                 response.getCollectionCaseId(),
                 response.getStatus(),
                 response.isAccepted());

        if (!response.isAccepted()) {
            log.warn("Collection submission rejected: {}",
                     response.getMessage());
        }

        auditService.log(AuditEvent.COLLECTION_RESPONSE_RECEIVED, response);
    }
}
```

## Melhorias Futuras
1. Usar enum para `status` em vez de String
2. Adicionar validações declarativas (Bean Validation)
3. Incluir campo para estimativa de recuperação
4. Adicionar lista de próximas ações recomendadas
5. Incluir dados de contato do agente responsável
6. Adicionar SLA esperado para primeiro contato

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
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
```

## Referências
- [Martin Fowler - DTO Pattern](https://martinfowler.com/eaaCatalog/dataTransferObject.html)
- [Jackson Date/Time Serialization](https://www.baeldung.com/jackson-serialize-dates)

---
**Status**: ✅ Documentado
**Última Atualização**: 2026-01-12
**Próxima Revisão**: Sprint 7 (Integração e Testes End-to-End)
