# RN-CircuitBreakerCoordinator: Fault Tolerance & Cascading Failure Prevention

**ID:** RN-CircuitBreakerCoordinator
**Category:** Integration Resilience
**Component:** `CircuitBreakerCoordinator.java`
**Location:** `/src/main/java/com/hospital/revenuecycle/integration/common/circuit/CircuitBreakerCoordinator.java`

---

## 1. Business Purpose

Implements the Circuit Breaker pattern to prevent cascading failures across external integrations, ensuring system stability when integration partners experience degradation or outages. Protects revenue cycle operations from being blocked by failing external systems.

---

## 2. Circuit Breaker States

### State Machine
```
CLOSED (Normal) ─[Failure Threshold]→ OPEN (Failing Fast)
    ↑                                        ↓
    └────────[Recovery]────── HALF_OPEN (Testing)
```

### State Descriptions

#### CLOSED State
- **Behavior:** All requests pass through to external system
- **Monitoring:** Track success/failure rates
- **Transition:** Opens if failure rate exceeds 50%

#### OPEN State
- **Behavior:** Requests fail immediately without calling external system
- **Duration:** 30 seconds (wait duration)
- **Transition:** After wait duration, transitions to HALF_OPEN

#### HALF_OPEN State
- **Behavior:** Allow limited requests (5) to test if service recovered
- **Evaluation:** If requests succeed, transition to CLOSED; if fail, back to OPEN
- **Purpose:** Gradual recovery verification

---

## 3. Technical Implementation

### Default Configuration
```java
public CircuitBreakerCoordinator() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .failureRateThreshold(50)                    // Open if 50% fail
            .slowCallRateThreshold(50)                   // Consider slow if >50% slow
            .slowCallDurationThreshold(Duration.ofSeconds(5))
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .permittedNumberOfCallsInHalfOpenState(5)
            .minimumNumberOfCalls(5)
            .slidingWindowSize(10)
            .build();

    this.circuitBreakerRegistry = CircuitBreakerRegistry.of(config);
}
```

**Configuration Parameters:**
- **Failure Rate Threshold:** 50% (5 out of 10 calls)
- **Slow Call Threshold:** 50% calls taking >5 seconds
- **Wait Duration:** 30 seconds before attempting recovery
- **Half-Open Calls:** 5 test calls to verify recovery
- **Sliding Window:** Last 10 calls evaluated for state transitions

---

## 4. Business Rules

### Rule: Automatic Failure Detection
**Condition:** Circuit breaker opens when failure rate exceeds threshold

**Implementation:**
```java
public <T> T execute(String name, Supplier<T> supplier) {
    CircuitBreaker circuitBreaker = circuitBreakerRegistry.circuitBreaker(name);

    // Register event listeners
    registerEventListeners(circuitBreaker, name);

    // Decorate and execute
    Supplier<T> decoratedSupplier = CircuitBreaker.decorateSupplier(circuitBreaker, supplier);
    return decoratedSupplier.get();
}
```

**Business Impact:**
- TASY API down: Circuit opens, UI shows cached patient data
- Insurance API degraded: Circuit opens, eligibility checks deferred
- TISS submission failing: Circuit opens, claims queued for later submission

### Rule: Fail-Fast on Open Circuit
**Condition:** When circuit is OPEN, reject requests immediately

**Behavior:**
```java
if (circuitBreaker.getState() == CircuitBreaker.State.OPEN) {
    throw new CallNotPermittedException("Circuit breaker is OPEN for: " + name);
}
```

**Business Impact:**
- Prevents thread pool exhaustion
- Reduces user wait time (fail in <1ms vs waiting 30s for timeout)
- Enables graceful degradation (e.g., show cached data)

---

## 5. Integration Use Cases

### TASY API Protection
```java
@Service
public class TasyPatientService {
    @Autowired
    private CircuitBreakerCoordinator circuitBreaker;

    public Patient getPatient(String patientId) {
        return circuitBreaker.execute("tasy-api", () ->
            tasyClient.getPatient(patientId)
        );
    }
}
```

**Scenario:** TASY EHR experiences database issues
- **5 consecutive failures** → Circuit opens
- **All subsequent calls fail immediately** (no wait)
- **After 30 seconds** → Circuit allows 5 test calls
- **If successful** → Circuit closes, normal operation resumes

### Insurance Eligibility Protection
```java
public EligibilityResponse checkEligibility(String patientId) {
    try {
        return circuitBreaker.execute("insurance-api", () ->
            insuranceClient.checkEligibility(patientId)
        );
    } catch (CallNotPermittedException e) {
        // Circuit is open, return last known status
        return eligibilityCache.getLastKnown(patientId);
    }
}
```

**Graceful Degradation:**
- Circuit open → Use cached eligibility status
- Display warning: "Eligibility data may be stale"
- Allow manual override for urgent cases

### TISS Submission Protection
```java
public SubmissionResult submitClaim(TissRequest request) {
    try {
        return circuitBreaker.execute("tiss-submission", () ->
            tissClient.submitClaim(request)
        );
    } catch (CallNotPermittedException e) {
        // Queue for later submission
        dlqHandler.addToQueue("tiss-submission", request, e);
        return SubmissionResult.queued();
    }
}
```

**Business Continuity:**
- Circuit open → Claims queued automatically
- Background job retries when circuit closes
- No manual intervention required

---

## 6. Event Monitoring

### State Transition Events
```java
private void registerEventListeners(CircuitBreaker circuitBreaker, String name) {
    circuitBreaker.getEventPublisher()
            .onStateTransition(event ->
                    log.warn("Circuit breaker '{}' state changed: {} -> {}",
                            name,
                            event.getStateTransition().getFromState(),
                            event.getStateTransition().getToState()))
            .onError(event ->
                    log.error("Circuit breaker '{}' recorded error", name, event.getThrowable()))
            .onSuccess(event ->
                    log.debug("Circuit breaker '{}' recorded success", name));
}
```

**Event Types:**
- **State Transition:** CLOSED → OPEN → HALF_OPEN → CLOSED
- **Error Recording:** Each failure increments failure counter
- **Success Recording:** Resets failure counter in CLOSED state

---

## 7. Manual Circuit Control

### Administrative Operations
```java
// Manually reset circuit (e.g., after maintenance window)
circuitBreakerCoordinator.reset("tasy-api");

// Manually open circuit (e.g., before planned maintenance)
circuitBreakerCoordinator.transitionToOpenState("insurance-api");

// Check current state
CircuitBreaker.State state = circuitBreakerCoordinator.getState("tiss-submission");
```

**Use Cases:**
- **Reset:** After confirming external system recovery
- **Manual Open:** Before planned maintenance to prevent alerts
- **State Check:** Health check endpoints, admin dashboards

---

## 8. Custom Circuit Breakers

### Per-Integration Tuning
```java
// TASY API: More lenient (healthcare-critical)
CircuitBreaker tasyCircuit = circuitBreakerCoordinator.createCustom(
    "tasy-api",
    70.0f,  // Open at 70% failure (vs default 50%)
    Duration.ofMinutes(1)  // Wait 1 minute before retry (vs 30s)
);

// WhatsApp API: Strict (non-critical)
CircuitBreaker whatsappCircuit = circuitBreakerCoordinator.createCustom(
    "whatsapp-api",
    30.0f,  // Open at 30% failure
    Duration.ofSeconds(10)  // Wait only 10 seconds
);
```

**Rationale:**
- **Critical Systems:** Higher failure tolerance, longer recovery wait
- **Non-Critical Systems:** Lower tolerance, faster recovery attempts

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
1. **Cache hit?** → Return immediately (bypass circuit)
2. **Circuit open?** → Fail fast (no external call)
3. **Circuit closed?** → Attempt call with retry protection
4. **Retry exhausted?** → Send to DLQ, open circuit

---

## 10. Business Impact Metrics

### Key Performance Indicators

| Metric | Target | Threshold | Action |
|--------|--------|-----------|--------|
| Circuit open duration | <5 min/day | >30 min/day | Investigate integration partner SLA |
| State transitions | <10/day | >50/day | Tune failure threshold or timeout |
| Fail-fast responses | <1ms | N/A | Performance goal achieved |
| Recovery success rate | >90% | <70% | Investigate root cause persistence |

### Cost Savings
- **Thread Pool Efficiency:** Prevents blocking threads on hung connections
- **User Experience:** Fast failures (1ms) vs timeout waits (30s)
- **Alert Fatigue:** Reduces redundant alerts during known outages

---

## 11. Error Handling

### Circuit Open Exception
```java
try {
    return circuitBreaker.execute("tasy-api", supplier);
} catch (CallNotPermittedException e) {
    log.warn("Circuit breaker '{}' is OPEN, failing fast", "tasy-api");

    // Attempt graceful degradation
    return cacheManager.get("tasy-patients-stale", patientId, () -> null);
}
```

**Exception:** `CallNotPermittedException` (from Resilience4j)
**Handling:** Graceful degradation, cached data, or user notification

---

## 12. Testing Strategy

### Unit Tests
```java
@Test
void circuitBreaker_shouldOpenAfterFailureThreshold() {
    CircuitBreakerCoordinator coordinator = new CircuitBreakerCoordinator();

    // Simulate 6 failures (threshold is 5)
    for (int i = 0; i < 6; i++) {
        try {
            coordinator.execute("test-circuit", () -> {
                throw new RuntimeException("Simulated failure");
            });
        } catch (Exception ignored) {}
    }

    // Circuit should now be OPEN
    assertThat(coordinator.getState("test-circuit"))
        .isEqualTo(CircuitBreaker.State.OPEN);
}
```

### Integration Tests
```java
@Test
void circuitBreaker_shouldFailFastWhenOpen() {
    coordinator.transitionToOpenState("test-circuit");

    long start = System.nanoTime();

    assertThatThrownBy(() ->
        coordinator.execute("test-circuit", () -> "value")
    ).isInstanceOf(CallNotPermittedException.class);

    long duration = System.nanoTime() - start;

    // Should fail in <1ms (vs 5000ms timeout)
    assertThat(duration).isLessThan(1_000_000);
}
```

---

## 13. Monitoring & Alerts

### Metrics Collection
```java
@Scheduled(fixedRate = 30000)
public void recordCircuitBreakerMetrics() {
    circuitBreakerRegistry.getAllCircuitBreakers().forEach(cb -> {
        String name = cb.getName();
        meterRegistry.gauge("circuit.breaker.state",
            Tags.of("circuit", name),
            cb.getState().getOrder());

        CircuitBreaker.Metrics metrics = cb.getMetrics();
        meterRegistry.gauge("circuit.breaker.failure.rate",
            Tags.of("circuit", name),
            metrics.getFailureRate());
    });
}
```

**Alert Rules:**
```yaml
alerts:
  - name: CircuitBreakerOpen
    condition: circuit.breaker.state == 1  # OPEN
    duration: 5m
    severity: warning
    message: "Circuit breaker {{ $labels.circuit }} has been open for >5 minutes"

  - name: CircuitBreakerFlapping
    condition: rate(circuit.breaker.state.transitions[5m]) > 10
    severity: critical
    message: "Circuit breaker {{ $labels.circuit }} flapping (>10 transitions in 5min)"
```

---

## 14. Compliance & Best Practices

### LGPD Considerations
- Circuit breaker events must not log PII
- Open circuit state does not expose sensitive error details
- Graceful degradation must maintain data privacy

### Performance Best Practices
- Use named circuit breakers per integration (not per method)
- Configure thresholds based on partner SLAs
- Monitor state transitions for early warning signs
- Combine with retry and cache for layered resilience

---

## 15. Related Components

### Direct Dependencies
- `RN-RetryHandler.md` - Inner resilience layer (retries before circuit opens)
- `RN-IntegrationDlqHandler.md` - Handles requests when circuit is open
- `RN-CacheManager.md` - Provides fallback data during outages

### Downstream Consumers
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/insurance/InsuranceApiClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/tiss/TissSubmissionClient.java`

---

## 16. Future Enhancements

### Planned Improvements
1. **Adaptive Thresholds:** Machine learning-based failure rate adjustment
2. **Distributed Circuit State:** Share circuit state across instances via Redis
3. **Circuit Breaker Dashboard:** Real-time visualization of all circuits
4. **Automatic SLA Tuning:** Configure thresholds from partner SLA definitions
5. **Predictive Opening:** Open circuit based on latency trends, not just failures

### Technical Debt
- No distributed state (each instance has independent circuit)
- Manual threshold configuration (no auto-tuning)
- Limited observability (no built-in dashboard)

---

**Version:** 1.0
**Last Updated:** 2025-01-12
**Status:** Production Active
