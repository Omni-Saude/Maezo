# RN-IntegrationDlqHandler: Dead Letter Queue for Failed Integration Requests

**ID:** RN-IntegrationDlqHandler
**Category:** Integration Infrastructure
**Component:** `IntegrationDlqHandler.java`
**Location:** `/src/main/java/com/hospital/revenuecycle/integration/common/dlq/IntegrationDlqHandler.java`

---

## 1. Business Purpose

Captures and stores failed integration requests for manual review, retry, and root cause analysis. Ensures no revenue cycle transactions are lost due to temporary integration failures, maintaining audit trail and enabling recovery workflows.

---

## 2. Technical Implementation

### Core Architecture
```java
@Component
@RequiredArgsConstructor
public class IntegrationDlqHandler {
    private final ObjectMapper objectMapper;
    private final Map<String, List<FailedRequest>> dlqStore = new ConcurrentHashMap<>();

    // In-memory storage of failed requests by integration name
    // Thread-safe for concurrent access
}
```

**Storage:** In-memory concurrent map (production should use database)
**Serialization:** Jackson ObjectMapper for request payload JSON
**Scope:** Per-integration DLQ (TASY, TISS, Insurance, etc.)

---

## 3. Failed Request Model

### FailedRequest Structure
```java
@Data
@Builder
public static class FailedRequest {
    private String id;                       // UUID for tracking
    private String integration;              // Integration name (e.g., "tasy", "tiss")
    private String requestPayload;           // Original request as JSON
    private String errorMessage;             // Exception message
    private String stackTrace;               // Full stack trace for debugging
    private LocalDateTime timestamp;         // When failure occurred
    private LocalDateTime lastRetryTimestamp; // Last retry attempt
    private int retryCount;                  // Number of retry attempts
}
```

**Key Fields:**
- **ID:** Unique identifier for tracking and retrieval
- **Integration:** Groups failures by external system
- **Request Payload:** Serialized request for replay
- **Error Context:** Message + stack trace for root cause analysis
- **Retry Metadata:** Tracks manual/automatic retry attempts

---

## 4. Business Rules

### Rule: Capture All Permanent Failures
**Condition:** Request fails after all retry attempts exhausted

**Implementation:**
```java
public void addToQueue(String integration, Object request, Throwable error) {
    FailedRequest failedRequest = FailedRequest.builder()
            .id(UUID.randomUUID().toString())
            .integration(integration)
            .requestPayload(serializeRequest(request))
            .errorMessage(error.getMessage())
            .stackTrace(getStackTrace(error))
            .timestamp(LocalDateTime.now())
            .retryCount(0)
            .build();

    dlqStore.computeIfAbsent(integration, k -> new ArrayList<>())
            .add(failedRequest);

    log.error("Added failed request to DLQ for {}: {}", integration, failedRequest.getId(), error);
}
```

**Business Impact:**
- No revenue cycle transactions lost
- All failures auditable and recoverable
- Root cause analysis enabled

### Rule: DLQ Entry Removal After Success
**Condition:** Failed request successfully retried or manually resolved

**Implementation:**
```java
public void removeFromQueue(String integration, String requestId) {
    List<FailedRequest> requests = dlqStore.get(integration);
    if (requests != null) {
        requests.removeIf(req -> req.getId().equals(requestId));
        log.info("Removed request {} from DLQ for {}", requestId, integration);
    }
}
```

**Rationale:**
- Keeps DLQ clean (only active failures)
- Prevents duplicate processing
- Enables accurate failure metrics

---

## 5. Integration Use Cases

### TASY Patient Load Failure
```java
@Service
public class TasyPatientService {
    public Patient getPatient(String patientId) {
        try {
            return circuitBreaker.execute("tasy-api", () ->
                retryHandler.execute("tasy-patient-load", () ->
                    tasyClient.getPatient(patientId)
                )
            );
        } catch (Exception e) {
            // All resilience mechanisms failed
            dlqHandler.addToQueue("tasy",
                Map.of("patientId", patientId),
                e);
            throw e;
        }
    }
}
```

**Scenario:** TASY database offline for maintenance
- Circuit breaker opens after 5 failures
- All subsequent requests fail immediately
- Each failure captured in DLQ
- After maintenance, DLQ entries manually replayed

### TISS Claim Submission Failure
```java
public SubmissionResult submitClaim(TissRequest request) {
    try {
        return tissClient.submit(request);
    } catch (TissSubmissionException e) {
        if (e.isPermanent()) {
            // Permanent error (e.g., invalid CPF)
            dlqHandler.addToQueue("tiss", request, e);
            throw e;
        } else {
            // Transient error (retry via RetryHandler)
            throw e;
        }
    }
}
```

**Scenario:** TISS claim has invalid data
- Validation fails at TISS gateway
- Not retryable (permanent business error)
- Captured in DLQ for manual correction
- Admin reviews DLQ, corrects CPF, resubmits

### Insurance Eligibility Timeout
```java
public EligibilityResponse checkEligibility(String patientId) {
    try {
        return insuranceClient.checkEligibility(patientId);
    } catch (TimeoutException e) {
        // Add to DLQ for later processing
        dlqHandler.addToQueue("insurance",
            Map.of("patientId", patientId),
            e);

        // Return last known eligibility
        return eligibilityCache.getLastKnown(patientId);
    }
}
```

**Scenario:** Insurance API experiencing high latency
- Request times out after 10 seconds
- Captured in DLQ
- Background job retries DLQ entries every 5 minutes
- Succeeds when API latency improves

---

## 6. DLQ Management Operations

### Query Failed Requests
```java
// Get all failed requests for an integration
List<FailedRequest> tasyFailures = dlqHandler.getFailedRequests("tasy");

// Get specific failed request by ID
Optional<FailedRequest> request = dlqHandler.getFailedRequest(requestId);
```

**Use Cases:**
- Admin dashboard showing DLQ entries
- Automated alerting on DLQ size
- Root cause analysis queries

### Retry Failed Requests
```java
// Manual retry from admin interface
public void retryFailedRequest(String requestId) {
    Optional<FailedRequest> optRequest = dlqHandler.getFailedRequest(requestId);

    if (optRequest.isPresent()) {
        FailedRequest request = optRequest.get();

        try {
            // Deserialize and retry original request
            Object payload = objectMapper.readValue(
                request.getRequestPayload(),
                Object.class
            );

            // Execute retry (integration-specific)
            retryIntegrationRequest(request.getIntegration(), payload);

            // Success - remove from DLQ
            dlqHandler.removeFromQueue(request.getIntegration(), requestId);

        } catch (Exception e) {
            // Retry failed - increment counter
            dlqHandler.incrementRetryCount(requestId);
            throw e;
        }
    }
}
```

### Clear DLQ
```java
// Clear all entries for an integration (e.g., after fixing root cause)
dlqHandler.clearQueue("tasy");

// Clear specific entry after manual resolution
dlqHandler.removeFromQueue("tiss", requestId);
```

---

## 7. Monitoring & Statistics

### DLQ Metrics
```java
public Map<String, Integer> getStatistics() {
    Map<String, Integer> stats = new HashMap<>();
    dlqStore.forEach((integration, requests) ->
            stats.put(integration, requests.size()));
    return stats;
}
```

**Example Output:**
```json
{
  "tasy": 12,
  "tiss": 5,
  "insurance": 3,
  "whatsapp": 0
}
```

**Business Metrics:**
- **DLQ Size:** Number of pending failures per integration
- **Retry Success Rate:** Successful retries / total retries
- **Age of Oldest Entry:** Time since oldest failure (SLA tracking)
- **Failure Patterns:** Common error messages (root cause analysis)

---

## 8. Automated DLQ Processing

### Background Retry Job
```java
@Scheduled(fixedDelay = 300000) // Every 5 minutes
public void processeDlqEntries() {
    dlqStore.forEach((integration, requests) -> {
        requests.stream()
            .filter(req -> req.getRetryCount() < 5)
            .forEach(req -> {
                try {
                    retryFailedRequest(req.getId());
                    log.info("DLQ retry succeeded for {}", req.getId());
                } catch (Exception e) {
                    log.warn("DLQ retry failed for {}", req.getId(), e);
                }
            });
    });
}
```

**Policy:**
- Retry every 5 minutes
- Maximum 5 retry attempts
- After 5 failures, requires manual intervention

---

## 9. Error Context Preservation

### Request Serialization
```java
private String serializeRequest(Object request) {
    try {
        return objectMapper.writeValueAsString(request);
    } catch (Exception e) {
        log.warn("Failed to serialize request", e);
        return request.toString();
    }
}
```

**Purpose:**
- Enables exact replay of failed request
- Preserves request context for debugging
- Supports audit trail requirements

### Stack Trace Capture
```java
private String getStackTrace(Throwable error) {
    StringBuilder sb = new StringBuilder();
    for (StackTraceElement element : error.getStackTrace()) {
        sb.append(element.toString()).append("\n");
    }
    return sb.toString();
}
```

**Purpose:**
- Root cause analysis
- Pattern detection (e.g., common failure points)
- Developer debugging

---

## 10. Business Impact Metrics

### Key Performance Indicators

| Metric | Target | Threshold | Action |
|--------|--------|-----------|--------|
| DLQ size | <10 entries | >100 entries | Investigate integration outage |
| DLQ entry age | <1 hour | >24 hours | Manual intervention required |
| Retry success rate | >80% | <50% | Root cause not transient |
| DLQ growth rate | <5/hour | >50/hour | Circuit breaker not working |

### Cost Analysis
- **Storage Cost:** Minimal (in-memory), but production needs persistent storage
- **Processing Cost:** Background jobs consume CPU/memory
- **Manual Review Cost:** ~10 minutes per complex DLQ entry
- **Business Value:** Prevents lost revenue from unprocessed claims

---

## 11. Coordination with Other Components

### Resilience Stack Integration
```java
public void processRequestWithFullResilience(String patientId) {
    try {
        // Layer 1: Cache
        cacheManager.get("tasy-patients", patientId, () ->
            // Layer 2: Circuit Breaker
            circuitBreaker.execute("tasy-api", () ->
                // Layer 3: Retry
                retryHandler.execute("tasy-patient-load", () ->
                    // Layer 4: External Call
                    tasyClient.getPatient(patientId)
                )
            )
        );
    } catch (Exception e) {
        // All layers failed - send to DLQ
        dlqHandler.addToQueue("tasy",
            Map.of("patientId", patientId),
            e);
    }
}
```

**Pattern:** DLQ is the "last line of defense"

---

## 12. Testing Strategy

### Unit Tests
```java
@Test
void addToQueue_shouldStoreFailedRequest() {
    dlqHandler.addToQueue("tasy",
        Map.of("patientId", "P12345"),
        new RuntimeException("Connection timeout"));

    List<FailedRequest> requests = dlqHandler.getFailedRequests("tasy");

    assertThat(requests).hasSize(1);
    assertThat(requests.get(0).getIntegration()).isEqualTo("tasy");
    assertThat(requests.get(0).getErrorMessage()).contains("Connection timeout");
}

@Test
void removeFromQueue_shouldDeleteFailedRequest() {
    dlqHandler.addToQueue("tasy", request, error);
    List<FailedRequest> requests = dlqHandler.getFailedRequests("tasy");
    String requestId = requests.get(0).getId();

    dlqHandler.removeFromQueue("tasy", requestId);

    assertThat(dlqHandler.getFailedRequests("tasy")).isEmpty();
}
```

### Integration Tests
```java
@Test
void dlqRetry_shouldReplayFailedRequest() {
    // Simulate failure
    dlqHandler.addToQueue("tasy", requestPayload, error);

    // Mock successful retry
    when(tasyClient.getPatient("P12345")).thenReturn(patient);

    // Retry from DLQ
    retryFailedRequest(requestId);

    // Verify removal from DLQ
    assertThat(dlqHandler.getFailedRequests("tasy")).isEmpty();
}
```

---

## 13. Admin Interface Integration

### DLQ Dashboard Endpoints
```java
@RestController
@RequestMapping("/api/admin/dlq")
public class DlqAdminController {

    @GetMapping("/statistics")
    public Map<String, Integer> getStatistics() {
        return dlqHandler.getStatistics();
    }

    @GetMapping("/{integration}")
    public List<FailedRequest> getFailedRequests(@PathVariable String integration) {
        return dlqHandler.getFailedRequests(integration);
    }

    @PostMapping("/{integration}/{requestId}/retry")
    public ResponseEntity<?> retryRequest(
            @PathVariable String integration,
            @PathVariable String requestId) {
        retryService.retryFailedRequest(requestId);
        return ResponseEntity.ok().build();
    }

    @DeleteMapping("/{integration}/{requestId}")
    public ResponseEntity<?> removeRequest(
            @PathVariable String integration,
            @PathVariable String requestId) {
        dlqHandler.removeFromQueue(integration, requestId);
        return ResponseEntity.ok().build();
    }
}
```

**UI Features:**
- List all DLQ entries by integration
- View request details (payload, error, timestamps)
- Manual retry button
- Bulk retry/delete operations
- DLQ size alerts and trends

---

## 14. Compliance & Audit

### LGPD Compliance
- **Data Retention:** DLQ entries must be purged after resolution (no indefinite storage)
- **PII Protection:** Request payloads may contain PII (must be encrypted at rest)
- **Access Control:** DLQ admin interface requires elevated permissions
- **Audit Trail:** All DLQ operations logged for compliance

### TISS Standards
- **Error Tracking:** TISS requires tracking of all submission failures
- **Retry Policy:** Aligns with TISS recommendation of 3 automatic retries
- **Error Codes:** DLQ captures TISS-specific error codes for reporting

---

## 15. Related Components

### Direct Dependencies
- `RN-IntegrationConfig.md` - Provides ObjectMapper for serialization
- `RN-CircuitBreakerCoordinator.md` - Sends failures to DLQ when circuit open
- `RN-RetryHandler.md` - Sends failures to DLQ after retry exhaustion

### Downstream Consumers
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/tiss/TissSubmissionClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/insurance/InsuranceApiClient.java`

---

## 16. Future Enhancements

### Planned Improvements
1. **Persistent Storage:** Migrate from in-memory to PostgreSQL for durability
2. **Kafka DLQ:** Use Kafka topics for distributed DLQ processing
3. **Smart Retry:** ML-based retry scheduling based on failure patterns
4. **DLQ Analytics:** Trend analysis, common failure root causes
5. **Automated Resolution:** Auto-correct known issues (e.g., format errors)

### Technical Debt
- In-memory storage (data lost on restart)
- No DLQ size limits (potential memory leak)
- Manual serialization (should use generic serializer)
- No DLQ aging policy (old entries never purged)

---

**Version:** 1.0
**Last Updated:** 2025-01-12
**Status:** Production Active
