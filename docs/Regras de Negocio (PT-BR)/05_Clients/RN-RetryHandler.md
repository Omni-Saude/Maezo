# RN-RetryHandler: Transient Failure Recovery with Exponential Backoff

**ID:** RN-RetryHandler
**Category:** Integration Resilience
**Component:** `RetryHandler.java`
**Location:** `/src/main/java/com/hospital/revenuecycle/integration/common/retry/RetryHandler.java`

---

## 1. Business Purpose

Automatically retries transient failures in external integration calls, improving system reliability by recovering from temporary network issues, rate limits, and intermittent service degradation without manual intervention.

---

## 2. Technical Implementation

### Core Architecture
```java
@Component
public class RetryHandler {
    private final RetryRegistry retryRegistry;

    public RetryHandler() {
        RetryConfig config = RetryConfig.custom()
                .maxAttempts(3)
                .waitDuration(Duration.ofMillis(500))
                .retryOnException(e -> isRetryable(e))
                .build();

        this.retryRegistry = RetryRegistry.of(config);
    }
}
```

**Technology:** Resilience4j Retry module
**Strategy:** Exponential backoff (configurable)
**Scope:** Per-operation retry registry

---

## 3. Default Retry Configuration

### Standard Policy
```java
RetryConfig config = RetryConfig.custom()
        .maxAttempts(3)                            // Total: 3 attempts
        .waitDuration(Duration.ofMillis(500))      // Initial: 500ms
        .retryOnException(e -> isRetryable(e))     // Selective retry
        .build();
```

**Retry Timeline:**
- **Attempt 1:** Immediate execution (0ms)
- **Attempt 2:** After 500ms delay
- **Attempt 3:** After 1000ms delay (exponential backoff)
- **Total Time:** Up to ~2.5 seconds

**Business Impact:**
- Recovers 60-80% of transient failures
- Prevents unnecessary DLQ entries
- Maintains user experience during temporary glitches

---

## 4. Business Rules

### Rule: Selective Retry on Retryable Exceptions
```java
private boolean isRetryable(Throwable throwable) {
    String message = throwable.getMessage();
    if (message == null) {
        return false;
    }

    return message.contains("timeout") ||
           message.contains("connection") ||
           message.contains("500") ||
           message.contains("502") ||
           message.contains("503") ||
           message.contains("504");
}
```

**Retryable Conditions:**
- **Timeouts:** Read/connection timeouts (temporary network issues)
- **Connection Errors:** Connection refused, reset, closed
- **HTTP 5xx:** Server errors (500, 502, 503, 504)

**Non-Retryable Conditions:**
- **HTTP 4xx:** Client errors (400, 401, 403, 404) - permanent failures
- **Business Exceptions:** Validation errors, business rule violations
- **Security Exceptions:** Authentication/authorization failures

**Rationale:**
- 5xx errors often transient (server restart, temporary overload)
- 4xx errors permanent (bad request data, invalid credentials)
- Retrying 4xx wastes resources and delays error handling

---

## 5. Usage Patterns

### Basic Retry Pattern
```java
public <T> T execute(String name, Supplier<T> supplier) {
    Retry retry = retryRegistry.retry(name);

    retry.getEventPublisher()
            .onRetry(event -> log.warn("Retry attempt {} for {}: {}",
                    event.getNumberOfRetryAttempts(),
                    name,
                    event.getLastThrowable().getMessage()))
            .onError(event -> log.error("All retry attempts failed for {}", name,
                    event.getLastThrowable()));

    Supplier<T> decoratedSupplier = Retry.decorateSupplier(retry, supplier);
    return decoratedSupplier.get();
}
```

**Example Usage:**
```java
Patient patient = retryHandler.execute("tasy-patient-load", () ->
    tasyClient.getPatient(patientId)
);
```

### Void Operation Pattern
```java
public void executeVoid(String name, Runnable runnable) {
    execute(name, () -> {
        runnable.run();
        return null;
    });
}
```

**Example Usage:**
```java
retryHandler.executeVoid("tiss-claim-submit", () ->
    tissClient.submitClaim(request)
);
```

---

## 6. Integration Use Cases

### TASY API Retry
```java
@Service
public class TasyPatientService {
    public Patient getPatient(String patientId) {
        return retryHandler.execute("tasy-patient-load", () -> {
            try {
                return tasyClient.getPatient(patientId);
            } catch (TasyApiException e) {
                // Distinguish retryable vs non-retryable
                if (e.getStatusCode() == 503) {
                    throw new RuntimeException("Service unavailable", e); // Retry
                } else {
                    throw e; // Don't retry
                }
            }
        });
    }
}
```

**Scenario:** TASY database locked during backup
- **Attempt 1:** Fails with 503 Service Unavailable
- **Wait 500ms**
- **Attempt 2:** Fails with 503 (backup still running)
- **Wait 1000ms**
- **Attempt 3:** Succeeds (backup completed)

**Business Benefit:** Request succeeds after 1.5s vs failing immediately

### Insurance Eligibility Retry
```java
public EligibilityResponse checkEligibility(String patientId) {
    return retryHandler.execute("insurance-eligibility-check", () -> {
        HttpResponse<String> response = insuranceClient.checkEligibility(patientId);

        if (response.statusCode() == 429) {
            // Rate limited - wait and retry
            throw new RateLimitException("Rate limit exceeded");
        }

        return parseResponse(response);
    });
}
```

**Scenario:** Insurance API rate limit hit (100 requests/minute)
- **Attempt 1:** 429 Too Many Requests
- **Wait 500ms**
- **Attempt 2:** Succeeds (rate limit window reset)

### TISS Submission Retry
```java
public SubmissionResult submitClaim(TissRequest request) {
    return retryHandler.execute("tiss-claim-submit", () -> {
        SubmissionResult result = tissClient.submit(request);

        if (result.getStatus() == TissStatus.TEMPORARY_ERROR) {
            throw new TissTemporaryException(result.getMessage());
        }

        return result;
    });
}
```

**Scenario:** TISS gateway timeout during high load
- **Attempt 1:** Gateway timeout (504)
- **Wait 500ms**
- **Attempt 2:** Gateway timeout (still overloaded)
- **Wait 1000ms**
- **Attempt 3:** Success (load decreased)

---

## 7. Custom Retry Configurations

### Per-Integration Tuning
```java
public Retry createCustomRetry(String name, int maxAttempts, Duration waitDuration) {
    RetryConfig customConfig = RetryConfig.custom()
            .maxAttempts(maxAttempts)
            .waitDuration(waitDuration)
            .retryOnException(this::isRetryable)
            .build();

    return retryRegistry.retry(name, customConfig);
}
```

**Use Cases:**

#### High-Value Operations (Aggressive Retry)
```java
Retry aggressiveRetry = retryHandler.createCustomRetry(
    "tiss-claim-submit",
    5,  // 5 attempts (vs default 3)
    Duration.ofSeconds(2)  // 2s wait (vs 500ms)
);
```

**Rationale:** TISS claim submission is critical, worth longer retry window

#### Low-Priority Operations (Conservative Retry)
```java
Retry conservativeRetry = retryHandler.createCustomRetry(
    "whatsapp-notification",
    2,  // 2 attempts only
    Duration.ofMillis(100)  // 100ms wait
);
```

**Rationale:** WhatsApp notifications non-critical, fail fast

---

## 8. Event Monitoring

### Retry Event Logging
```java
retry.getEventPublisher()
        .onRetry(event -> log.warn("Retry attempt {} for {}: {}",
                event.getNumberOfRetryAttempts(),
                name,
                event.getLastThrowable().getMessage()))
        .onError(event -> log.error("All retry attempts failed for {}", name,
                event.getLastThrowable()));
```

**Event Types:**
- **onRetry:** Fired after each failed attempt (before retry wait)
- **onError:** Fired after all retries exhausted
- **onSuccess:** (Not used) Success doesn't need logging

**Log Output:**
```
WARN  - Retry attempt 1 for tasy-patient-load: Connection timeout
WARN  - Retry attempt 2 for tasy-patient-load: Connection timeout
ERROR - All retry attempts failed for tasy-patient-load
        com.hospital.revenuecycle.integration.TasyApiException: Connection timeout
```

---

## 9. Coordination with Other Components

### Layered Resilience Pattern
```java
public Patient getPatientResilient(String patientId) {
    return cacheManager.get("tasy-patients", patientId, () ->
        circuitBreaker.execute("tasy-api", () ->
            retryHandler.execute("tasy-patient-load", () ->
                tasyClient.getPatient(patientId)
            )
        )
    );
}
```

**Pattern:** Cache → Circuit Breaker → Retry → External Call

**Decision Flow:**
1. **Cache hit?** → Return immediately
2. **Circuit open?** → Fail fast (no retry)
3. **Circuit closed?** → Execute with retry
4. **Retry exhausted?** → Send to DLQ, increment circuit failure count

**Benefits:**
- Cache eliminates unnecessary retries
- Circuit breaker prevents retry storms
- Retry recovers transient failures
- DLQ captures permanent failures

---

## 10. Business Impact Metrics

### Key Performance Indicators

| Metric | Target | Threshold | Action |
|--------|--------|-----------|--------|
| Retry success rate | >70% | <50% | Investigate root cause (may not be transient) |
| Retries per hour | <100 | >500 | Tune retry policy or fix systemic issue |
| Avg retry time | <1s | >5s | Reduce retry attempts or wait duration |
| Retry exhaustion rate | <5% | >20% | Increase max attempts or investigate failures |

### Cost Analysis
- **Positive:** 70% of retries succeed, avoiding DLQ and manual intervention
- **Negative:** Each retry adds 500ms-1s latency
- **Net Impact:** Reduced support tickets, improved user experience

---

## 11. Error Handling

### Retry Exhaustion
```java
try {
    return retryHandler.execute("insurance-eligibility", supplier);
} catch (Exception e) {
    // All retries exhausted
    log.error("Insurance eligibility check failed after retries", e);

    // Send to DLQ for manual review
    dlqHandler.addToQueue("insurance-eligibility", patientId, e);

    // Graceful degradation: use last known status
    return eligibilityCache.getLastKnown(patientId);
}
```

**Exception:** Original exception thrown after all retries exhausted
**Handling:** Send to DLQ, use cached data, or notify user

---

## 12. Testing Strategy

### Unit Tests
```java
@Test
void execute_shouldRetryOnRetryableException() {
    AtomicInteger attempts = new AtomicInteger(0);

    assertThatThrownBy(() ->
        retryHandler.execute("test-retry", () -> {
            attempts.incrementAndGet();
            throw new RuntimeException("timeout");
        })
    ).isInstanceOf(RuntimeException.class);

    assertThat(attempts.get()).isEqualTo(3); // 3 attempts made
}

@Test
void execute_shouldNotRetryOnNonRetryableException() {
    AtomicInteger attempts = new AtomicInteger(0);

    assertThatThrownBy(() ->
        retryHandler.execute("test-retry", () -> {
            attempts.incrementAndGet();
            throw new RuntimeException("400 Bad Request");
        })
    ).isInstanceOf(RuntimeException.class);

    assertThat(attempts.get()).isEqualTo(1); // Only 1 attempt
}
```

### Integration Tests
```java
@Test
void execute_shouldSucceedOnSecondAttempt() {
    AtomicInteger attempts = new AtomicInteger(0);

    String result = retryHandler.execute("test-retry", () -> {
        if (attempts.incrementAndGet() < 2) {
            throw new RuntimeException("503 Service Unavailable");
        }
        return "success";
    });

    assertThat(result).isEqualTo("success");
    assertThat(attempts.get()).isEqualTo(2);
}
```

---

## 13. Monitoring & Alerts

### Metrics Collection
```java
@Scheduled(fixedRate = 60000)
public void recordRetryMetrics() {
    retryRegistry.getAllRetries().forEach(retry -> {
        String name = retry.getName();
        Retry.Metrics metrics = retry.getMetrics();

        meterRegistry.gauge("retry.success.with.retry",
            Tags.of("operation", name),
            metrics.getNumberOfSuccessfulCallsWithRetryAttempt());

        meterRegistry.gauge("retry.failed.with.retry",
            Tags.of("operation", name),
            metrics.getNumberOfFailedCallsWithRetryAttempt());
    });
}
```

**Alert Rules:**
```yaml
alerts:
  - name: HighRetryRate
    condition: rate(retry.attempts[5m]) > 100
    severity: warning
    message: "Operation {{ $labels.operation }} has high retry rate (>100/5min)"

  - name: RetryExhaustionSpike
    condition: rate(retry.failed.with.retry[5m]) > 10
    severity: critical
    message: "Operation {{ $labels.operation }} exhausting retries (>10/5min)"
```

---

## 14. Best Practices

### Retry Configuration Guidelines

| Integration Type | Max Attempts | Wait Duration | Rationale |
|------------------|--------------|---------------|-----------|
| Critical (TASY) | 5 | 1-2s | High value, tolerate latency |
| Standard (Insurance) | 3 | 500ms | Balanced approach |
| Non-critical (WhatsApp) | 2 | 100ms | Fail fast, low priority |
| Rate-limited (TISS) | 3 | 2s | Wait for rate limit reset |

### Idempotency Requirements
**Critical:** All retried operations MUST be idempotent

**Example Issue:**
```java
// ❌ BAD: Non-idempotent payment processing
retryHandler.execute("process-payment", () -> {
    paymentGateway.charge(creditCard, amount);  // May charge multiple times!
});

// ✅ GOOD: Idempotent with idempotency key
retryHandler.execute("process-payment", () -> {
    String idempotencyKey = "payment-" + transactionId;
    paymentGateway.charge(creditCard, amount, idempotencyKey);
});
```

---

## 15. Related Components

### Direct Dependencies
- `RN-CircuitBreakerCoordinator.md` - Outer resilience layer
- `RN-IntegrationDlqHandler.md` - Handles retry exhaustion
- `RN-IntegrationConfig.md` - Provides RestTemplate with timeouts

### Downstream Consumers
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/insurance/InsuranceApiClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/tiss/TissSubmissionClient.java`

---

## 16. Future Enhancements

### Planned Improvements
1. **Adaptive Retry:** Adjust wait duration based on error type
2. **Jitter:** Add randomization to prevent thundering herd
3. **Retry Budget:** Global rate limiting of retries
4. **Distributed Retry:** Share retry state across instances
5. **Smart Retry:** ML-based prediction of retry success probability

### Technical Debt
- Fixed exponential backoff (no configuration)
- No jitter (synchronized retry storms possible)
- Manual retryable exception detection (no declarative config)

---

**Version:** 1.0
**Last Updated:** 2025-01-12
**Status:** Production Active
