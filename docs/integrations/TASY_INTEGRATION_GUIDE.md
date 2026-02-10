# TASY ERP Integration Guide

## Overview

Tasy is Philips' hospital ERP system (Oracle database) used by Hospital AUSTA for patient management, billing, prescriptions, and vital signs tracking. The CIB Seven BPM platform integrates with Tasy through a dual-strategy approach:

- **Primary**: Change Data Capture (CDC) via Debezium for near-real-time synchronization
- **Fallback**: API polling when CDC is unavailable

All BPM workers consume FHIR resources from the HAPI FHIR R4 7.4.0 server, NOT directly from Tasy. FHIR adapters run in the background to sync Tasy data to the canonical FHIR data store, ensuring workers have clean, standardized healthcare data.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TASY ERP (Oracle Database)                       │
│                         Hospital AUSTA Production                        │
└────────────────┬────────────────────────────────────────────────────────┘
                 │
    ┌────────────┴────────────┬──────────────────┐
    │                         │                  │
    v                         v                  v

PRIMARY (ADR-004)        FALLBACK             POLLING
CDC via Debezium         Tasy REST API        Tasy REST API
│                        │                    │
├─ Oracle LogMiner       │                    │
├─ Redo Log Capture      │                    │
└─ Kafka Topics          v                    v
   (1-3s latency)    TasyApiClient    CDCFallbackPoller
                     (direct calls)    (periodic queries)
                     │                    │
                     └────────┬───────────┘
                              │
                              v
                    ┌─────────────────────┐
                    │   Kafka Broker      │
                    │  (Event Streaming)  │
                    │                     │
                    │ tasy.AUSTA.{TABLE}  │
                    └─────────┬───────────┘
                              │
                              v
                    ┌─────────────────────────┐
                    │  CDC-to-BPM Bridge      │
                    │  (Event Consumer)       │
                    │                         │
                    │  Deserializes/validates│
                    │  Loads to FHIR Server   │
                    └─────────┬───────────────┘
                              │
                              v
                    ┌─────────────────────────────────┐
                    │   HAPI FHIR R4 7.4.0 Server     │
                    │   (Canonical Data Store)        │
                    │                                 │
                    │  Patient, Encounter, Claim,     │
                    │  MedicationRequest, Observation │
                    └─────────┬───────────────────────┘
                              │
                ┌─────────────┼─────────────┬──────────────┐
                │             │             │              │
                v             v             v              v
            Clinical     Patient       Revenue      BPM
            Operations   Access        Cycle        Workers
            Worker       Worker        Worker       (Any domain)
```

### FHIR Adapter Layer

```
           Tasy API Client
           │
           v
    ┌─────────────────┐
    │ FHIR Adapters   │      All adapters:
    ├─────────────────┤
    │ Patient         │      - Read from Tasy API or CDC events
    │ Coverage        │      - Transform to FHIR resources
    │ Encounter       │      - Post to HAPI FHIR server
    │ Billing         │      - Run asynchronously
    │ Prescription    │      - Include correlation IDs
    │ VitalSigns      │      - Handle errors gracefully
    └────────┬────────┘
             │
             v
      HAPI FHIR Server
      (HTTP/REST)
```

## Data Flow

### Primary: CDC via Debezium (ADR-004)

**How it works:**
1. Tasy Oracle database writes changes to redo logs
2. Debezium connector reads redo logs via Oracle LogMiner
3. Changes are captured as CDC events
4. Events are published to Kafka topics (one per table)
5. CDC-to-BPM bridge consumes events and loads to FHIR server

**Advantages:**
- Near real-time synchronization (1-3 second latency)
- Zero impact on production database (read-only from logs)
- Captures ALL changes (updates, inserts, deletes)
- No polling overhead

**Kafka Topics:**
```
tasy.AUSTA.ATENDIMENTO          # Encounters
tasy.AUSTA.CONTA_MEDICA         # Billing claims
tasy.AUSTA.ITEM_CONTA           # Claim line items
tasy.AUSTA.PRESCRICAO           # Prescriptions
tasy.AUSTA.SINAL_VITAL          # Vital signs
```

**Related ADR:** ADR-004 (Debezium CDC for ERP Integration)

### Fallback: Polling via API (when CDC unavailable)

**How it works:**
1. CDCFallbackPoller checks if CDC is healthy
2. If CDC is down for >5 minutes, poller starts
3. Poller queries Tasy REST API at configured intervals
4. Detects changes via `LAST_UPDATE_DATE` column
5. Produces synthetic CDC events to same Kafka topics
6. Bridge consumes and processes normally

**Polling Intervals by Table:**
- ATENDIMENTO: 60 seconds
- CONTA_MEDICA: 120 seconds
- ITEM_CONTA: 300 seconds
- PRESCRICAO: 300 seconds
- SINAL_VITAL: 300 seconds

**State Tracking:**
- Last processed timestamp stored in Redis (per table, per tenant)
- Resume from checkpoint after restart
- No missed changes (unless Redis loses state)

**Latency Impact:**
- ~60-300 seconds (depends on table)
- Acceptable for non-critical flows
- Not recommended for real-time use cases

## Tasy Table to FHIR Mapping

| Tasy Table | FHIR Resource | Adapter Class | Kafka Topic | CDC Enabled |
|---|---|---|---|---|
| PACIENTE | Patient | TasyPatientAdapter | N/A (batch load) | No |
| CONVENIO_PACIENTE | Coverage | TasyCoverageAdapter | N/A (batch load) | No |
| ATENDIMENTO | Encounter | TasyEncounterAdapter | `tasy.AUSTA.ATENDIMENTO` | Yes |
| CONTA_MEDICA | Claim | TasyBillingAdapter | `tasy.AUSTA.CONTA_MEDICA` | Yes |
| ITEM_CONTA | Claim.item | TasyBillingAdapter | `tasy.AUSTA.ITEM_CONTA` | Yes |
| PRESCRICAO | MedicationRequest | TasyPrescriptionAdapter | `tasy.AUSTA.PRESCRICAO` | Yes |
| SINAL_VITAL | Observation | TasyVitalSignsAdapter | `tasy.AUSTA.SINAL_VITAL` | Yes |

**Notes:**
- PACIENTE and CONVENIO_PACIENTE are loaded via batch ETL (not CDC)
- FHIR resources include mappings for all relevant Tasy fields
- Adapters handle data type conversions and validation
- All resources include correlation IDs for traceability

## Authentication

Tasy API requires authentication. The platform supports multiple strategies:

### OAuth2 Client Credentials (Recommended)

```python
TasyApiSettings(
    base_url="https://tasy.austa.local/api",
    auth_type="oauth2",
    client_id="bpm-platform",           # from Vault
    client_secret="***",                # from Vault
    token_url="https://tasy.austa.local/oauth/token",
    scope="tasy:read"                   # optional
)
```

**Token Management:**
- Automatic token refresh handled by `TasyApiClient`
- Tokens cached in memory with expiry tracking
- Failed refresh triggers circuit breaker

### API Key (Legacy)

```python
TasyApiSettings(
    base_url="https://tasy.austa.local/api",
    auth_type="api_key",
    api_key="***",                      # from Vault
    api_key_header="X-API-Key"          # or "Authorization: Bearer"
)
```

### Credential Storage

- **Production**: HashiCorp Vault (recommended)
- **Development**: `.env` file (NEVER commit)
- **Testing**: Mock credentials

**Tenant-Aware Resolution:**
```python
from healthcare_platform.shared.context import TenantContext

async def get_tasy_settings():
    tenant_id = TenantContext.get_current_tenant()  # from request context
    # Vault lookup: vault/integrations/tasy/{tenant_id}
    return await vault.get_secret(f"integrations/tasy/{tenant_id}")
```

## Rate Limiting

### Default Configuration

- **Rate**: 10 requests/second (token bucket algorithm)
- **Burst**: 20 concurrent requests
- **Per Tenant**: Independent limits per tenant

### Configuration

```python
TasyApiSettings(
    ...
    rate_limit_rps=10,          # requests per second
    rate_limit_burst=20,        # concurrent requests
)
```

### Handling Rate Limits

If Tasy API returns `429 Too Many Requests`:
1. `TasyApiClient` applies exponential backoff
2. Retries at 2s, 4s, 8s, 16s intervals
3. After 3 failed retries, circuit breaker opens
4. Circuit breaker reopens after 60 seconds

```python
# Exponential backoff example
attempt 1: wait 2 seconds
attempt 2: wait 4 seconds
attempt 3: wait 8 seconds
attempt 4: wait 16 seconds (circuit breaker opens)

# Circuit breaker
opened for 60 seconds
all requests fail immediately (no API calls)
after 60s, try again (if half-open succeeds, close circuit)
```

## Error Handling

### Retry Strategy

| Scenario | Behavior | Retries | Max Delay |
|----------|----------|---------|-----------|
| Timeout | Exponential backoff | 3 | 16 seconds |
| 5xx error | Exponential backoff | 3 | 16 seconds |
| 429 (rate limit) | Exponential backoff | 3 | 16 seconds |
| 401 (auth failure) | Alert + halt worker | 0 | N/A |
| 404 (not found) | Fail immediately | 0 | N/A |
| Connection refused | Exponential backoff | 3 | 16 seconds |

### Circuit Breaker

```python
# Open after N consecutive failures
failure_threshold = 5

# Reset after timeout
reset_timeout = 60 seconds

# States:
# CLOSED -> requests allowed -> OPEN (on failure threshold)
# OPEN -> all requests fail immediately -> HALF_OPEN (after reset_timeout)
# HALF_OPEN -> single test request -> CLOSED (if success) or OPEN (if failure)
```

### Cached FHIR Fallback

If Tasy API is down for extended period:
1. CDC-to-BPM bridge uses cached FHIR data
2. Cache is indexed by patient ID
3. Cache TTL: 24 hours
4. Workers receive stale but consistent data

**Stale Data Marker:**
```json
{
  "resourceType": "Patient",
  "id": "12345",
  "meta": {
    "lastUpdated": "2025-02-09T14:30:00Z"
  },
  "extension": [
    {
      "url": "http://healthcare.austa.local/StructureDefinition/cached-at",
      "valueDateTime": "2025-02-10T10:00:00Z"
    },
    {
      "url": "http://healthcare.austa.local/StructureDefinition/cache-source",
      "valueString": "tasy_fallback"
    }
  ]
}
```

## Observability (ADR-010)

All Tasy integration activities are logged and monitored for visibility and debugging.

### Logging

All API calls include:
- **Correlation ID** (`X-Correlation-ID` header)
- **Tenant ID** (from context)
- **Request/response size**
- **Latency**
- **Status code**

**PII Protection (LGPD Compliance):**
- No patient names in logs
- No CPF/medical record numbers
- No medication details
- Only request IDs and outcomes logged

Example log:
```
{
  "timestamp": "2025-02-10T10:30:45Z",
  "level": "INFO",
  "service": "tasy-integration",
  "operation": "get_patient",
  "correlation_id": "req-12345-abcde",
  "tenant_id": "austa-001",
  "method": "GET",
  "path": "/api/v1/patients/{id}",
  "status_code": 200,
  "latency_ms": 245,
  "request_size": 512,
  "response_size": 4096
}
```

### Metrics (Prometheus)

**Tasy API Client Metrics:**
```
tasy_api_calls_total{
    method="GET",
    endpoint="/api/v1/patients",
    status="200",
    tenant_id="austa-001"
}

tasy_api_errors_total{
    method="GET",
    endpoint="/api/v1/patients",
    error_type="timeout",
    tenant_id="austa-001"
}

tasy_api_latency_seconds{
    method="GET",
    endpoint="/api/v1/patients",
    le="0.1|0.25|0.5|1|2|5"
}

tasy_circuit_breaker_state{
    state="CLOSED|OPEN|HALF_OPEN",
    tenant_id="austa-001"
}
```

**FHIR Adapter Metrics:**
```
tasy_adapter_conversions_total{
    adapter="TasyPatientAdapter",
    resource_type="Patient",
    status="success|failure",
    tenant_id="austa-001"
}

tasy_adapter_errors_total{
    adapter="TasyPatientAdapter",
    error_type="validation_error|mapping_error",
    tenant_id="austa-001"
}

tasy_adapter_latency_seconds{
    adapter="TasyPatientAdapter",
    le="0.1|0.25|0.5|1|2"
}
```

**CDC Fallback Metrics:**
```
cdc_fallback_polls_total{
    table="ATENDIMENTO",
    status="success|failure",
    tenant_id="austa-001"
}

cdc_fallback_lag_seconds{
    table="ATENDIMENTO",
    le="1|5|10|30|60"
}

cdc_fallback_events_produced_total{
    table="ATENDIMENTO",
    tenant_id="austa-001"
}
```

### Grafana Dashboard

Location: `config/observability/grafana/dashboards/tasy-integration.json`

**Panels:**
- API call volume and error rate
- Latency percentiles (p50, p95, p99)
- Circuit breaker state per tenant
- Adapter conversion success rate
- CDC lag and event volume
- Cache hit/miss ratio

## Quick Start for Developers

### Using TasyApiClient (Direct API calls)

```python
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClient, TasyApiSettings
from healthcare_platform.shared.context import TenantContext

# Get settings from Vault (tenant-aware)
tenant_id = TenantContext.get_current_tenant()
settings = TasyApiSettings.from_vault(tenant_id)

# Initialize client (handles auth, rate limiting, retries)
async with TasyApiClient(settings) as client:
    # Get single patient
    patient = await client.get_patient("12345")

    # Get list of encounters (paginated)
    encounters = await client.list_encounters(
        patient_id="12345",
        limit=100,
        offset=0
    )

    # Get vital signs within date range
    vitals = await client.list_vital_signs(
        patient_id="12345",
        start_date="2025-01-01",
        end_date="2025-02-10"
    )
```

### Using FHIR Adapters (Recommended for workers)

Workers should consume FHIR resources, not Tasy directly:

```python
from healthcare_platform.shared.integrations.fhir_client import FHIRClient
from healthcare_platform.shared.context import TenantContext

# Get FHIR client (per tenant)
tenant_id = TenantContext.get_current_tenant()
fhir = FHIRClient(
    base_url="http://fhir:8080/fhir",
    tenant_id=tenant_id
)

# Retrieve FHIR resources
patient = await fhir.get_patient("12345")
encounters = await fhir.search_encounters(
    patient="12345",
    status="finished"
)

# All data is synchronized from Tasy via adapters
# Workers don't need to know about Tasy integration
```

### Using CDCFallbackPoller (Background monitoring)

The poller runs automatically in the background and only activates if CDC is unavailable:

```python
from healthcare_platform.shared.integrations.cdc_fallback_poller import CDCFallbackPoller, KafkaEventSink
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClient
from healthcare_platform.shared.context import TenantContext

# Initialize components
async def start_fallback_poller():
    tenant_id = TenantContext.get_current_tenant()
    settings = TasyApiSettings.from_vault(tenant_id)

    tasy_client = TasyApiClient(settings)
    kafka_sink = KafkaEventSink(
        bootstrap_servers=["kafka:9092"],
        topic_prefix="tasy.AUSTA"
    )

    poller = CDCFallbackPoller(
        tasy_api_client=tasy_client,
        event_sink=kafka_sink,
        cdc_health_check_url="http://debezium:8083/connectors/tasy-connector/status"
    )

    # Start background polling (runs in task)
    await poller.start()

    # ... application runs ...

    # Stop on shutdown
    await poller.stop()
```

### Adding a New Table to CDC

1. **Add to Debezium configuration:**
   ```yaml
   # config/debezium/connectors/tasy-oracle.yaml
   table.include.list: "PACIENTE,CONVENIO,ATENDIMENTO,CONTA_MEDICA,ITEM_CONTA,PRESCRICAO,SINAL_VITAL,NEW_TABLE"
   ```

2. **Create FHIR adapter:**
   ```python
   # healthcare_platform/shared/integrations/tasy_adapters/new_table_adapter.py
   from .base_adapter import BaseTasyAdapter

   class TasyNewTableAdapter(BaseTasyAdapter):
       def __init__(self, fhir_client):
           super().__init__("NEW_TABLE", fhir_client)

       async def adapt(self, tasy_record):
           # Convert Tasy record to FHIR resource
           pass
   ```

3. **Register adapter:**
   ```python
   # healthcare_platform/shared/integrations/tasy_adapters/__init__.py
   from .new_table_adapter import TasyNewTableAdapter

   ADAPTERS = {
       "NEW_TABLE": TasyNewTableAdapter,
       # ...
   }
   ```

4. **Update poller intervals:**
   ```python
   # healthcare_platform/shared/integrations/cdc_fallback_poller.py
   POLLING_INTERVALS = {
       "PACIENTE": 0,              # batch load only
       "ATENDIMENTO": 60,          # 60 seconds
       "NEW_TABLE": 120,           # 120 seconds (configure)
       # ...
   }
   ```

5. **Deploy Debezium connector changes** (restart connectors)

## Related ADRs

- **ADR-004**: Debezium CDC for ERP Integration
- **ADR-005**: HAPI FHIR R4 7.4.0 as Canonical Data Store
- **ADR-006**: Kafka REST Bridge Only
- **ADR-010**: Observability Stack (Prometheus + Grafana)
- **ADR-011**: LGPD History TTL (data retention and PII)

## File Structure

```
healthcare_platform/shared/integrations/
├── __init__.py
├── base.py                          # Base client (circuit breaker, retry, rate limit)
├── fhir_client.py                   # HAPI FHIR R4 client wrapper
├── tasy_client.py                   # Legacy: CDC-only Tasy client
├── tasy_api_client.py               # NEW: Direct Tasy REST API client
├── cdc_fallback_poller.py           # NEW: Polling fallback for CDC downtime
│
└── tasy_adapters/
    ├── __init__.py                  # ADAPTERS registry
    ├── base_adapter.py              # Base class (validation, correlation IDs)
    ├── patient_adapter.py           # PACIENTE -> Patient
    ├── coverage_adapter.py          # CONVENIO_PACIENTE -> Coverage
    ├── encounter_adapter.py         # ATENDIMENTO -> Encounter
    ├── billing_adapter.py           # CONTA_MEDICA + ITEM_CONTA -> Claim
    ├── prescription_adapter.py      # PRESCRICAO -> MedicationRequest
    └── vital_signs_adapter.py       # SINAL_VITAL -> Observation
```

## Troubleshooting

### Symptom: FHIR resources are stale

**Diagnosis:**
- Check CDC lag: `cdc_fallback_lag_seconds` metric
- Check Debezium connector status
- Review Kafka consumer lag

**Solution:**
1. Check if CDC connector is running: `docker logs debezium-connector`
2. Verify Kafka topics exist: `kafka-topics.sh --list`
3. Check for Oracle LogMiner errors in connector logs
4. Restart connector if needed

### Symptom: Rate limit errors (429)

**Diagnosis:**
- Monitor `tasy_api_errors_total{error_type="rate_limit"}`
- Check concurrent request count

**Solution:**
1. Reduce polling interval in CDCFallbackPoller
2. Increase `rate_limit_rps` in TasyApiSettings (if quota allows)
3. Implement request batching to reduce calls
4. Stagger requests across multiple workers

### Symptom: Circuit breaker is open

**Diagnosis:**
- Check `tasy_circuit_breaker_state{state="OPEN"}`
- Review `tasy_api_errors_total` for failure pattern

**Solution:**
1. Verify Tasy API is accessible: `curl https://tasy.austa.local/api/health`
2. Check credentials in Vault (may have expired)
3. Review logs for specific error: `tasy_api_errors_total{error_type="..."}`
4. Wait for circuit breaker reset (60 seconds) and retry

### Symptom: Worker fails with "Patient not found"

**Diagnosis:**
- FHIR resource doesn't exist in FHIR server
- Adapter may have failed silently

**Solution:**
1. Check adapter logs: `tasy_adapter_errors_total`
2. Verify Tasy CDC event was produced to Kafka
3. Check FHIR server health: `http://fhir:8080/fhir/metadata`
4. Verify correlation ID in logs to trace flow
5. Manually trigger sync: `POST /api/v1/admin/sync-tasy/{table-name}`

## Support and Contributing

For questions or issues with Tasy integration:

1. Check ADRs (ADR-004, ADR-005, ADR-006, ADR-010, ADR-011)
2. Review observability dashboards (Grafana)
3. Search logs with correlation ID
4. Contact @platform-team on Slack
5. File issue in healthcare-platform repo

**Contributing:**
- Add adapters for new tables (follow `base_adapter.py` pattern)
- Update observability (add metrics and dashboards)
- Improve error handling (add specific retries)
- Enhance LGPD compliance (audit logs, data retention)
