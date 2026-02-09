# RN-PACSClientConfig - Configuração do Cliente PACS

## Identificação
- **ID**: RN-PACSClientConfig
- **Nome**: PACS Client Configuration
- **Categoria**: Configuration/Integration
- **Subcategoria**: Security & Authentication
- **Camada**: Infrastructure Layer
- **Arquivo**: `src/main/java/com/hospital/revenuecycle/integration/pacs/PACSClientConfig.java`

---

## Descrição

Classe de configuração Spring que define interceptadores e comportamentos do cliente Feign para integração com o Sistema de Arquivamento e Comunicação de Imagens (PACS), incluindo autenticação, headers HTTP e configurações de timeout específicas para operações de imagem.

---

## Propósito e Objetivo

### Objetivo Principal
Centralizar configurações de segurança e comunicação HTTP para o cliente PACS, garantindo autenticação consistente, timeouts adequados para operações de imagem e padronização de headers FHIR em todas as requisições.

### Problema que Resolve
- **Autenticação centralizada**: Evita passar API key manualmente em cada chamada
- **Timeouts específicos**: Operações de imagem podem ser mais lentas que LIS
- **Headers FHIR padrão**: Garante compatibilidade com API FHIR do PACS
- **Segurança**: Gerencia credenciais de forma segura

---

## Componentes da Configuração

### 1. API Key Management

**Injeção de Propriedade**:
```java
@Value("${pacs.api-key}")
private String pacsApiKey;
```

**Configuração em application.yml**:
```yaml
pacs:
  base-url: https://pacs-api.hospital.com/fhir/R4
  api-key: ${PACS_API_KEY}  # Variável de ambiente
  timeout:
    connect: 10000  # 10s (maior que LIS devido a imagens)
    read: 60000     # 60s (maior que LIS)
```

---

### 2. Request Interceptor

**Bean Spring**: Registra interceptador global para todas as requisições PACS

**Implementação**:
```java
@Bean
public RequestInterceptor pacsRequestInterceptor() {
    return requestTemplate -> {
        // 1. Autenticação Bearer
        requestTemplate.header("Authorization", "Bearer " + pacsApiKey);

        // 2. Headers FHIR obrigatórios
        requestTemplate.header("Accept", "application/fhir+json");
        requestTemplate.header("Content-Type", "application/fhir+json");
    };
}
```

**Headers Configurados**:

| Header | Valor | Propósito |
|--------|-------|-----------|
| Authorization | Bearer {token} | Autenticação na API PACS |
| Accept | application/fhir+json | Cliente aceita JSON FHIR |
| Content-Type | application/fhir+json | Payloads em JSON FHIR |

---

## Diferenças de Configuração vs LIS

### Timeouts Maiores
**Motivo**: Operações de imagem envolvem transferência de dados maiores

```yaml
# LIS
lis:
  timeout:
    connect: 5000
    read: 30000

# PACS
pacs:
  timeout:
    connect: 10000  # 2x maior
    read: 60000     # 2x maior
```

### Connection Pooling Otimizado
```java
@Bean
public Client pacsClient() {
    return new ApacheHttpClient(HttpClients.custom()
        .setMaxConnTotal(100)        // Menor pool que LIS
        .setMaxConnPerRoute(20)       // Conexões por rota
        .setConnectionTimeToLive(10, TimeUnit.MINUTES)
        .build()
    );
}
```

---

## Regras de Negócio

### RN-PACSCONF-01: Timeout Diferenciado
**Descrição**: PACS deve ter timeouts maiores que LIS devido ao tamanho dos dados de imagem.

**Implementação**:
```yaml
feign:
  client:
    config:
      pacs-client:
        connectTimeout: 10000
        readTimeout: 60000
        # Para operações de download de imagem
        readTimeout: 120000
```

---

### RN-PACSCONF-02: Retry Policy para Imagens
**Descrição**: Falhas em transferência de imagens devem ter retry com backoff.

**Configuração**:
```java
@Bean
public Retryer pacsRetryer() {
    return new Retryer.Default(
        2000L,    // initial interval: 2s
        10000L,   // max interval: 10s
        3         // max attempts
    );
}
```

---

### RN-PACSCONF-03: Cache de Metadados
**Descrição**: Metadados de estudos (não as imagens) podem ser cacheados.

**Implementação**:
```java
@Configuration
@EnableCaching
public class PACSCacheConfig {

    @Bean
    public CacheManager pacesCacheManager() {
        return new ConcurrentMapCacheManager("pacs-studies", "pacs-series");
    }
}

@Service
public class PACSService {

    @Cacheable(value = "pacs-studies", key = "#studyId")
    public PACSStudyDTO getStudy(String studyId) {
        return pacsClient.getStudyById(studyId, apiKey);
    }
}
```

---

## Integração com DICOM

### DICOM Web (DICOMweb) Configuration
```yaml
pacs:
  dicomweb:
    wado-uri: https://pacs.hospital.com/wado
    wado-rs: https://pacs.hospital.com/wado-rs
    qido-rs: https://pacs.hospital.com/qido-rs
    stow-rs: https://pacs.hospital.com/stow-rs
```

**Serviços DICOMweb**:
- **WADO (Web Access to DICOM Objects)**: Recuperação de imagens
- **QIDO (Query based on ID for DICOM Objects)**: Queries DICOM
- **STOW (Store Over the Web)**: Armazenamento de imagens

---

## Segurança

### 1. TLS/SSL para Imagens Médicas
```java
@Bean
public Client securedPACSClient() throws Exception {
    // Truststore específico para PACS
    KeyStore trustStore = KeyStore.getInstance("JKS");
    trustStore.load(
        new FileInputStream("pacs-truststore.jks"),
        "pacs-password".toCharArray()
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

### 2. DICOM Audit Logging
```java
@Aspect
@Component
public class PACSAuditAspect {

    @AfterReturning(pointcut = "execution(* com.hospital.revenuecycle.integration.pacs.PACSClient.*(..))", returning = "result")
    public void logPACSAccess(JoinPoint joinPoint, Object result) {
        String method = joinPoint.getSignature().getName();
        Object[] args = joinPoint.getArgs();

        // Registrar acesso conforme DICOM Audit Trail
        auditService.logDICOMAccess(
            getCurrentUser(),
            method,
            args,
            LocalDateTime.now()
        );
    }
}
```

---

## Configurações Avançadas

### 1. Circuit Breaker Específico para PACS
```yaml
resilience4j:
  circuitbreaker:
    instances:
      pacsClient:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 30s  # Maior que LIS
        permittedNumberOfCallsInHalfOpenState: 3
```

---

### 2. Rate Limiting para Proteção do PACS
```java
@Configuration
public class PACSRateLimitConfig {

    @Bean
    public RateLimiter pacsRateLimiter() {
        RateLimiterConfig config = RateLimiterConfig.custom()
            .limitForPeriod(50)  // 50 requisições
            .limitRefreshPeriod(Duration.ofMinutes(1))  // por minuto
            .timeoutDuration(Duration.ofSeconds(5))
            .build();

        return RateLimiter.of("pacs-client", config);
    }
}
```

---

### 3. Logging de Performance
```java
@Bean
public Logger.Level pacsLoggerLevel() {
    // BASIC em produção (não loga payloads grandes)
    return Logger.Level.BASIC;
}

@Bean
public Logger pacsLogger() {
    return new Slf4jLogger() {
        @Override
        protected void log(String configKey, String format, Object... args) {
            // Adicionar métricas de performance
            if (format.contains("---> END HTTP")) {
                metricsService.recordPACSRequestDuration(configKey, getDuration());
            }
            super.log(configKey, format, args);
        }
    };
}
```

---

## Ambientes

### application-dev.yml (Desenvolvimento)
```yaml
pacs:
  base-url: https://pacs-sandbox.hospital.com/fhir/R4
  api-key: ${PACS_DEV_API_KEY}
  timeout:
    connect: 15000  # Maior em dev (VPN pode ser lenta)
    read: 90000

feign:
  client:
    config:
      pacs-client:
        loggerLevel: FULL  # Logs completos em dev
```

### application-prod.yml (Produção)
```yaml
pacs:
  base-url: https://pacs-api.hospital.com/fhir/R4
  api-key: ${PACS_API_KEY}  # Secret Manager
  timeout:
    connect: 10000
    read: 60000

feign:
  client:
    config:
      pacs-client:
        loggerLevel: BASIC  # Logs mínimos em prod

resilience4j:
  circuitbreaker:
    instances:
      pacsClient:
        enabled: true  # Circuit breaker ativo
```

---

## Troubleshooting

### Problema 1: Read Timeout
**Sintomas**:
```
java.net.SocketTimeoutException: Read timed out
```

**Causa**: PACS lento ou estudo com muitas imagens

**Solução**:
```yaml
pacs:
  timeout:
    read: 120000  # Aumentar para 2 minutos
```

---

### Problema 2: DICOM UID não encontrado
**Sintomas**:
```
404 Not Found - Study UID not found
```

**Causa**: Estudo ainda não arquivado no PACS

**Solução**:
```java
@Service
public class PACSPollingService {

    public PACSStudyDTO waitForStudyAvailability(String studyUID, Duration maxWait) {
        Instant deadline = Instant.now().plus(maxWait);

        while (Instant.now().isBefore(deadline)) {
            try {
                return pacsClient.getStudyById(studyUID, apiKey);
            } catch (FeignException.NotFound e) {
                log.info("Estudo {} ainda não disponível no PACS, aguardando...", studyUID);
                Thread.sleep(5000); // 5s
            }
        }

        throw new TimeoutException("Estudo não disponível após " + maxWait);
    }
}
```

---

## Métricas e Observabilidade

### Métricas Específicas PACS
```java
@Configuration
public class PACSMetricsConfig {

    @Bean
    public MeterRegistryCustomizer<MeterRegistry> pacsMetricsCustomizer() {
        return registry -> {
            registry.config().commonTags("service", "pacs-integration");

            // Métrica customizada: tempo de download de imagens
            registry.gauge("pacs.image.download.duration.seconds", downloadDurationGauge);
        };
    }
}
```

**Dashboards Grafana**:
```promql
# Latência p95 de queries PACS
histogram_quantile(0.95,
  rate(http_client_requests_duration_bucket{client="pacs-client"}[5m])
)

# Taxa de timeout
sum(rate(http_client_requests_total{client="pacs-client",status="504"}[5m]))
  / sum(rate(http_client_requests_total{client="pacs-client"}[5m]))
```

---

## Referências Técnicas

1. **Spring Cloud OpenFeign**: https://spring.io/projects/spring-cloud-openfeign
2. **DICOMweb Standards**: https://www.dicomstandard.org/dicomweb
3. **HL7 FHIR ImagingStudy**: http://hl7.org/fhir/R4/imagingstudy.html
4. **Resilience4j**: https://resilience4j.readme.io/

---

**Versão**: 1.0
**Última Atualização**: 2024-01-12
**Responsável**: Equipe de Integração - Revenue Cycle Management
