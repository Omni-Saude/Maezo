# RN-WhatsAppConfig - Configuração Cliente Retrofit WhatsApp

## 1. Visão Geral

### 1.1 Objetivo
Classe de configuração Spring que inicializa e configura o cliente HTTP Retrofit para integração com WhatsApp Business API, incluindo timeouts, interceptors, converters e logging.

### 1.2 Contexto no Ciclo da Receita
- **Módulo**: Integration Layer - Configuration
- **Processo BPMN**: HTTP Client Configuration
- **Componente**: `com.hospital.revenuecycle.integration.whatsapp.WhatsAppClientConfig`
- **Tipo**: Spring Configuration (@Configuration)

### 1.3 Responsabilidades
- Configurar OkHttpClient com timeouts adequados
- Adicionar interceptors de logging
- Configurar conversores JSON (Jackson)
- Criar instância do WhatsAppClient Retrofit
- Gerenciar URL base da API

---

## 2. Regras de Negócio

### RN-WAC-001: URL Base da API
**Descrição**: A configuração deve usar a URL base correta do WhatsApp Business API (Graph API).

**Propriedade**:
```yaml
whatsapp:
  api:
    base-url: https://graph.facebook.com/v18.0/
```

**Implementação**:
```java
@Value("${whatsapp.api.base-url:https://graph.facebook.com/v18.0/}")
private String whatsappBaseUrl;
```

**Versões da API**:
- `v18.0` - Versão atual (recomendada)
- `v17.0` - Versão anterior
- `latest` - Sempre a versão mais recente (não recomendado para produção)

**Validação**:
```java
@PostConstruct
public void validateConfiguration() {
    if (!whatsappBaseUrl.startsWith("https://")) {
        throw new IllegalStateException(
            "WhatsApp API base URL must use HTTPS: " + whatsappBaseUrl
        );
    }

    if (!whatsappBaseUrl.endsWith("/")) {
        whatsappBaseUrl += "/";
    }

    log.info("WhatsApp API configured with base URL: {}", whatsappBaseUrl);
}
```

---

### RN-WAC-002: Timeouts de Conexão
**Descrição**: O cliente HTTP deve ter timeouts configurados para evitar travamentos em caso de lentidão da API.

**Configuração**:
```java
OkHttpClient okHttpClient = new OkHttpClient.Builder()
    .connectTimeout(10, TimeUnit.SECONDS)    // Timeout de conexão
    .readTimeout(30, TimeUnit.SECONDS)       // Timeout de leitura
    .writeTimeout(30, TimeUnit.SECONDS)      // Timeout de escrita
    .build();
```

**Justificativas**:

1. **Connect Timeout (10s)**:
   - Tempo para estabelecer conexão TCP
   - 10 segundos é adequado para APIs públicas
   - Previne travamento em caso de rede instável

2. **Read Timeout (30s)**:
   - Tempo máximo para ler resposta
   - WhatsApp API pode levar até 20s em picos de carga
   - 30s permite margem de segurança

3. **Write Timeout (30s)**:
   - Tempo máximo para enviar payload
   - Importante para mensagens com mídia
   - Previne timeout em uploads lentos

**Configuração Parametrizada**:
```yaml
whatsapp:
  client:
    connect-timeout: 10s
    read-timeout: 30s
    write-timeout: 30s
```

```java
@Value("${whatsapp.client.connect-timeout:10s}")
private Duration connectTimeout;

@Value("${whatsapp.client.read-timeout:30s}")
private Duration readTimeout;

@Value("${whatsapp.client.write-timeout:30s}")
private Duration writeTimeout;

OkHttpClient okHttpClient = new OkHttpClient.Builder()
    .connectTimeout(connectTimeout)
    .readTimeout(readTimeout)
    .writeTimeout(writeTimeout)
    .build();
```

---

### RN-WAC-003: Logging Interceptor
**Descrição**: O sistema deve registrar requisições e respostas HTTP para debugging e auditoria.

**Implementação**:
```java
HttpLoggingInterceptor loggingInterceptor = new HttpLoggingInterceptor();
loggingInterceptor.setLevel(HttpLoggingInterceptor.Level.BODY);
```

**Níveis de Logging**:

| Nível | Descrição | Uso |
|-------|-----------|-----|
| `NONE` | Sem logging | Produção (se houver outro sistema de log) |
| `BASIC` | Request method, URL, response code | Produção (padrão) |
| `HEADERS` | BASIC + headers | Debugging de autenticação |
| `BODY` | HEADERS + body | Desenvolvimento/Testes |

**Configuração por Ambiente**:
```yaml
# application-dev.yml
whatsapp:
  client:
    logging-level: BODY

# application-prod.yml
whatsapp:
  client:
    logging-level: BASIC
```

```java
@Value("${whatsapp.client.logging-level:BASIC}")
private String loggingLevel;

HttpLoggingInterceptor loggingInterceptor = new HttpLoggingInterceptor();
loggingInterceptor.setLevel(
    HttpLoggingInterceptor.Level.valueOf(loggingLevel)
);
```

**Redação de Dados Sensíveis**:
```java
HttpLoggingInterceptor loggingInterceptor = new HttpLoggingInterceptor(
    message -> {
        // Mascarar tokens de autenticação
        String sanitized = message.replaceAll(
            "Bearer [A-Za-z0-9\\-_]+",
            "Bearer ****"
        );
        // Mascarar números de telefone
        sanitized = sanitized.replaceAll(
            "\\+\\d{1,3}\\d{9,}",
            "+***********"
        );
        log.info(sanitized);
    }
);
```

---

### RN-WAC-004: Jackson Converter
**Descrição**: O sistema deve usar Jackson para serialização/deserialização JSON com ObjectMapper configurado.

**Implementação**:
```java
@Bean
public WhatsAppClient whatsAppClient(ObjectMapper objectMapper) {
    Retrofit retrofit = new Retrofit.Builder()
        .baseUrl(whatsappBaseUrl)
        .client(okHttpClient)
        .addConverterFactory(JacksonConverterFactory.create(objectMapper))
        .build();

    return retrofit.create(WhatsAppClient.class);
}
```

**ObjectMapper Configuration**:
```java
@Bean
public ObjectMapper objectMapper() {
    ObjectMapper mapper = new ObjectMapper();

    // Configurações de serialização
    mapper.configure(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS, false);
    mapper.configure(SerializationFeature.FAIL_ON_EMPTY_BEANS, false);

    // Configurações de deserialização
    mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    // Registrar módulos
    mapper.registerModule(new JavaTimeModule());

    // Estratégia de naming (snake_case para WhatsApp API)
    mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

    return mapper;
}
```

**Justificativa**:
- WhatsApp API usa snake_case (`messaging_product`, `phone_number_id`)
- Java usa camelCase (`messagingProduct`, `phoneNumberId`)
- Jackson faz conversão automática com estratégia de naming

---

### RN-WAC-005: Retry Policy
**Descrição**: O cliente deve implementar política de retry para falhas transitórias.

**Implementação**:
```java
@Bean
public OkHttpClient okHttpClient() {
    return new OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .addInterceptor(loggingInterceptor)
        .addInterceptor(retryInterceptor())
        .build();
}

private Interceptor retryInterceptor() {
    return chain -> {
        Request request = chain.request();
        Response response = null;
        IOException exception = null;

        int maxRetries = 3;
        int attempt = 0;

        while (attempt < maxRetries) {
            try {
                response = chain.proceed(request);

                // Retry em caso de 5xx ou 429 (Rate Limit)
                if (response.isSuccessful() ||
                    (response.code() != 429 && response.code() < 500)) {
                    return response;
                }

                response.close();

            } catch (IOException e) {
                exception = e;
            }

            attempt++;
            if (attempt < maxRetries) {
                // Backoff exponencial
                long delay = (long) Math.pow(2, attempt) * 1000;
                Thread.sleep(delay);
            }
        }

        if (exception != null) {
            throw exception;
        }

        return response;
    };
}
```

**Códigos para Retry**:
- `429 Too Many Requests` - Rate limit
- `500 Internal Server Error` - Erro transitório do servidor
- `502 Bad Gateway` - Gateway temporariamente indisponível
- `503 Service Unavailable` - Serviço temporariamente indisponível
- `504 Gateway Timeout` - Timeout no gateway

---

### RN-WAC-006: Connection Pool
**Descrição**: O cliente deve usar connection pooling para reutilização de conexões.

**Implementação**:
```java
@Bean
public OkHttpClient okHttpClient() {
    ConnectionPool connectionPool = new ConnectionPool(
        10,                        // Max idle connections
        5,                         // Keep alive duration
        TimeUnit.MINUTES           // Time unit
    );

    return new OkHttpClient.Builder()
        .connectionPool(connectionPool)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .addInterceptor(loggingInterceptor)
        .build();
}
```

**Benefícios**:
- Reduz latência (reutiliza conexões TCP)
- Diminui carga no servidor
- Melhora throughput
- Economiza recursos de rede

---

### RN-WAC-007: Authentication Interceptor
**Descrição**: Adicionar interceptor para injetar token de autenticação automaticamente.

**Implementação**:
```java
private Interceptor authenticationInterceptor() {
    return chain -> {
        Request originalRequest = chain.request();

        // Buscar token do serviço de configuração
        String accessToken = tokenService.getAccessToken();

        // Adicionar header de autorização
        Request authenticatedRequest = originalRequest.newBuilder()
            .header("Authorization", "Bearer " + accessToken)
            .build();

        return chain.proceed(authenticatedRequest);
    };
}

@Bean
public OkHttpClient okHttpClient() {
    return new OkHttpClient.Builder()
        // ... outras configurações ...
        .addInterceptor(authenticationInterceptor())
        .build();
}
```

**Token Service**:
```java
@Service
public class WhatsAppTokenService {

    @Value("${whatsapp.access-token}")
    private String accessToken;

    private Instant tokenExpiry;

    public String getAccessToken() {
        // Verificar se token está expirado
        if (tokenExpiry != null && Instant.now().isAfter(tokenExpiry)) {
            refreshAccessToken();
        }

        return accessToken;
    }

    private void refreshAccessToken() {
        // TODO: Implementar refresh de token
        // Tokens permanentes do WhatsApp têm validade de 60 dias
        log.warn("Access token may be expired. Please refresh manually.");
    }
}
```

---

## 3. Configuração Completa

### 3.1 Código Completo
```java
@Configuration
public class WhatsAppClientConfig {

    @Value("${whatsapp.api.base-url:https://graph.facebook.com/v18.0/}")
    private String whatsappBaseUrl;

    @Value("${whatsapp.client.connect-timeout:10s}")
    private Duration connectTimeout;

    @Value("${whatsapp.client.read-timeout:30s}")
    private Duration readTimeout;

    @Value("${whatsapp.client.write-timeout:30s}")
    private Duration writeTimeout;

    @Value("${whatsapp.client.logging-level:BASIC}")
    private String loggingLevel;

    @Autowired
    private WhatsAppTokenService tokenService;

    /**
     * Create WhatsApp Retrofit client.
     */
    @Bean
    public WhatsAppClient whatsAppClient(ObjectMapper objectMapper) {
        OkHttpClient okHttpClient = buildOkHttpClient();

        Retrofit retrofit = new Retrofit.Builder()
            .baseUrl(whatsappBaseUrl)
            .client(okHttpClient)
            .addConverterFactory(JacksonConverterFactory.create(objectMapper))
            .build();

        return retrofit.create(WhatsAppClient.class);
    }

    private OkHttpClient buildOkHttpClient() {
        HttpLoggingInterceptor loggingInterceptor = new HttpLoggingInterceptor();
        loggingInterceptor.setLevel(
            HttpLoggingInterceptor.Level.valueOf(loggingLevel)
        );

        ConnectionPool connectionPool = new ConnectionPool(
            10, 5, TimeUnit.MINUTES
        );

        return new OkHttpClient.Builder()
            .connectionPool(connectionPool)
            .connectTimeout(connectTimeout)
            .readTimeout(readTimeout)
            .writeTimeout(writeTimeout)
            .addInterceptor(loggingInterceptor)
            .addInterceptor(authenticationInterceptor())
            .addInterceptor(retryInterceptor())
            .build();
    }

    private Interceptor authenticationInterceptor() {
        return chain -> {
            Request originalRequest = chain.request();
            String accessToken = tokenService.getAccessToken();

            Request authenticatedRequest = originalRequest.newBuilder()
                .header("Authorization", "Bearer " + accessToken)
                .build();

            return chain.proceed(authenticatedRequest);
        };
    }

    private Interceptor retryInterceptor() {
        return chain -> {
            Request request = chain.request();
            Response response = null;
            IOException exception = null;

            int maxRetries = 3;
            for (int attempt = 0; attempt < maxRetries; attempt++) {
                try {
                    response = chain.proceed(request);

                    if (response.isSuccessful() ||
                        (response.code() != 429 && response.code() < 500)) {
                        return response;
                    }

                    response.close();

                } catch (IOException e) {
                    exception = e;
                }

                if (attempt < maxRetries - 1) {
                    long delay = (long) Math.pow(2, attempt + 1) * 1000;
                    Thread.sleep(delay);
                }
            }

            if (exception != null) {
                throw exception;
            }

            return response;
        };
    }

    @PostConstruct
    public void validateConfiguration() {
        if (!whatsappBaseUrl.startsWith("https://")) {
            throw new IllegalStateException(
                "WhatsApp API base URL must use HTTPS"
            );
        }

        if (!whatsappBaseUrl.endsWith("/")) {
            whatsappBaseUrl += "/";
        }

        log.info("WhatsApp HTTP client configured: baseUrl={}, " +
                "connectTimeout={}, readTimeout={}, writeTimeout={}",
            whatsappBaseUrl, connectTimeout, readTimeout, writeTimeout);
    }
}
```

### 3.2 application.yml
```yaml
whatsapp:
  api:
    base-url: https://graph.facebook.com/v18.0/
    phone-number-id: ${WHATSAPP_PHONE_NUMBER_ID}

  access-token: ${WHATSAPP_ACCESS_TOKEN}

  client:
    connect-timeout: 10s
    read-timeout: 30s
    write-timeout: 30s
    logging-level: BASIC

  # Pool de conexões
  connection-pool:
    max-idle-connections: 10
    keep-alive-duration: 5m

  # Retry policy
  retry:
    max-attempts: 3
    initial-delay: 1s
    multiplier: 2.0
    max-delay: 30s
```

---

## 4. Segurança

### 4.1 Proteção de Credenciais
```java
// ❌ NUNCA fazer isso
@Value("${whatsapp.access-token:EAAJxF5ZAZCfG8BAMBAA...}")
private String accessToken;

// ✅ CORRETO - usar variáveis de ambiente
@Value("${whatsapp.access-token}")
private String accessToken;
```

**Variáveis de Ambiente**:
```bash
export WHATSAPP_ACCESS_TOKEN="EAAJxF5ZAZCfG8BAMBAA..."
export WHATSAPP_PHONE_NUMBER_ID="123456789"
```

**Docker Secrets**:
```yaml
version: '3.8'
services:
  app:
    image: hospital/revenue-cycle
    secrets:
      - whatsapp_token

secrets:
  whatsapp_token:
    external: true
```

### 4.2 SSL/TLS Configuration
```java
private SSLContext createSSLContext() {
    try {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init((KeyStore) null);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(null, tmf.getTrustManagers(), null);

        return sslContext;
    } catch (Exception e) {
        throw new RuntimeException("Failed to create SSL context", e);
    }
}

@Bean
public OkHttpClient okHttpClient() {
    return new OkHttpClient.Builder()
        .sslSocketFactory(
            createSSLContext().getSocketFactory(),
            (X509TrustManager) TrustManagerFactory
                .getInstance(TrustManagerFactory.getDefaultAlgorithm())
                .getTrustManagers()[0]
        )
        // ... outras configurações ...
        .build();
}
```

---

## 5. Testes

### 5.1 Testes de Configuração
```java
@SpringBootTest
class WhatsAppClientConfigTest {

    @Autowired
    private WhatsAppClient whatsAppClient;

    @Test
    void whatsAppClient_ShouldBeConfigured() {
        assertNotNull(whatsAppClient);
    }

    @Test
    void okHttpClient_ShouldHaveCorrectTimeouts() {
        // Verificar via reflection ou propriedades expostas
        // ...
    }
}
```

### 5.2 Testes de Integração
```java
@SpringBootTest
class WhatsAppIntegrationTest {

    @Autowired
    private WhatsAppClient whatsAppClient;

    @Value("${whatsapp.phone-number-id}")
    private String phoneNumberId;

    @Value("${whatsapp.access-token}")
    private String accessToken;

    @Test
    void sendTemplateMessage_RealAPI_Success() {
        WhatsAppTemplateDTO template = buildTestTemplate();

        Call<WhatsAppResponse> call = whatsAppClient.sendTemplateMessage(
            phoneNumberId,
            "Bearer " + accessToken,
            template
        );

        Response<WhatsAppResponse> response = call.execute();
        assertTrue(response.isSuccessful());
        assertNotNull(response.body());
    }
}
```

---

## 6. Troubleshooting

### 6.1 Timeouts
**Problema**: Requisições estão dando timeout.

**Soluções**:
1. Aumentar timeouts:
```yaml
whatsapp:
  client:
    read-timeout: 60s
```

2. Verificar conectividade de rede
3. Verificar status da API do WhatsApp

### 6.2 SSL Errors
**Problema**: `SSLHandshakeException`.

**Soluções**:
1. Atualizar certificados Java:
```bash
keytool -import -trustcacerts -file certificate.crt -alias whatsapp
```

2. Verificar versão do Java (mínimo JDK 8)

### 6.3 Authentication Errors
**Problema**: 401 Unauthorized.

**Soluções**:
1. Verificar validade do token
2. Renovar access token
3. Verificar permissões da conta WhatsApp Business

---

## 7. Referências

- [Retrofit Documentation](https://square.github.io/retrofit/)
- [OkHttp Documentation](https://square.github.io/okhttp/)
- [Jackson Documentation](https://github.com/FasterXML/jackson)
- [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api)
