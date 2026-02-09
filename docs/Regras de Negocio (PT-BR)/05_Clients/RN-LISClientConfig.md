# RN-LISClientConfig - Configuração do Cliente LIS

## Identificação
- **ID**: RN-LISClientConfig
- **Nome**: LIS Client Configuration
- **Categoria**: Configuration/Integration
- **Subcategoria**: Security & Authentication
- **Camada**: Infrastructure Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/lis/LISClientConfig.java`

---

## Descrição

Classe de configuração Spring que define interceptadores e comportamentos do cliente Feign para integração com o Sistema de Informação Laboratorial (LIS), incluindo autenticação, headers HTTP e configurações de timeout.

---

## Propósito e Objetivo

### Objetivo Principal
Centralizar configurações de segurança e comunicação HTTP para o cliente LIS, garantindo autenticação consistente e padronização de headers em todas as requisições ao sistema laboratorial.

### Problema que Resolve
- **Autenticação repetitiva**: Evita passar API key manualmente em cada chamada
- **Inconsistência de headers**: Garante headers FHIR corretos em todas as requisições
- **Segurança**: Gerencia credenciais de forma segura via variáveis de ambiente
- **Manutenibilidade**: Centraliza configuração de integração em um único ponto

---

## Componentes da Configuração

### 1. API Key Management

**Injeção de Propriedade**:
```java
@Value("${lis.api-key}")
private String lisApiKey;
```

**Configuração em application.yml**:
```yaml
lis:
  base-url: https://lis-api.hospital.com/fhir/R4
  api-key: ${LIS_API_KEY}  # Variável de ambiente
  timeout:
    connect: 5000
    read: 30000
```

**Segurança**:
- API key NUNCA deve estar hardcoded no código
- Usar variável de ambiente: `export LIS_API_KEY=xxxxx`
- Em produção: usar secrets manager (AWS Secrets Manager, HashiCorp Vault)

---

### 2. Request Interceptor

#### Função: lisRequestInterceptor()

**Bean Spring**: Registra interceptador global para todas as requisições LIS

**Implementação**:
```java
@Bean
public RequestInterceptor lisRequestInterceptor() {
    return requestTemplate -> {
        // 1. Autenticação Bearer
        requestTemplate.header("Authorization", "Bearer " + lisApiKey);

        // 2. Headers FHIR obrigatórios
        requestTemplate.header("Accept", "application/fhir+json");
        requestTemplate.header("Content-Type", "application/fhir+json");
    };
}
```

**Headers Configurados**:

| Header | Valor | Propósito |
|--------|-------|-----------|
| Authorization | Bearer {token} | Autenticação na API LIS |
| Accept | application/fhir+json | Indica que cliente aceita JSON FHIR |
| Content-Type | application/fhir+json | Indica que payloads são JSON FHIR |

---

## Padrões FHIR Implementados

### Content Negotiation (FHIR R4)

**MIME Types Suportados**:
1. `application/fhir+json` (preferido)
2. `application/json+fhir` (alternativo)
3. `application/json` (genérico)

**Versionamento FHIR**:
```http
Accept: application/fhir+json; fhirVersion=4.0
```

### Charset e Encoding
```http
Content-Type: application/fhir+json; charset=UTF-8
```

---

## Regras de Negócio Implementadas

### RN-LISCONF-01: Segurança de Credenciais
**Descrição**: API keys nunca devem ser expostas em código ou logs.

**Implementação**:
```java
// ✅ CORRETO
@Value("${lis.api-key}")
private String lisApiKey;

// ❌ INCORRETO
private String lisApiKey = "sk-123456789";
```

**Proteção em Logs**:
```java
// Evitar log de headers sensíveis
logback.xml:
<logger name="feign" level="INFO">
    <filter class="ch.qos.logback.core.filter.EvaluatorFilter">
        <evaluator>
            <expression>message.contains("Authorization")</expression>
        </evaluator>
        <onMatch>DENY</onMatch>
    </filter>
</logger>
```

---

### RN-LISCONF-02: Retry Policy
**Descrição**: Requisições falhadas devem ser retentadas com backoff exponencial.

**Configuração Recomendada**:
```yaml
feign:
  client:
    config:
      lis-client:
        connectTimeout: 5000
        readTimeout: 30000
        loggerLevel: BASIC
        retryer:
          period: 1000
          maxPeriod: 5000
          maxAttempts: 3
```

**Implementação Customizada**:
```java
@Bean
public Retryer feignRetryer() {
    return new Retryer.Default(
        1000L,    // initial interval (ms)
        5000L,    // max interval (ms)
        3         // max attempts
    );
}
```

---

### RN-LISCONF-03: Error Decoder
**Descrição**: Erros HTTP devem ser convertidos em exceções específicas do domínio.

**Implementação**:
```java
@Bean
public ErrorDecoder lisErrorDecoder() {
    return (methodKey, response) -> {
        if (response.status() == 401) {
            return new LISAuthenticationException("API key inválida");
        }
        if (response.status() == 404) {
            return new ResourceNotFoundException("Recurso LIS não encontrado");
        }
        if (response.status() >= 500) {
            return new LISServerException("Erro no servidor LIS");
        }
        return new FeignException.Default(methodKey, response);
    };
}
```

---

## Configurações Avançadas

### 1. Connection Pooling

**Apache HTTP Client Configuration**:
```java
@Bean
public Client feignClient() {
    return new ApacheHttpClient(HttpClients.custom()
        .setMaxConnTotal(200)
        .setMaxConnPerRoute(50)
        .setConnectionTimeToLive(5, TimeUnit.MINUTES)
        .build()
    );
}
```

**Benefícios**:
- Reutilização de conexões TCP
- Redução de latência
- Melhor throughput

---

### 2. Circuit Breaker (Resilience4j)

**Configuração**:
```yaml
resilience4j:
  circuitbreaker:
    instances:
      lisClient:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
```

**Implementação**:
```java
@Component
public class LISClientWrapper {

    @Autowired
    private LISClient lisClient;

    @CircuitBreaker(name = "lisClient", fallbackMethod = "fallbackGetOrders")
    public List<LISOrderDTO> getOrders(String encounterId) {
        return lisClient.getOrdersByEncounter(encounterId, getApiKey());
    }

    private List<LISOrderDTO> fallbackGetOrders(String encounterId, Exception e) {
        log.error("LIS indisponível, usando cache", e);
        return getCachedOrders(encounterId);
    }
}
```

---

### 3. Logging e Monitoramento

**Feign Logger Configuration**:
```java
@Bean
public Logger.Level feignLoggerLevel() {
    return Logger.Level.BASIC; // NONE, BASIC, HEADERS, FULL
}
```

**Níveis de Log**:
- **NONE**: Sem logs (produção)
- **BASIC**: Request method, URL, response status, execution time
- **HEADERS**: BASIC + request/response headers
- **FULL**: HEADERS + bodies (CUIDADO: pode expor dados sensíveis)

**Logging Seguro**:
```java
@Bean
public Logger feignLogger() {
    return new Slf4jLogger() {
        @Override
        protected void logRequest(String configKey, Level logLevel, Request request) {
            // Remove Authorization header dos logs
            Request sanitized = Request.create(
                request.httpMethod(),
                request.url(),
                sanitizeHeaders(request.headers()),
                request.body(),
                request.charset(),
                request.requestTemplate()
            );
            super.logRequest(configKey, logLevel, sanitized);
        }

        private Map<String, Collection<String>> sanitizeHeaders(Map<String, Collection<String>> headers) {
            Map<String, Collection<String>> sanitized = new HashMap<>(headers);
            sanitized.remove("Authorization");
            return sanitized;
        }
    };
}
```

---

## Ambientes e Profiles

### application.yml (Base)
```yaml
lis:
  base-url: ${LIS_BASE_URL:https://lis-api.hospital.com/fhir/R4}
  api-key: ${LIS_API_KEY}
  timeout:
    connect: ${LIS_TIMEOUT_CONNECT:5000}
    read: ${LIS_TIMEOUT_READ:30000}
```

### application-dev.yml (Desenvolvimento)
```yaml
lis:
  base-url: https://lis-sandbox.hospital.com/fhir/R4
  api-key: ${LIS_DEV_API_KEY}

feign:
  client:
    config:
      lis-client:
        loggerLevel: FULL  # Logs detalhados em dev
```

### application-prod.yml (Produção)
```yaml
lis:
  base-url: https://lis-api.hospital.com/fhir/R4
  api-key: ${LIS_API_KEY}  # Secret Manager

feign:
  client:
    config:
      lis-client:
        loggerLevel: BASIC  # Logs mínimos em prod

resilience4j:
  circuitbreaker:
    instances:
      lisClient:
        enabled: true  # Circuit breaker ativo em prod
```

---

## Segurança e Compliance

### 1. Secrets Management

**AWS Secrets Manager Integration**:
```java
@Configuration
public class SecretsConfig {

    @Bean
    public String lisApiKey() {
        AWSSecretsManager client = AWSSecretsManagerClientBuilder.standard()
            .withRegion(Regions.US_EAST_1)
            .build();

        GetSecretValueRequest request = new GetSecretValueRequest()
            .withSecretId("prod/lis/api-key");

        GetSecretValueResult result = client.getSecretValue(request);
        return result.getSecretString();
    }
}
```

---

### 2. TLS/SSL Configuration

**Certificado do Servidor LIS**:
```java
@Bean
public Client feignClient() throws Exception {
    // Carregar truststore customizado
    KeyStore trustStore = KeyStore.getInstance(KeyStore.getDefaultType());
    trustStore.load(
        new FileInputStream("lis-truststore.jks"),
        "truststore-password".toCharArray()
    );

    SSLContext sslContext = SSLContexts.custom()
        .loadTrustMaterial(trustStore, null)
        .build();

    CloseableHttpClient httpClient = HttpClients.custom()
        .setSSLContext(sslContext)
        .build();

    return new ApacheHttpClient(httpClient);
}
```

---

### 3. API Key Rotation

**Suporte a Múltiplas Keys (Blue-Green Rotation)**:
```java
@Configuration
public class LISClientConfig {

    @Value("${lis.api-key}")
    private String primaryApiKey;

    @Value("${lis.api-key-backup:#{null}}")
    private String backupApiKey;

    @Bean
    public RequestInterceptor lisRequestInterceptor() {
        return requestTemplate -> {
            String apiKey = getCurrentApiKey();
            requestTemplate.header("Authorization", "Bearer " + apiKey);
            // ... outros headers
        };
    }

    private String getCurrentApiKey() {
        // Tenta primary, fallback para backup
        if (isKeyValid(primaryApiKey)) {
            return primaryApiKey;
        }
        if (backupApiKey != null && isKeyValid(backupApiKey)) {
            log.warn("Using backup API key for LIS");
            return backupApiKey;
        }
        throw new IllegalStateException("No valid API key for LIS");
    }

    private boolean isKeyValid(String key) {
        // Validação básica (não vazio, formato correto)
        return key != null && key.matches("^[A-Za-z0-9_-]+$");
    }
}
```

---

## Testes

### Teste de Configuração
```java
@SpringBootTest
@TestPropertySource(properties = {
    "lis.api-key=test-api-key-12345"
})
class LISClientConfigTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void shouldConfigureRequestInterceptor() {
        RequestInterceptor interceptor = context.getBean(RequestInterceptor.class);
        assertNotNull(interceptor);

        RequestTemplate template = new RequestTemplate();
        interceptor.apply(template);

        // Verificar headers configurados
        assertTrue(template.headers().containsKey("Authorization"));
        assertTrue(template.headers().containsKey("Accept"));
        assertEquals(
            "application/fhir+json",
            template.headers().get("Accept").iterator().next()
        );
    }

    @Test
    void shouldInjectApiKey() {
        // Verificar que API key foi injetada
        String apiKey = context.getEnvironment().getProperty("lis.api-key");
        assertEquals("test-api-key-12345", apiKey);
    }
}
```

### Teste de Integração com WireMock
```java
@SpringBootTest
@AutoConfigureWireMock(port = 0)
class LISClientIntegrationTest {

    @Autowired
    private LISClient lisClient;

    @Value("${wiremock.server.port}")
    private int wireMockPort;

    @Test
    void shouldAuthenticateWithBearerToken() {
        stubFor(get(urlPathEqualTo("/ServiceRequest"))
            .withHeader("Authorization", equalTo("Bearer test-key"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/fhir+json")
                .withBody("[]")));

        List<LISOrderDTO> orders = lisClient.getOrdersByEncounter(
            "enc-123",
            "Bearer test-key"
        );

        verify(getRequestedFor(urlPathEqualTo("/ServiceRequest"))
            .withHeader("Authorization", equalTo("Bearer test-key"))
            .withHeader("Accept", equalTo("application/fhir+json")));
    }
}
```

---

## Troubleshooting

### Problema 1: 401 Unauthorized

**Sintomas**:
```
feign.FeignException$Unauthorized: [401 Unauthorized] during [GET] to [https://lis-api.hospital.com/fhir/R4/ServiceRequest]
```

**Causas Comuns**:
1. API key inválida ou expirada
2. Formato incorreto do header Authorization
3. API key não configurada (variável de ambiente ausente)

**Solução**:
```bash
# Verificar variável de ambiente
echo $LIS_API_KEY

# Testar manualmente
curl -H "Authorization: Bearer $LIS_API_KEY" \
     -H "Accept: application/fhir+json" \
     https://lis-api.hospital.com/fhir/R4/ServiceRequest?encounter=test
```

---

### Problema 2: 406 Not Acceptable

**Sintomas**:
```
feign.FeignException$NotAcceptable: [406 Not Acceptable]
```

**Causa**: Header Accept incorreto ou ausente

**Solução**:
```java
// Verificar que interceptor está configurado corretamente
requestTemplate.header("Accept", "application/fhir+json");
```

---

### Problema 3: Connection Timeout

**Sintomas**:
```
java.net.SocketTimeoutException: connect timed out
```

**Solução**:
```yaml
feign:
  client:
    config:
      lis-client:
        connectTimeout: 10000  # Aumentar timeout
        readTimeout: 60000
```

---

## Métricas e Observabilidade

### Micrometer Metrics
```java
@Configuration
public class LISMetricsConfig {

    @Bean
    public MeterRegistryCustomizer<MeterRegistry> metricsCustomizer() {
        return registry -> registry.config()
            .commonTags("service", "lis-integration");
    }
}
```

**Métricas Automáticas (Spring Boot Actuator)**:
- `http.client.requests` - Contador de requisições
- `http.client.requests.duration` - Histogram de latências

**Dashboards Grafana**:
```promql
# Taxa de requisições LIS
rate(http_client_requests_total{uri=~"/ServiceRequest.*"}[5m])

# Latência p95
histogram_quantile(0.95,
  rate(http_client_requests_duration_bucket{client="lis-client"}[5m])
)

# Taxa de erro
sum(rate(http_client_requests_total{status=~"5.."}[5m]))
  / sum(rate(http_client_requests_total[5m]))
```

---

## Referências Técnicas

1. **Spring Cloud OpenFeign**: https://spring.io/projects/spring-cloud-openfeign
2. **Feign RequestInterceptor**: https://github.com/OpenFeign/feign/wiki/Request-Interceptors
3. **HL7 FHIR Content Types**: http://hl7.org/fhir/R4/http.html#mime-type
4. **Resilience4j Circuit Breaker**: https://resilience4j.readme.io/docs/circuitbreaker
5. **Spring Boot Externalized Configuration**: https://docs.spring.io/spring-boot/docs/current/reference/html/features.html#features.external-config

---

## Glossário

- **Feign Client**: Biblioteca HTTP declarativa para Spring
- **Request Interceptor**: Componente que intercepta requisições HTTP para adicionar headers, autenticação, etc.
- **Bearer Token**: Esquema de autenticação HTTP onde token é enviado no header Authorization
- **Circuit Breaker**: Padrão de resiliência que previne chamadas a sistemas indisponíveis
- **Content Negotiation**: Mecanismo HTTP para cliente e servidor acordarem formato de dados

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
