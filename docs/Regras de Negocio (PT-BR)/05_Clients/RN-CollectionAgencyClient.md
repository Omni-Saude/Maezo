# RN-CollectionAgencyClient - Cliente de Integração com Agência de Cobrança

## Metadata
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/collection/CollectionAgencyClient.java`
- **Tipo**: External Integration Client
- **Categoria**: 05_Clients - Collection Agency Integration
- **Camunda DMN**: N/A (Feign HTTP Client)
- **Complexidade**: Média
- **Autor**: Revenue Cycle Development Team
- **Data Criação**: 2026-01-09
- **Versão**: 1.0

## Descrição

### Objetivo
Cliente Feign para integração com API externa de agência de cobrança, responsável por submeter contas inadimplentes para cobrança terceirizada.

### Tecnologia
- **Framework**: Spring Cloud OpenFeign
- **Protocolo**: HTTP/REST
- **Base URL**: Configurável via `collection.agency.api.base-url`
- **Autenticação**: API Key via interceptor

## Regras de Negócio

### RN-CAC-001: Submissão de Conta para Cobrança
**Operação**: `POST /v1/accounts/submit`

**Entrada**: `CollectionRequest` (via body)
- Account number, patient details, balance owed, etc.

**Saída**: `CollectionResponse`
- Collection case ID, status, acceptance confirmation

**Comportamento**:
1. Envia requisição HTTP POST com dados da conta
2. API externa valida dados e cria caso de cobrança
3. Retorna identificador do caso e status de aceitação

**Critérios de Submissão**:
- Contas com saldo devedor > limite mínimo
- Dias de atraso > threshold configurado
- Tentativas de cobrança interna esgotadas

### RN-CAC-002: Configuração Customizada
- Utiliza `CollectionAgencyFeignConfig` para configurações específicas:
  - API Key authentication
  - Retry policy (3 tentativas)
  - Logging level (FULL)
  - Timeout customizado

## Relacionamentos

### Upstream (Chama este cliente)
- **CollectionService**: Submete contas inadimplentes
- **DelinquencyManagementService**: Escalona casos para cobrança externa
- **PaymentFollowUpService**: Inicia processo de cobrança terceirizada

### Downstream (Sistemas externos)
- **Collection Agency API**: API REST de agência de cobrança
  - Endpoint: `${collection.agency.api.base-url}/v1/accounts/submit`

### DTOs Relacionados
- **CollectionRequest**: DTO de requisição
- **CollectionResponse**: DTO de resposta

## Configurações

### application.yml
```yaml
collection:
  agency:
    api:
      base-url: https://api.collectionagency.com
      key: ${COLLECTION_API_KEY}
      timeout:
        connect: 5000
        read: 10000
```

### Feign Configuration (CollectionAgencyFeignConfig)
- **RequestInterceptor**: Adiciona API Key no header `X-API-Key`
- **Retryer**: Retry com delay inicial 1s, máximo 5s, 3 tentativas
- **Logger Level**: FULL (logs completos de request/response)

## Tratamento de Erros

### Cenários de Falha
1. **API indisponível**: FeignException com HTTP 503/504
2. **Dados inválidos**: HTTP 400 Bad Request
3. **Autenticação falhou**: HTTP 401 Unauthorized
4. **Conta rejeitada**: `accepted=false` no response
5. **Timeout**: ReadTimeoutException

### Estratégia de Recuperação
- **Retry Automático**: 3 tentativas com backoff exponencial
- **Circuit Breaker**: Recomendado configurar via Resilience4j
- **Fallback**: Marcar conta para revisão manual

## Padrões de Design

### Design Patterns Aplicados
1. **Remote Facade**: Abstrai complexidade da API remota
2. **Adapter Pattern**: Adapta interface externa para modelo interno
3. **Configuration Object**: Configuração externalizada via `CollectionAgencyFeignConfig`
4. **Interceptor Pattern**: Adiciona autenticação via RequestInterceptor

### Boas Práticas
- Interface declarativa (Feign client)
- Autenticação segura via environment variable
- Retry automático para resiliência
- Logging completo para troubleshooting

## Exemplos de Uso

### Caso 1: Submeter Conta Inadimplente para Cobrança
```java
@Autowired
private CollectionAgencyClient collectionClient;

public void submitToCollection(Account account) {
    CollectionRequest request = CollectionRequest.builder()
        .accountNumber(account.getAccountNumber())
        .patientId(account.getPatientId())
        .patientName(account.getPatientName())
        .balanceOwed(account.getBalanceOwed())
        .lastPaymentDate(account.getLastPaymentDate())
        .daysPastDue(account.getDaysPastDue())
        .contactPhone(account.getContactPhone())
        .contactEmail(account.getContactEmail())
        .build();

    try {
        CollectionResponse response = collectionClient.submitToCollection(request);

        if (response.isAccepted()) {
            log.info("Account submitted successfully. Case ID: {}",
                     response.getCollectionCaseId());
            updateAccountStatus(account, "SENT_TO_COLLECTION",
                                response.getCollectionCaseId());
        } else {
            log.warn("Collection agency rejected account: {}",
                     response.getMessage());
            handleRejection(account, response);
        }
    } catch (FeignException e) {
        log.error("Failed to submit account to collection: {}",
                  account.getAccountNumber(), e);
        throw new CollectionIntegrationException("Collection submission failed", e);
    }
}
```

### Caso 2: Validação Pré-Submissão
```java
public boolean isEligibleForCollection(Account account) {
    return account.getBalanceOwed().compareTo(MIN_COLLECTION_AMOUNT) >= 0
        && account.getDaysPastDue() >= MIN_DAYS_PAST_DUE
        && account.getInternalAttempts() >= MAX_INTERNAL_ATTEMPTS
        && account.getStatus() == AccountStatus.DELINQUENT;
}
```

## Testes

### Cenários de Teste
1. **Submissão bem-sucedida**: Verifica criação de caso de cobrança
2. **Conta rejeitada**: Valida tratamento de rejeição
3. **API indisponível**: Testa retry e fallback
4. **Autenticação inválida**: Verifica tratamento de HTTP 401
5. **Timeout de comunicação**: Testa comportamento em timeout

### Exemplo de Teste Unitário
```java
@Test
void testSubmitToCollection_Success() {
    CollectionRequest request = CollectionRequest.builder()
        .accountNumber("ACC-001")
        .patientId("PAT-001")
        .balanceOwed(new BigDecimal("5000.00"))
        .daysPastDue(90)
        .build();

    CollectionResponse mockResponse = CollectionResponse.builder()
        .collectionCaseId("CASE-12345")
        .status("ACCEPTED")
        .accepted(true)
        .build();

    when(collectionClient.submitToCollection(request))
        .thenReturn(mockResponse);

    CollectionResponse response = collectionClient.submitToCollection(request);

    assertThat(response.isAccepted()).isTrue();
    assertThat(response.getCollectionCaseId()).isEqualTo("CASE-12345");
}
```

## Integrações ANS/TISS
- **N/A**: Não lida diretamente com padrões TISS
- **Impacto**: Contas em cobrança devem ser rastreadas para compliance

## Fluxo BPMN/Camunda
- **Processo**: Gerenciamento de Inadimplência
- **Tarefa**: Service Task "Enviar para Cobrança Externa"
- **Decisão**: Gateway "Tentativas Internas Esgotadas?"
- **Execução**: Assíncrona recomendada

## Logs e Observabilidade

### Eventos Logados
- Submissão de contas para cobrança
- Respostas de aceitação/rejeição
- Falhas de comunicação
- Retry attempts

### Métricas
- Taxa de aceitação de submissões
- Latência de chamadas à API externa
- Taxa de erro por tipo (4xx, 5xx)
- Número de contas em cobrança por agência

## Segurança

### Autenticação
- **Método**: API Key via header `X-API-Key`
- **Configuração**: Environment variable `COLLECTION_API_KEY`
- **Interceptor**: `CollectionAgencyFeignConfig.collectionRequestInterceptor()`

### Proteção de Dados
- **HTTPS**: Obrigatório para produção
- **PII**: Dados sensíveis de pacientes (nome, telefone, email)
- **LGPD**: Consentimento para compartilhamento com terceiros

## Compliance e Auditoria
- **Rastreabilidade**: Log de todas submissões com case ID
- **Audit Trail**: Registro de mudanças de status da conta
- **LGPD**: Necessário consentimento explícito do paciente

## Melhorias Futuras
1. Implementar circuit breaker (Resilience4j)
2. Adicionar OAuth2 authentication
3. Criar webhook para status updates da agência
4. Implementar queue para submissões em lote
5. Adicionar métricas detalhadas (Micrometer)
6. Criar dashboard de acompanhamento de cobranças

## Dependências
```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
<dependency>
    <groupId>io.github.resilience4j</groupId>
    <artifactId>resilience4j-spring-boot2</artifactId>
</dependency>
```

## Referências
- Spring Cloud OpenFeign Documentation
- [Collection Agency API Specification](https://api.collectionagency.com/docs)
- [Best Practices for Debt Collection](https://www.cfpb.gov/)

---
**Status**: ✅ Documentado
**Última Atualização**: 2026-01-12
**Próxima Revisão**: Sprint 7 (Integração e Testes End-to-End)
