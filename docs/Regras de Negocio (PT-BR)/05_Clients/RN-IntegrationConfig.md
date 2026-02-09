# RN-IntegrationConfig: Central Integration Infrastructure Configuration

**ID:** RN-IntegrationConfig
**Category:** Integration Infrastructure
**Component:** `IntegrationConfig.java`
**Location:** `/src/main/java/com/hospital/revenuecycle/integration/config/IntegrationConfig.java`

---

## 1. Business Purpose

Provides centralized configuration infrastructure for all external system integrations, ensuring consistent REST communication patterns, JSON serialization standards, and Feign client coordination across the revenue cycle platform.

---

## 2. Technical Implementation

### Core Components

#### RestTemplate Configuration
```java
@Bean
public RestTemplate restTemplate(RestTemplateBuilder builder) {
    SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(5000);  // 5 seconds
    factory.setReadTimeout(10000);    // 10 seconds

    return builder
            .setConnectTimeout(Duration.ofSeconds(5))
            .setReadTimeout(Duration.ofSeconds(10))
            .requestFactory(() -> factory)
            .build();
}
```

**Purpose:**
- Standard HTTP client for REST API calls
- Consistent timeout policies across all integrations
- Used primarily by TISS submission client

**Configuration Parameters:**
- **Connect Timeout:** 5 seconds (connection establishment)
- **Read Timeout:** 10 seconds (response reading)
- **Factory:** SimpleClientHttpRequestFactory (thread-safe)

#### ObjectMapper Configuration
```java
@Bean
public ObjectMapper objectMapper() {
    ObjectMapper mapper = new ObjectMapper();
    mapper.registerModule(new JavaTimeModule());
    mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    mapper.enable(SerializationFeature.INDENT_OUTPUT);
    return mapper;
}
```

**Purpose:**
- Standard JSON serialization/deserialization
- Java 8 date/time support (LocalDate, LocalDateTime)
- Human-readable JSON output (pretty printing)

**Key Features:**
- **JavaTimeModule:** Support for java.time.* types
- **ISO-8601 Date Format:** Dates serialized as ISO strings
- **Pretty Printing:** Enabled for debugging (should disable in production)

---

## 3. Integration Patterns

### Feign Client Discovery
```java
@EnableFeignClients(basePackages = "com.hospital.revenuecycle.integration")
```

**Automatically discovers:**
- Insurance API client
- Collection agency client
- TASY client
- PACS client
- LIS client
- WhatsApp client
- Scheduling client

### RestTemplate Usage Pattern
```java
@Service
public class TissSubmissionClient {
    @Autowired
    private RestTemplate restTemplate;

    public ResponseEntity<String> submitClaim(TissRequest request) {
        return restTemplate.postForEntity(
            tissUrl + "/claims",
            request,
            String.class
        );
    }
}
```

---

## 4. Business Rules

### Timeout Policy
**Rule:** All integration HTTP calls must complete within defined timeout windows

**Implementation:**
- **Connect Timeout:** 5 seconds maximum for TCP connection establishment
- **Read Timeout:** 10 seconds maximum for response data reading
- **Total Maximum:** 15 seconds end-to-end for any integration call

**Rationale:**
- Prevents thread pool exhaustion from hung connections
- Ensures timely failure detection for circuit breakers
- Maintains system responsiveness under integration partner degradation

### JSON Serialization Standards
**Rule:** All integration payloads must use consistent JSON format

**Implementation:**
- ISO-8601 date/time format (e.g., "2025-01-12T10:30:00")
- Consistent field naming (camelCase via Jackson defaults)
- Pretty printing for development/debugging

**Rationale:**
- Ensures compatibility with external systems
- Facilitates debugging and log analysis
- Maintains audit trail readability

---

## 5. Dependencies & Integration Points

### Upstream Dependencies
```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
```

### Downstream Consumers
- **TISS Submission Client:** Uses RestTemplate for XML-based TISS protocol
- **Insurance API Client:** Uses Feign with custom ObjectMapper
- **Collection Agency Client:** Uses Feign with standard JSON
- **TASY Client:** Uses RestTemplate for proprietary EHR API
- **PACS/LIS Clients:** Use RestTemplate for DICOM/HL7 integration
- **WhatsApp Client:** Uses Feign for Business API

---

## 6. Coordination with Other Components

### Circuit Breaker Integration
```java
// CircuitBreakerCoordinator wraps RestTemplate calls
circuitBreaker.execute("tasy-api", () ->
    restTemplate.getForEntity(url, PatientResponse.class)
);
```

### Retry Handler Integration
```java
// RetryHandler wraps RestTemplate calls
retryHandler.execute("insurance-api", () ->
    restTemplate.postForEntity(url, request, Response.class)
);
```

### Cache Manager Integration
```java
// CacheManager caches RestTemplate responses
String cacheKey = "patient-" + patientId;
return cacheManager.get("tasy-patients", cacheKey, () ->
    restTemplate.getForEntity(url, Patient.class).getBody()
);
```

---

## 7. Configuration Best Practices

### Production Recommendations
```java
// Disable pretty printing in production
mapper.disable(SerializationFeature.INDENT_OUTPUT);

// Enable connection pooling
PoolingHttpClientConnectionManager connectionManager =
    new PoolingHttpClientConnectionManager();
connectionManager.setMaxTotal(100);
connectionManager.setDefaultMaxPerRoute(20);
```

### Security Considerations
- **HTTPS Only:** RestTemplate should enforce HTTPS for external calls
- **Authentication Headers:** Add via interceptors (not hardcoded)
- **Secret Management:** Never store API keys in configuration beans

### Performance Tuning
- **Connection Pooling:** Use Apache HttpClient for production
- **Timeout Tuning:** Adjust per integration partner SLA
- **Keep-Alive:** Enable HTTP persistent connections

---

## 8. Monitoring & Observability

### Key Metrics
- **RestTemplate Call Duration:** Track via Micrometer metrics
- **Timeout Exceptions:** Monitor for integration partner issues
- **JSON Serialization Errors:** Track ObjectMapper exceptions

### Logging Strategy
```java
@Slf4j
public class IntegrationConfig {
    @Bean
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder
            .interceptors((request, body, execution) -> {
                log.debug("REST call: {} {}", request.getMethod(), request.getURI());
                return execution.execute(request, body);
            })
            .build();
    }
}
```

---

## 9. Testing Strategy

### Unit Testing
```java
@Test
void restTemplate_shouldConfigureTimeouts() {
    RestTemplate restTemplate = config.restTemplate(builder);

    SimpleClientHttpRequestFactory factory =
        (SimpleClientHttpRequestFactory) restTemplate.getRequestFactory();

    assertThat(factory.getConnectTimeout()).isEqualTo(5000);
    assertThat(factory.getReadTimeout()).isEqualTo(10000);
}
```

### Integration Testing
```java
@Test
void objectMapper_shouldSerializeJavaTimeTypes() {
    ObjectMapper mapper = config.objectMapper();
    LocalDateTime now = LocalDateTime.now();

    String json = mapper.writeValueAsString(now);

    assertThat(json).matches("\"\\d{4}-\\d{2}-\\d{2}T.*\"");
}
```

---

## 10. Error Scenarios

| Scenario | Detection | Handling | Recovery |
|----------|-----------|----------|----------|
| Connection timeout | RestTemplate throws ResourceAccessException | Circuit breaker opens | Retry after backoff |
| Read timeout | RestTemplate throws ResourceAccessException | Circuit breaker opens | Retry with increased timeout |
| JSON serialization error | ObjectMapper throws JsonProcessingException | Log error, send to DLQ | Manual data correction |
| Feign client not found | Spring startup fails | Application context error | Fix package scan or add @FeignClient |

---

## 11. Compliance & Audit

### LGPD Compliance
- **Data Minimization:** RestTemplate should not log request bodies containing PII
- **Encryption:** All RestTemplate calls must use TLS 1.2+
- **Audit Trail:** Log all external integration calls with timestamps

### TISS Standards
- **RestTemplate Configuration:** Supports TISS XML over HTTP(S)
- **Timeout Alignment:** Meets TISS recommendation of <30s response
- **Error Codes:** Maps HTTP status to TISS error codes

---

## 12. Related Components

### Direct Dependencies
- `/src/main/java/com/hospital/revenuecycle/integration/tiss/TissSubmissionClient.java` - Uses RestTemplate
- `/src/main/java/com/hospital/revenuecycle/integration/insurance/InsuranceApiClient.java` - Uses Feign + ObjectMapper
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java` - Uses RestTemplate

### Resilience Infrastructure
- `RN-CircuitBreakerCoordinator.md` - Wraps RestTemplate calls for fault tolerance
- `RN-RetryHandler.md` - Adds retry logic to RestTemplate operations
- `RN-CacheManager.md` - Caches RestTemplate responses
- `RN-IntegrationDlqHandler.md` - Stores failed RestTemplate requests

---

## 13. Future Enhancements

### Planned Improvements
1. **WebClient Migration:** Migrate from RestTemplate to reactive WebClient
2. **HTTP/2 Support:** Enable HTTP/2 for improved performance
3. **Custom Serializers:** Add hospital-specific JSON serializers
4. **Request Correlation:** Add correlation IDs to all RestTemplate calls
5. **Dynamic Configuration:** Move timeouts to application.yml for runtime tuning

### Technical Debt
- Pretty printing enabled in production (impacts performance)
- SimpleClientHttpRequestFactory lacks connection pooling
- Missing request/response logging interceptors
- No distributed tracing integration (Sleuth/Zipkin)

---

**Version:** 1.0
**Last Updated:** 2025-01-12
**Status:** Production Active
