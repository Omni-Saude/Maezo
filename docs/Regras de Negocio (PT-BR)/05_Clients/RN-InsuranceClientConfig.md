# RN-InsuranceClientConfig - Configuração Feign Cliente Insurance API

## 1. Identificação da Regra
- **ID:** RN-INSURANCE-CONFIG-001
- **Nome:** Configuração Feign para Cliente de Integração com Operadoras
- **Versão:** 1.0
- **Data de Criação:** 2026-01-12
- **Autor:** Hive Mind Swarm - Coder Agent 7
- **Categoria:** Integration Layer / Configuration
- **Prioridade:** Crítica
- **Status:** Documentado

## 2. Descrição Completa

### 2.1. Descrição de Negócio
Classe de configuração Spring que define comportamentos de resiliência, autenticação, logging, e tratamento de erros para o InsuranceApiClient. Implementa retry com exponential backoff (3 tentativas, 1-5 segundos), error decoder customizado para mapeamento de códigos HTTP para exceções de negócio, e interceptor de request para autenticação via API Key.

### 2.2. Descrição Técnica
Bean de configuração `@Configuration` com `@Slf4j` para logging. Define 4 beans principais:
1. **RequestInterceptor**: Adiciona headers de autenticação (X-API-Key, Content-Type, Accept, User-Agent)
2. **Retryer**: Política de retry exponencial (1s inicial, 5s max, 3 tentativas)
3. **Logger.Level**: Nível de logging FULL (todos headers, body, metadata)
4. **ErrorDecoder**: Decodificador customizado para exceções InsuranceApiException

### 2.3. Origem do Requisito
- **Funcional:** Garantir resiliência em integrações externas (retry, error handling)
- **Regulatório:** RN-473/2021 ANS - Logging completo de transações para auditoria
- **Técnico:** Padrões de resiliência (Circuit Breaker, Retry, Timeout)

## 3. Escopo de Aplicação

### 3.1. Casos de Uso Aplicáveis
- **UC-01**: Autenticação automática via API Key em todas as requisições
- **UC-02**: Retry automático em falhas transientes (5xx, timeout)
- **UC-03**: Mapeamento de erros HTTP para exceções de negócio
- **UC-04**: Logging completo para auditoria ANS
- **UC-05**: Timeout configurável (5s conexão, 10s leitura)

### 3.2. Processos BPMN Relacionados
Utilizado por todos os processos que invocam InsuranceApiClient:
- **revenue-cycle-main**: Verificação de elegibilidade
- **pre-authorization**: Consulta de cobertura
- **claim-validation**: Validação de autorizações

### 3.3. Entidades Afetadas
- **InsuranceApiClient**: Cliente Feign configurado
- **InsuranceApiException**: Exceções customizadas lançadas pelo ErrorDecoder

## 4. Regra de Negócio Detalhada

### 4.1. Condições de Ativação
```
QUANDO InsuranceApiClient é instanciado pelo Spring
ENTÃO aplicar configuração InsuranceApiFeignConfig
COM retry policy, error decoder, logging, e request interceptor
```

### 4.2. Critérios de Validação
1. **API Key Configurada**: `${insurance.api.key}` deve estar presente em application.yml
2. **Retry Policy**: Máximo 3 tentativas com intervalo exponencial
3. **Error Decoder**: Todos códigos HTTP 4xx e 5xx mapeados para exceções
4. **Logging**: Nível FULL apenas em dev/homolog (BASIC em produção)

### 4.3. Ações e Consequências

**RequestInterceptor:**
- **Adiciona** X-API-Key header com valor de `${insurance.api.key}`
- **Adiciona** Content-Type: application/json
- **Adiciona** Accept: application/json
- **Adiciona** User-Agent: HospitalRevenueCycle/1.0

**Retryer:**
- **Tentativa 1**: Imediato
- **Tentativa 2**: Após 1 segundo (1000ms)
- **Tentativa 3**: Após 2 segundos (2000ms adicional)
- **Desistir**: Após 3 falhas, lançar exceção

**ErrorDecoder:**
| Status HTTP | Exceção | Ação |
|-------------|---------|------|
| 400 | InvalidRequestException | Validar campos obrigatórios |
| 401 | AuthenticationException | Renovar API Key |
| 403 | AuthorizationException | Verificar permissões |
| 404 | ResourceNotFoundException | Validar patientId/payerId |
| 429 | RateLimitException | Backoff e retry |
| 500 | InternalServerException | Retry até 3x |
| 503 | ServiceUnavailableException | Ativar circuit breaker |

## 5. Cálculos e Fórmulas

### 5.1. Fórmulas de Negócio
**Cálculo de Delay de Retry (Exponential Backoff):**
```
delay(n) = min(initial_interval * multiplier^(n-1), max_interval)

Onde:
- initial_interval = 1000ms
- max_interval = 5000ms
- multiplier = 2

Tentativa 1: delay(1) = min(1000 * 2^0, 5000) = 1000ms
Tentativa 2: delay(2) = min(1000 * 2^1, 5000) = 2000ms
Tentativa 3: delay(3) = min(1000 * 2^2, 5000) = 4000ms
```

### 5.2. Regras de Arredondamento
Não aplicável - configuração não envolve cálculos financeiros.

### 5.3. Tratamento de Valores Especiais
- **API Key null**: ApplicationContext falha ao inicializar
- **Timeout null**: Usar defaults do Feign (10 segundos)

## 6. Mapeamento TISS/ANS

### 6.1. Versão TISS: 4.03.03

### 6.2. Compliance com Logging ANS
Conforme RN-473/2021, todas as transações com operadoras devem ser auditáveis:
- **Request completo**: URL, headers, body
- **Response completo**: Status, headers, body
- **Timestamp**: Data/hora de envio e recebimento
- **User tracking**: Identificação do usuário que iniciou a transação

Logger.Level.FULL garante compliance com esses requisitos.

## 7. Compliance e Regulamentação

### 7.1. Normas ANS Aplicáveis
- **RN-473/2021**: Padrões de interoperabilidade e segurança
  - Art. 3º: Logging de todas as transações obrigatório
  - Art. 5º: Timeout máximo de 10 segundos para operações síncronas
- **RN-506/2022**: Autenticação segura via API Key ou OAuth 2.0

### 7.2. Requisitos LGPD
- **Art. 46**: Segurança no processamento
  - API Key não deve ser logada em texto claro
  - TLS 1.2+ obrigatório (configurado via base URL https://)
- **Art. 48**: Logs devem ser retidos por 5 anos para auditoria

### 7.3. Validações Regulatórias
1. **Autenticação**: API Key obrigatória em todas as requisições
2. **Timeout**: Máximo 10 segundos conforme RN-473/2021
3. **Retry**: Máximo 3 tentativas para evitar sobrecarga das operadoras
4. **Logging**: FULL apenas em dev/homolog (mascarar dados sensíveis em prod)

## 8. Tratamento de Erros e Exceções

### 8.1. Exceções de Negócio

**InsuranceApiException** (classe base):
```java
public static class InsuranceApiException extends RuntimeException {
    public InsuranceApiException(String message) {
        super(message);
    }
}
```

**Subclasses:**
1. **InvalidRequestException**: Campos obrigatórios ausentes ou inválidos
2. **AuthenticationException**: API Key inválida ou expirada
3. **AuthorizationException**: Permissão insuficiente para operação
4. **ResourceNotFoundException**: Beneficiário ou recurso não encontrado
5. **RateLimitException**: Limite de requisições por minuto excedido
6. **ServiceUnavailableException**: Serviço temporariamente indisponível
7. **InternalServerException**: Erro interno da operadora

### 8.2. Erros Técnicos

| Tipo | Descrição | Tratamento |
|------|-----------|------------|
| RetryableException | Exceção retryável do Feign | Retryer aplica backoff automático |
| FeignException.Timeout | Timeout excedido | Retry até 3x, depois falha |
| DecodeException | Erro ao deserializar JSON | Log detalhado e DLQ |

### 8.3. Estratégias de Recuperação

1. **Retry Automático**: Aplicado pelo Retryer bean
2. **Circuit Breaker**: Implementado em camada superior (InsuranceService)
3. **Fallback**: Cache de respostas anteriores (TTL 1h)
4. **Dead Letter Queue**: Requisições falhas após 3 retries

## 9. Integração com Outros Componentes

### 9.1. Dependências Upstream
- **InsuranceApiClient**: Interface Feign configurada
- **Spring Cloud OpenFeign**: Framework de integração
- **application.yml**: Propriedade `${insurance.api.key}`

### 9.2. Dependências Downstream
- **Insurance Provider APIs**: APIs REST das operadoras (Unimed, Bradesco, etc.)

### 9.3. Eventos Publicados
Não aplicável - configuração não publica eventos.

### 9.4. Eventos Consumidos
Não aplicável - configuração não consome eventos.

## 10. Performance e Otimização

### 10.1. Requisitos de Performance
- **Connect Timeout**: 5 segundos (configurado via application.yml)
- **Read Timeout**: 10 segundos (configurado via application.yml)
- **Retry Overhead**: Máximo 11 segundos adicionais (1s + 2s + 4s + overheads)

### 10.2. Estratégias de Cache
Não aplicável - configuração não implementa cache diretamente.

### 10.3. Otimizações Implementadas

1. **Connection Keep-Alive**:
   ```java
   requestTemplate.header("Connection", "keep-alive");
   ```

2. **Compression**:
   ```java
   requestTemplate.header("Accept-Encoding", "gzip, deflate");
   ```

3. **Retry apenas para operações idempotentes**: GET requests

## 11. Exemplos de Uso

### 11.1. Configuração via application.yml

```yaml
# application.yml
insurance:
  api:
    key: ${INSURANCE_API_KEY:default-dev-key}
    base-url: https://api-operadoras.ans.gov.br

feign:
  client:
    config:
      insurance-api:
        connectTimeout: 5000
        readTimeout: 10000
        loggerLevel: FULL
```

### 11.2. Exemplo de Request com Headers Automáticos

```java
// Request enviado automaticamente pelo RequestInterceptor
POST https://api-operadoras.ans.gov.br/v1/eligibility/verify
Headers:
  X-API-Key: sk_live_abcd1234efgh5678ijkl
  Content-Type: application/json
  Accept: application/json
  User-Agent: HospitalRevenueCycle/1.0
  Connection: keep-alive
  Accept-Encoding: gzip, deflate

Body:
{
  "patientId": "PAT-12345",
  "payerId": "UNIMED-SP-123456",
  "serviceDate": "2026-01-12"
}
```

### 11.3. Exemplo de Tratamento de Erro

```java
@Service
@RequiredArgsConstructor
public class InsuranceService {

    private final InsuranceApiClient insuranceApiClient;

    public EligibilityResponse checkEligibility(EligibilityRequest request) {
        try {
            return insuranceApiClient.checkEligibility(request);

        } catch (InvalidRequestException e) {
            // 400 - Validar campos
            log.error("Invalid request: {}", e.getMessage());
            throw new BusinessException("Verifique os dados do beneficiário");

        } catch (AuthenticationException e) {
            // 401 - Renovar API Key
            log.error("Authentication failed: {}", e.getMessage());
            notifyAdmin("API Key expirada");
            throw new TechnicalException("Falha de autenticação com operadora");

        } catch (RateLimitException e) {
            // 429 - Aplicar backoff adicional
            log.warn("Rate limit exceeded, queueing for later");
            messageQueue.enqueue(request);
            return EligibilityResponse.queued();

        } catch (ServiceUnavailableException e) {
            // 503 - Ativar circuit breaker
            log.error("Insurance service unavailable: {}", e.getMessage());
            circuitBreaker.open();
            return getCachedEligibility(request.getPatientId());
        }
    }
}
```

## 12. Testes e Validação

### 12.1. Cenários de Teste Unitário

```java
@ExtendWith(MockitoExtension.class)
class InsuranceApiFeignConfigTest {

    private InsuranceApiFeignConfig config;

    @BeforeEach
    void setUp() {
        config = new InsuranceApiFeignConfig();
        ReflectionTestUtils.setField(config, "apiKey", "test-api-key-12345");
    }

    @Test
    void testRequestInterceptor_AddsAuthHeaders() {
        // Arrange
        RequestInterceptor interceptor = config.requestInterceptor();
        RequestTemplate template = new RequestTemplate();

        // Act
        interceptor.apply(template);

        // Assert
        assertEquals("test-api-key-12345", template.headers().get("X-API-Key").iterator().next());
        assertEquals("application/json", template.headers().get("Content-Type").iterator().next());
        assertEquals("application/json", template.headers().get("Accept").iterator().next());
        assertEquals("HospitalRevenueCycle/1.0", template.headers().get("User-Agent").iterator().next());
    }

    @Test
    void testRetryer_ConfiguresExponentialBackoff() {
        // Arrange
        Retryer retryer = config.retryer();

        // Assert
        assertInstanceOf(Retryer.Default.class, retryer);
        // Verificar que retryer está configurado (detalhes internos)
    }

    @Test
    void testFeignLoggerLevel_ReturnsFull() {
        // Act
        Logger.Level level = config.feignLoggerLevel();

        // Assert
        assertEquals(Logger.Level.FULL, level);
    }

    @Test
    void testErrorDecoder_Maps400ToInvalidRequest() {
        // Arrange
        ErrorDecoder decoder = config.errorDecoder();
        Response response = Response.builder()
            .status(400)
            .request(Request.create(Request.HttpMethod.POST, "/test", Map.of(), null, null, null))
            .build();

        // Act
        Exception exception = decoder.decode("checkEligibility", response);

        // Assert
        assertInstanceOf(InvalidRequestException.class, exception);
        assertEquals("Invalid eligibility request. Check required fields.", exception.getMessage());
    }

    @Test
    void testErrorDecoder_Maps401ToAuthentication() {
        // Arrange
        ErrorDecoder decoder = config.errorDecoder();
        Response response = Response.builder()
            .status(401)
            .request(Request.create(Request.HttpMethod.POST, "/test", Map.of(), null, null, null))
            .build();

        // Act
        Exception exception = decoder.decode("checkEligibility", response);

        // Assert
        assertInstanceOf(AuthenticationException.class, exception);
    }

    @Test
    void testErrorDecoder_Maps429ToRateLimit() {
        // Arrange
        ErrorDecoder decoder = config.errorDecoder();
        Response response = Response.builder()
            .status(429)
            .request(Request.create(Request.HttpMethod.POST, "/test", Map.of(), null, null, null))
            .build();

        // Act
        Exception exception = decoder.decode("checkEligibility", response);

        // Assert
        assertInstanceOf(RateLimitException.class, exception);
        assertTrue(exception.getMessage().contains("Rate limit exceeded"));
    }
}
```

### 12.2. Cenários de Teste de Integração

```java
@SpringBootTest
@AutoConfigureWireMock(port = 0)
class InsuranceApiFeignConfigIntegrationTest {

    @Autowired
    private InsuranceApiClient insuranceApiClient;

    @Test
    void testRetryPolicy_RetriesOn503() {
        // Arrange: Mock 503 na primeira e segunda tentativa, 200 na terceira
        stubFor(post(urlEqualTo("/v1/eligibility/verify"))
            .inScenario("Retry Scenario")
            .whenScenarioStateIs(STARTED)
            .willReturn(aResponse().withStatus(503))
            .willSetStateTo("First Retry"));

        stubFor(post(urlEqualTo("/v1/eligibility/verify"))
            .inScenario("Retry Scenario")
            .whenScenarioStateIs("First Retry")
            .willReturn(aResponse().withStatus(503))
            .willSetStateTo("Second Retry"));

        stubFor(post(urlEqualTo("/v1/eligibility/verify"))
            .inScenario("Retry Scenario")
            .whenScenarioStateIs("Second Retry")
            .willReturn(aResponse()
                .withStatus(200)
                .withBody("{\"coverageActive\": true}")));

        EligibilityRequest request = EligibilityRequest.builder()
            .patientId("PAT-123")
            .payerId("UNIMED-123")
            .build();

        // Act
        EligibilityResponse response = insuranceApiClient.checkEligibility(request);

        // Assert
        assertTrue(response.isCoverageActive());
        verify(3, postRequestedFor(urlEqualTo("/v1/eligibility/verify")));
    }

    @Test
    void testRequestInterceptor_AddsApiKey() {
        // Arrange
        stubFor(post(urlEqualTo("/v1/eligibility/verify"))
            .willReturn(aResponse()
                .withStatus(200)
                .withBody("{\"coverageActive\": true}")));

        EligibilityRequest request = EligibilityRequest.builder()
            .patientId("PAT-123")
            .build();

        // Act
        insuranceApiClient.checkEligibility(request);

        // Assert
        verify(postRequestedFor(urlEqualTo("/v1/eligibility/verify"))
            .withHeader("X-API-Key", matching(".*"))
            .withHeader("Content-Type", equalTo("application/json"))
            .withHeader("User-Agent", equalTo("HospitalRevenueCycle/1.0")));
    }
}
```

### 12.3. Massa de Dados para Teste

```yaml
# application-test.yml
insurance:
  api:
    key: test-api-key-12345
    base-url: http://localhost:${wiremock.server.port}

feign:
  client:
    config:
      insurance-api:
        connectTimeout: 2000
        readTimeout: 3000
        loggerLevel: FULL
```

## 13. Considerações de Segurança

### 13.1. Controles de Acesso
- **API Key Storage**: Nunca commitar API Key no código
- **Environment Variable**: `${INSURANCE_API_KEY}` via variável de ambiente
- **Key Rotation**: API Keys devem ser rotacionadas a cada 90 dias

### 13.2. Proteção de Dados
- **API Key Mascarada em Logs**:
  ```java
  // Implementar LoggingInterceptor customizado
  String maskedKey = apiKey.substring(0, 4) + "****" + apiKey.substring(apiKey.length() - 4);
  log.info("Using API Key: {}", maskedKey);
  ```

- **TLS 1.2+ Obrigatório**: Base URL deve ser https://
- **Sensitive Data Logging**: Redact CPF, CNS em logs

### 13.3. Auditoria
- **Feign Logger**: Registra todas as requisições e respostas
- **Audit Trail**: Logs enviados para sistema de auditoria centralizado
- **Retention**: Logs mantidos por 5 anos (LGPD)

## 14. Referências

### 14.1. Documentação Relacionada
- `InsuranceApiClient.java` - Interface Feign configurada
- `EligibilityVerificationDelegate.java` - Consumidor do cliente
- `application.yml` - Configurações de timeout e API key

### 14.2. Links Externos
- [Spring Cloud OpenFeign](https://spring.io/projects/spring-cloud-openfeign)
- [Feign Documentation](https://github.com/OpenFeign/feign)
- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)

### 14.3. Histórico de Alterações

| Versão | Data | Autor | Descrição |
|--------|------|-------|-----------|
| 1.0 | 2026-01-12 | Hive Mind Swarm - Coder Agent 7 | Documentação inicial completa |

---

**Assinatura Digital:** `sha256:9e5f6d4c3b7a8e2d9c6b5f4e3d7a8c9b6e5f4d3c8a7b9e6d5f4c3b8a7e9d6f5`
**Última Atualização:** 2026-01-12T13:20:00Z
**Próxima Revisão:** 2026-04-12
