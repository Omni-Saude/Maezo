# RN-CollectionAgencyFeignConfig - Configuração Feign para Agência de Cobrança

## Metadata
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/collection/CollectionAgencyFeignConfig.java`
- **Tipo**: Configuration Class
- **Categoria**: 05_Clients - Collection Agency Integration
- **Camunda DMN**: N/A
- **Complexidade**: Baixa
- **Autor**: Revenue Cycle Development Team
- **Data Criação**: 2026-01-09
- **Versão**: 1.0

## Descrição

### Objetivo
Configuração customizada do Feign Client para integração com API de agência de cobrança, incluindo autenticação, retry policy, e logging.

### Tecnologia
- **Framework**: Spring Cloud OpenFeign
- **Logging**: SLF4J + Lombok
- **Configuration**: Spring @Configuration

## Regras de Negócio

### RN-CAFC-001: Autenticação via API Key
**Bean**: `collectionRequestInterceptor()`

**Comportamento**:
1. Adiciona header `X-API-Key` em todas requisições
2. API Key obtida de propriedade `collection.agency.api.key`
3. Adiciona header `Content-Type: application/json`

**Segurança**:
- API Key deve vir de environment variable
- Nunca hardcoded no código
- Protegida via Spring Boot property management

### RN-CAFC-002: Política de Retry
**Bean**: `collectionRetryer()`

**Parâmetros**:
- **Initial Delay**: 1000ms (1 segundo)
- **Max Delay**: 5000ms (5 segundos)
- **Max Attempts**: 3 tentativas

**Comportamento**:
- Retry automático em caso de falha temporária
- Backoff progressivo entre tentativas
- Após 3 falhas, propaga exceção

### RN-CAFC-003: Logging Level
**Bean**: `collectionFeignLoggerLevel()`

**Configuração**:
- **Level**: FULL
- **Logs**: Request headers, body, response headers, body
- **Uso**: Troubleshooting e auditoria

## Configurações

### application.yml
```yaml
collection:
  agency:
    api:
      key: ${COLLECTION_API_KEY}  # Environment variable
      base-url: https://api.collectionagency.com
      timeout:
        connect: 5000
        read: 10000
```

### Environment Variables
```bash
export COLLECTION_API_KEY="your-secret-api-key"
```

## Beans Configurados

### 1. RequestInterceptor
**Propósito**: Adiciona headers de autenticação e content type

```java
@Bean
public RequestInterceptor collectionRequestInterceptor() {
    return requestTemplate -> {
        requestTemplate.header("X-API-Key", apiKey);
        requestTemplate.header("Content-Type", "application/json");
    };
}
```

**Headers Adicionados**:
- `X-API-Key`: Chave de API para autenticação
- `Content-Type`: Tipo de conteúdo JSON

### 2. Retryer
**Propósito**: Define política de retry para falhas temporárias

```java
@Bean
public Retryer collectionRetryer() {
    return new Retryer.Default(1000L, TimeUnit.SECONDS.toMillis(5), 3);
}
```

**Parâmetros**:
- `period`: 1000ms - Delay inicial entre retries
- `maxPeriod`: 5000ms - Delay máximo entre retries
- `maxAttempts`: 3 - Número máximo de tentativas

### 3. Logger Level
**Propósito**: Configura nível de logging do Feign

```java
@Bean
public Logger.Level collectionFeignLoggerLevel() {
    return Logger.Level.FULL;
}
```

**Níveis Disponíveis**:
- `NONE`: Sem logs
- `BASIC`: Request method, URL, response status
- `HEADERS`: BASIC + request/response headers
- `FULL`: HEADERS + request/response body

## Relacionamentos

### Utilizado Por
- **CollectionAgencyClient**: Aplica esta configuração via annotation
  ```java
  @FeignClient(
      name = "collection-agency-api",
      url = "${collection.agency.api.base-url}",
      configuration = CollectionAgencyFeignConfig.class
  )
  ```

## Exemplos de Uso

### Caso 1: Configuração Aplicada Automaticamente
```java
@Autowired
private CollectionAgencyClient client;

// Headers de autenticação e retry são aplicados automaticamente
CollectionResponse response = client.submitToCollection(request);
```

### Caso 2: Logs Gerados (Level FULL)
```
2026-01-12 10:30:00 DEBUG [CollectionAgencyClient#submitToCollection]
---> POST https://api.collectionagency.com/v1/accounts/submit HTTP/1.1
---> X-API-Key: ********
---> Content-Type: application/json
---> {"accountNumber":"ACC-001","balanceOwed":5000.00,...}

<--- HTTP/1.1 200 OK (234ms)
<--- Content-Type: application/json
<--- {"collectionCaseId":"CASE-12345","status":"ACCEPTED",...}
```

### Caso 3: Retry em Ação
```
2026-01-12 10:30:00 WARN  [Retryer] Retrying request (attempt 1/3)
2026-01-12 10:30:01 WARN  [Retryer] Retrying request (attempt 2/3)
2026-01-12 10:30:06 ERROR [Retryer] Max attempts reached, propagating exception
```

## Padrões de Design

### Design Patterns Aplicados
1. **Interceptor Pattern**: RequestInterceptor adiciona cross-cutting concerns
2. **Strategy Pattern**: Retryer define estratégia de retry
3. **Configuration Object**: Centraliza configurações do Feign

### Boas Práticas
- Configuração externalizada (application.yml)
- API Key via environment variable
- Logging configurável por ambiente
- Retry para resiliência

## Testes

### Cenários de Teste
1. **Interceptor adiciona headers**: Verifica presença de X-API-Key
2. **Retry em caso de falha**: Valida 3 tentativas antes de falhar
3. **Logging captura request/response**: Verifica logs gerados

### Exemplo de Teste Unitário
```java
@Test
void testCollectionRequestInterceptor() {
    CollectionAgencyFeignConfig config = new CollectionAgencyFeignConfig();
    ReflectionTestUtils.setField(config, "apiKey", "test-api-key");

    RequestInterceptor interceptor = config.collectionRequestInterceptor();
    RequestTemplate template = new RequestTemplate();

    interceptor.apply(template);

    assertThat(template.headers()).containsEntry("X-API-Key",
                                                  List.of("test-api-key"));
    assertThat(template.headers()).containsEntry("Content-Type",
                                                  List.of("application/json"));
}
```

### Teste de Integração (Retry)
```java
@Test
void testRetryPolicy() throws Exception {
    // Simula 2 falhas seguidas de sucesso
    when(mockServer.submitToCollection(any()))
        .thenThrow(new FeignException.ServiceUnavailable("Unavailable",
                                                          request, null))
        .thenThrow(new FeignException.ServiceUnavailable("Unavailable",
                                                          request, null))
        .thenReturn(successResponse);

    CollectionResponse response = client.submitToCollection(request);

    assertThat(response).isNotNull();
    verify(mockServer, times(3)).submitToCollection(any());
}
```

## Segurança

### Proteção de API Key
```yaml
# application.yml
collection:
  agency:
    api:
      key: ${COLLECTION_API_KEY}  # ✅ Environment variable
      # key: "hardcoded-key"  ❌ NEVER DO THIS
```

### Logging Seguro
- **Produção**: Considerar usar `Logger.Level.BASIC` para evitar logs sensíveis
- **Masking**: Implementar masking de dados sensíveis nos logs

```java
@Bean
@Profile("prod")
public Logger.Level collectionFeignLoggerLevel() {
    return Logger.Level.BASIC;  // Menos detalhado em produção
}
```

## Observabilidade

### Métricas Potenciais (não implementadas)
- Número de retries por requisição
- Taxa de sucesso após retry
- Latência por tentativa

### Logging Best Practices
```java
@Bean
public Logger.Level feignLoggerLevel(@Value("${feign.logging.level:BASIC}")
                                      String level) {
    return Logger.Level.valueOf(level);
}
```

## Melhorias Futuras
1. Adicionar timeout customizado (connect, read)
2. Implementar circuit breaker (Resilience4j)
3. Adicionar métricas (Micrometer)
4. Implementar masking de dados sensíveis nos logs
5. Configurar retry apenas para erros específicos (5xx)
6. Adicionar compressão (gzip) para payloads grandes

## Configurações Avançadas

### Timeouts Customizados
```java
@Bean
public Request.Options collectionRequestOptions() {
    return new Request.Options(
        5000, TimeUnit.MILLISECONDS,  // connectTimeout
        10000, TimeUnit.MILLISECONDS, // readTimeout
        true  // followRedirects
    );
}
```

### Error Decoder Customizado
```java
@Bean
public ErrorDecoder collectionErrorDecoder() {
    return (methodKey, response) -> {
        if (response.status() == 401) {
            return new UnauthorizedException("Invalid API key");
        }
        return new FeignException.Default(methodKey, response);
    };
}
```

## Dependências
```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
<dependency>
    <groupId>org.projectlombok</groupId>
    <artifactId>lombok</artifactId>
    <scope>provided</scope>
</dependency>
```

## Referências
- [Spring Cloud OpenFeign Documentation](https://docs.spring.io/spring-cloud-openfeign/docs/current/reference/html/)
- [Feign Retry Documentation](https://github.com/OpenFeign/feign/blob/master/core/src/main/java/feign/Retryer.java)
- [12-Factor App - Config](https://12factor.net/config)

---
**Status**: ✅ Documentado
**Última Atualização**: 2026-01-12
**Próxima Revisão**: Sprint 7 (Integração e Testes End-to-End)
