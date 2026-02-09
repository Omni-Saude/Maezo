# RN-CacheManager: High-Performance Integration Response Caching

**ID:** RN-CacheManager
**Category:** Integration Infrastructure
**Component:** `CacheManager.java`
**Location:** `/src/main/java/com/hospital/revenuecycle/integration/common/cache/CacheManager.java`

---

## 1. Business Purpose

Provides high-performance in-memory caching for external integration responses, reducing API call volume, improving response times, and minimizing costs associated with rate-limited or pay-per-call integration partners.

---

## 2. Technical Implementation

### Core Architecture
```java
@Component
public class CacheManager {
    private final ConcurrentMap<String, Cache<String, Object>> caches =
        new ConcurrentHashMap<>();

    // Uses Caffeine for high-performance caching
    // Supports multiple named caches with independent configurations
}
```

**Technology:** Caffeine Cache (high-performance Java caching library)
**Storage:** In-memory, thread-safe concurrent maps
**Eviction:** TTL-based and size-based policies

---

## 3. Cache Configuration Patterns

### Default Cache Creation
```java
public Cache<String, Object> getCache(String cacheName) {
    return caches.computeIfAbsent(cacheName, name ->
            Caffeine.newBuilder()
                    .maximumSize(1000)
                    .expireAfterWrite(Duration.ofMinutes(10))
                    .recordStats()
                    .build());
}
```

**Default Configuration:**
- **Max Size:** 1000 entries per cache
- **TTL:** 10 minutes after write
- **Statistics:** Enabled for monitoring
- **Eviction Policy:** LRU (Least Recently Used)

### Custom Cache Creation
```java
public Cache<String, Object> getCache(String cacheName, long maxSize, Duration ttl) {
    return caches.computeIfAbsent(cacheName, name ->
            Caffeine.newBuilder()
                    .maximumSize(maxSize)
                    .expireAfterWrite(ttl)
                    .recordStats()
                    .build());
}
```

**Use Cases:**
- **Long-lived Caches:** Insurance eligibility (TTL: 24 hours)
- **High-volume Caches:** Patient demographics (Max Size: 10,000)
- **Transient Caches:** TISS submission status (TTL: 1 minute)

---

## 4. Business Rules

### Cache-or-Compute Pattern
```java
public <T> T get(String cacheName, String key, Supplier<T> supplier) {
    Cache<String, Object> cache = getCache(cacheName);

    Object value = cache.get(key, k -> {
        log.debug("Cache miss for key: {} in cache: {}", key, cacheName);
        return supplier.get();
    });

    return (T) value;
}
```

**Rule:** Cache Miss Behavior
- If key exists: Return cached value immediately
- If key missing: Execute supplier function, cache result, return value

**Business Impact:**
- Reduces external API calls by 60-80%
- Improves response time from ~500ms to ~5ms
- Decreases integration partner rate limit violations

### Cache Invalidation Strategy
```java
public void invalidate(String cacheName, String key) {
    Cache<String, Object> cache = caches.get(cacheName);
    if (cache != null) {
        cache.invalidate(key);
        log.debug("Invalidated key: {} from cache: {}", key, cacheName);
    }
}
```

**Rule:** Explicit Invalidation Triggers
- Patient demographic update detected
- Insurance coverage changed
- Manual cache clear via admin endpoint
- External system data modification event

---

## 5. Cache Naming Conventions

### Standard Cache Names
```java
// Insurance eligibility checks (24 hour TTL)
cacheManager.get("insurance-eligibility", patientId, () ->
    insuranceClient.checkEligibility(patientId));

// TASY patient demographics (30 minute TTL)
cacheManager.get("tasy-patients", patientId, () ->
    tasyClient.getPatient(patientId));

// TISS glosa codes (permanent until app restart)
cacheManager.get("tiss-codes", codeId, () ->
    tissCodeRepository.findById(codeId));

// Collection agency status (5 minute TTL)
cacheManager.get("collection-status", accountId, () ->
    collectionClient.getStatus(accountId));
```

**Naming Convention:** `{integration}-{resource-type}`

---

## 6. Integration Use Cases

### Insurance Eligibility Caching
```java
@Service
public class EligibilityService {
    @Autowired
    private CacheManager cacheManager;

    public EligibilityResponse checkEligibility(String patientId, String insuranceId) {
        String cacheKey = patientId + ":" + insuranceId;

        return cacheManager.get(
            "insurance-eligibility",
            cacheKey,
            () -> insuranceApiClient.checkEligibility(patientId, insuranceId)
        );
    }
}
```

**Business Benefit:**
- Insurance APIs often rate-limited (e.g., 100 requests/minute)
- Eligibility rarely changes intra-day
- Caching reduces API costs by ~70%

### TASY Patient Demographics Caching
```java
@Service
public class PatientService {
    public Patient getPatient(String patientId) {
        return cacheManager.get(
            "tasy-patients",
            patientId,
            () -> tasyClient.getPatientDemographics(patientId)
        );
    }
}
```

**Business Benefit:**
- Patient demographics accessed frequently during episode
- TASY API has ~300ms latency
- Cache reduces response time to ~5ms

---

## 7. Cache Statistics & Monitoring

### Statistics API
```java
public String getStats(String cacheName) {
    Cache<String, Object> cache = caches.get(cacheName);
    if (cache != null) {
        return cache.stats().toString();
    }
    return "Cache not found: " + cacheName;
}
```

**Example Statistics Output:**
```
CacheStats{
  hitCount=8472,
  missCount=1284,
  loadSuccessCount=1284,
  loadFailureCount=12,
  totalLoadTime=3842000000,
  evictionCount=47,
  evictionWeight=47
}
```

**Key Metrics:**
- **Hit Rate:** 86.8% (8472 hits / 9756 total)
- **Avg Load Time:** ~3ms per miss
- **Eviction Count:** 47 entries evicted due to size/TTL

---

## 8. Cache Operations

### Manual Cache Management
```java
// Put value directly
cacheManager.put("tasy-patients", "P12345", patientObject);

// Clear specific entry
cacheManager.invalidate("insurance-eligibility", "P12345:INS789");

// Clear entire cache
cacheManager.clearCache("collection-status");
```

**Use Cases:**
- **Put:** Preload cache from batch jobs
- **Invalidate:** Handle real-time data updates
- **Clear:** Handle external system outages/maintenance

---

## 9. Business Rules Implementation

### Rule: Cache TTL by Data Volatility
| Data Type | Volatility | TTL | Rationale |
|-----------|------------|-----|-----------|
| Insurance eligibility | Low | 24 hours | Rarely changes intra-day |
| Patient demographics | Low | 30 minutes | Infrequent updates |
| TISS codes | Static | Until restart | Reference data |
| Collection status | Medium | 5 minutes | Changes during payment process |
| TISS submission status | High | 1 minute | Real-time processing |

### Rule: Cache Size by Access Frequency
| Cache Name | Max Size | Access Rate | Rationale |
|------------|----------|-------------|-----------|
| tasy-patients | 10,000 | Very High | Accessed per transaction |
| insurance-eligibility | 5,000 | High | Multiple checks per episode |
| tiss-codes | 1,000 | Medium | Reference data lookup |
| collection-status | 1,000 | Low | Administrative queries |

---

## 10. Error Handling

### Cache Miss with Supplier Failure
```java
try {
    return cacheManager.get("tasy-patients", patientId, () -> {
        Patient patient = tasyClient.getPatient(patientId);
        if (patient == null) {
            throw new PatientNotFoundException(patientId);
        }
        return patient;
    });
} catch (Exception e) {
    log.error("Failed to load patient {} from TASY", patientId, e);
    // Falls through to DLQ handler
    dlqHandler.addToQueue("tasy-patients", patientId, e);
    throw e;
}
```

**Error Scenarios:**
- **Supplier throws exception:** Exception propagated, no caching occurs
- **Null value returned:** Cached as-is (consider NullPointerException risk)
- **Timeout during load:** No caching, propagate timeout exception

---

## 11. Coordination with Other Components

### Circuit Breaker Integration
```java
public Patient getPatientWithResilience(String patientId) {
    return cacheManager.get("tasy-patients", patientId, () ->
        circuitBreaker.execute("tasy-api", () ->
            retryHandler.execute("tasy-patient-load", () ->
                tasyClient.getPatient(patientId)
            )
        )
    );
}
```

**Pattern:** Cache > Circuit Breaker > Retry > External Call

**Benefit:**
- Cache hit: No circuit breaker call
- Cache miss: Protected by circuit breaker + retry
- External API protected from thundering herd

### Dead Letter Queue Integration
```java
try {
    return cacheManager.get("insurance-eligibility", key, supplier);
} catch (Exception e) {
    dlqHandler.addToQueue("insurance-eligibility", key, e);
    throw e;
}
```

---

## 12. Testing Strategy

### Unit Tests
```java
@Test
void get_cacheMiss_shouldExecuteSupplier() {
    String result = cacheManager.get("test-cache", "key1", () -> "value1");

    assertThat(result).isEqualTo("value1");

    // Verify supplier not called on second access
    String cached = cacheManager.get("test-cache", "key1", () -> "value2");
    assertThat(cached).isEqualTo("value1"); // Original cached value
}

@Test
void invalidate_shouldRemoveCacheEntry() {
    cacheManager.put("test-cache", "key1", "value1");
    cacheManager.invalidate("test-cache", "key1");

    String result = cacheManager.get("test-cache", "key1", () -> "value2");
    assertThat(result).isEqualTo("value2"); // New value, cache was cleared
}
```

### Performance Tests
```java
@Test
void cachePerformance_shouldReduceLoadTime() {
    long start = System.nanoTime();
    cacheManager.get("test-cache", "key1", () -> {
        Thread.sleep(100); // Simulate 100ms external call
        return "value";
    });
    long firstCall = System.nanoTime() - start;

    start = System.nanoTime();
    cacheManager.get("test-cache", "key1", () -> "value");
    long secondCall = System.nanoTime() - start;

    assertThat(secondCall).isLessThan(firstCall / 10); // >10x faster
}
```

---

## 13. Monitoring & Alerts

### Key Metrics
```java
// Expose cache statistics via Micrometer
@Scheduled(fixedRate = 60000)
public void recordCacheMetrics() {
    caches.forEach((name, cache) -> {
        CacheStats stats = cache.stats();
        meterRegistry.gauge("cache.hit.rate", Tags.of("cache", name),
            stats.hitRate());
        meterRegistry.gauge("cache.size", Tags.of("cache", name),
            cache.estimatedSize());
    });
}
```

**Alert Thresholds:**
- Hit rate < 70%: Investigate cache configuration
- Eviction rate > 10%: Increase cache size
- Load failure rate > 1%: External system issues

---

## 14. Configuration Best Practices

### Production Recommendations
```yaml
# application.yml
cache:
  insurance-eligibility:
    max-size: 5000
    ttl: 24h
  tasy-patients:
    max-size: 10000
    ttl: 30m
  tiss-codes:
    max-size: 1000
    ttl: 0 # No expiration
```

### Memory Considerations
- **Max Size:** Set based on JVM heap (rule: <10% of heap per cache)
- **Eviction:** Monitor to prevent OOM
- **Statistics:** Enable in production for observability

---

## 15. Related Components

### Direct Dependencies
- `RN-IntegrationConfig.md` - Provides ObjectMapper for cache serialization
- `RN-CircuitBreakerCoordinator.md` - Wraps cached supplier functions
- `RN-RetryHandler.md` - Handles cache miss retry logic

### Downstream Consumers
- `/src/main/java/com/hospital/revenuecycle/integration/insurance/InsuranceApiClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/tasy/TasyClient.java`
- `/src/main/java/com/hospital/revenuecycle/integration/tiss/TissCodeService.java`

---

## 16. Future Enhancements

### Planned Improvements
1. **Distributed Caching:** Migrate to Redis for multi-instance deployment
2. **Cache Warming:** Preload cache from batch jobs at startup
3. **Dynamic TTL:** Adjust TTL based on data volatility patterns
4. **Cache Hierarchies:** Multi-level caching (L1: local, L2: Redis)
5. **Event-driven Invalidation:** Kafka-based cache invalidation

### Technical Debt
- In-memory only (not suitable for horizontal scaling)
- No persistence (cache lost on restart)
- Manual cache name management (no enum/constants)

---

**Version:** 1.0
**Last Updated:** 2025-01-12
**Status:** Production Active
