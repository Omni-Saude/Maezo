# TASY REST API Catalog

## Overview

This document catalogs all available TASY ERP REST API endpoints for real-time clinical and billing data access. The TASY API complements the CDC (Change Data Capture) integration by providing synchronous access to ERP data.

**Base URL**: Configured per tenant (e.g., `https://tasy.hospital.com.br/api`)

**API Version**: v1

**Authentication**: OAuth2 Client Credentials OR API Key

**Rate Limiting**: 10 requests/second per tenant (configurable)

**Protocol**: REST over HTTPS

**Response Format**: JSON

---

## Authentication

### Method 1: OAuth2 Client Credentials (Recommended)

TASY supports OAuth2 client credentials flow for machine-to-machine authentication.

**Token Endpoint**: `POST /oauth/token`

**Request**:
```http
POST /oauth/token HTTP/1.1
Host: tasy.hospital.com.br
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "read:patients read:encounters read:billing"
}
```

**Usage**:
```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Token Lifetime**: 3600 seconds (1 hour). Client automatically refreshes 60 seconds before expiry.

### Method 2: API Key

For simpler integrations, TASY supports API key authentication.

**Request Header**:
```http
X-API-Key: your-api-key-here
```

**Note**: API keys do not expire but should be rotated quarterly per security policy.

---

## Common Headers

All requests must include:

| Header | Required | Description | Example |
|--------|----------|-------------|---------|
| `Authorization` | Yes (OAuth2) | Bearer token | `Bearer eyJ...` |
| `X-API-Key` | Yes (API Key) | API key for authentication | `abc123...` |
| `X-Correlation-ID` | Yes | Request tracing ID | `7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e` |
| `X-Tenant-ID` | Yes | Tenant identifier | `hospital-saopaulo` |
| `Accept` | Yes | Response format | `application/json` |
| `Content-Type` | Yes (POST/PUT) | Request body format | `application/json` |

---

## Rate Limiting

**Default Limit**: 10 requests/second per tenant

**Rate Limit Headers** (included in all responses):
```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1609459200
```

**Exceeded Rate Limit Response**:
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 1

{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please retry after 1 second.",
  "retry_after_seconds": 1
}
```

**Client Behavior**: The `TasyApiClient` uses token bucket rate limiting to prevent exceeding limits.

---

## Error Handling

### Standard Error Response

All API errors follow this format:

```json
{
  "error": "error_code",
  "message": "Human-readable error description in Portuguese",
  "details": {
    "field": "patient_id",
    "reason": "Patient ID must be numeric"
  },
  "timestamp": "2025-01-15T14:30:00Z",
  "trace_id": "7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e"
}
```

### HTTP Status Codes

| Code | Meaning | Retryable | Description |
|------|---------|-----------|-------------|
| 200 | OK | N/A | Request succeeded |
| 201 | Created | N/A | Resource created successfully |
| 400 | Bad Request | No | Invalid request parameters |
| 401 | Unauthorized | No | Missing or invalid authentication |
| 403 | Forbidden | No | Insufficient permissions |
| 404 | Not Found | No | Resource does not exist |
| 429 | Too Many Requests | Yes | Rate limit exceeded |
| 500 | Internal Server Error | Yes | TASY server error |
| 502 | Bad Gateway | Yes | TASY service unavailable |
| 503 | Service Unavailable | Yes | TASY temporarily unavailable |
| 504 | Gateway Timeout | Yes | TASY request timeout |

### Common Error Codes

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| `invalid_request` | 400 | Malformed request or missing required fields |
| `authentication_failed` | 401 | Invalid credentials or expired token |
| `authorization_failed` | 403 | User lacks permission for this operation |
| `resource_not_found` | 404 | Requested resource does not exist |
| `rate_limit_exceeded` | 429 | Too many requests |
| `internal_error` | 500 | TASY server error |
| `database_error` | 500 | TASY database connection error |
| `timeout` | 504 | Request took too long |

---

## API Endpoints

### 1. Patient Management

#### 1.1 Get Patient by ID

**Endpoint**: `GET /api/v1/patients/{id}`

**Description**: Retrieve a single patient record by TASY patient ID.

**TASY Table**: `PACIENTE`

**FHIR Resource**: `Patient`

**Rate Limit**: 10 req/s

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | TASY patient ID (numeric) |

**Request Example**:
```http
GET /api/v1/patients/12345 HTTP/1.1
Host: tasy.hospital.com.br
Authorization: Bearer eyJ...
X-Correlation-ID: 7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e
X-Tenant-ID: hospital-saopaulo
Accept: application/json
```

**Response Example** (200 OK):
```json
{
  "id": "12345",
  "mrn": "MRN-2024-001234",
  "cpf": "123.456.789-00",
  "name": "João Silva",
  "birth_date": "1980-05-15",
  "gender": "M",
  "phone": "+55 11 98765-4321",
  "email": "joao.silva@example.com",
  "address": {
    "street": "Rua Example",
    "number": "123",
    "complement": "Apto 45",
    "district": "Centro",
    "city": "São Paulo",
    "state": "SP",
    "postal_code": "01234-567"
  },
  "active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-20T14:15:00Z"
}
```

**Error Responses**:
- `404 Not Found`: Patient ID does not exist
- `401 Unauthorized`: Invalid or missing authentication

---

#### 1.2 Search Patients

**Endpoint**: `GET /api/v1/patients`

**Description**: Search for patients by MRN or CPF.

**TASY Table**: `PACIENTE`

**FHIR Resource**: `Patient`

**Rate Limit**: 10 req/s

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mrn` | string | No* | Medical record number |
| `cpf` | string | No* | Brazilian tax ID (CPF) |
| `limit` | integer | No | Max results (default: 50, max: 100) |
| `offset` | integer | No | Pagination offset (default: 0) |

*At least one of `mrn` or `cpf` is required.

**Request Example**:
```http
GET /api/v1/patients?mrn=MRN-2024-001234 HTTP/1.1
Host: tasy.hospital.com.br
Authorization: Bearer eyJ...
X-Correlation-ID: 7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e
X-Tenant-ID: hospital-saopaulo
Accept: application/json
```

**Response Example** (200 OK):
```json
{
  "results": [
    {
      "id": "12345",
      "mrn": "MRN-2024-001234",
      "cpf": "123.456.789-00",
      "name": "João Silva",
      "birth_date": "1980-05-15",
      "gender": "M",
      "active": true
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

---

#### 1.3 Get Patient Coverage

**Endpoint**: `GET /api/v1/patients/{id}/coverages`

**Description**: Get all insurance coverage (convênios) for a patient.

**TASY Table**: `CONVENIO_PACIENTE`

**FHIR Resource**: `Coverage`

**Rate Limit**: 10 req/s

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | TASY patient ID |

**Request Example**:
```http
GET /api/v1/patients/12345/coverages HTTP/1.1
Host: tasy.hospital.com.br
Authorization: Bearer eyJ...
X-Correlation-ID: 7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e
X-Tenant-ID: hospital-saopaulo
Accept: application/json
```

**Response Example** (200 OK):
```json
{
  "coverages": [
    {
      "id": "COV-789",
      "patient_id": "12345",
      "payer_id": "PAYER-456",
      "payer_name": "Unimed São Paulo",
      "plan_name": "Plano 500 Enfermaria",
      "member_id": "123456789012345",
      "status": "active",
      "valid_from": "2024-01-01",
      "valid_until": "2024-12-31",
      "contract_id": "CONTRACT-999"
    }
  ],
  "total": 1
}
```

---

### 2. Encounter Management

#### 2.1 Get Encounter by ID

**Endpoint**: `GET /api/v1/encounters/{id}`

**Description**: Retrieve a single encounter (atendimento) by ID.

**TASY Table**: `ATENDIMENTO`

**FHIR Resource**: `Encounter`

**Rate Limit**: 10 req/s

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | TASY encounter ID |

**Request Example**:
```http
GET /api/v1/encounters/67890 HTTP/1.1
Host: tasy.hospital.com.br
Authorization: Bearer eyJ...
X-Correlation-ID: 7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e
X-Tenant-ID: hospital-saopaulo
Accept: application/json
```

**Response Example** (200 OK):
```json
{
  "id": "67890",
  "patient_id": "12345",
  "encounter_type": "emergency",
  "status": "in-progress",
  "admission_date": "2025-01-15T08:30:00Z",
  "discharge_date": null,
  "attending_physician": {
    "id": "DOC-123",
    "name": "Dr. Maria Santos",
    "specialty": "Cardiologia"
  },
  "department": "Emergency Department",
  "location": {
    "building": "Main Hospital",
    "floor": "2",
    "room": "205"
  },
  "payer_id": "PAYER-456",
  "created_at": "2025-01-15T08:30:00Z",
  "updated_at": "2025-01-15T14:15:00Z"
}
```

---

#### 2.2 Search Encounters

**Endpoint**: `GET /api/v1/encounters`

**Description**: Search encounters for a patient.

**TASY Table**: `ATENDIMENTO`

**FHIR Resource**: `Encounter`

**Rate Limit**: 10 req/s

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `patient` | string | Yes | TASY patient ID |
| `status` | string | No | Filter by status: `planned`, `in-progress`, `finished`, `cancelled` |
| `from_date` | date | No | Start date (ISO 8601: YYYY-MM-DD) |
| `to_date` | date | No | End date (ISO 8601: YYYY-MM-DD) |
| `limit` | integer | No | Max results (default: 50, max: 100) |
| `offset` | integer | No | Pagination offset |

**Request Example**:
```http
GET /api/v1/encounters?patient=12345&status=in-progress HTTP/1.1
Host: tasy.hospital.com.br
Authorization: Bearer eyJ...
X-Correlation-ID: 7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e
X-Tenant-ID: hospital-saopaulo
Accept: application/json
```

**Response Example** (200 OK):
```json
{
  "results": [
    {
      "id": "67890",
      "patient_id": "12345",
      "encounter_type": "emergency",
      "status": "in-progress",
      "admission_date": "2025-01-15T08:30:00Z",
      "discharge_date": null,
      "department": "Emergency Department"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

---

### 3. Billing Management

#### 3.1 Get Billing Account

**Endpoint**: `GET /api/v1/billing/accounts/{id}`

**Description**: Retrieve a billing account (conta médica).

**TASY Table**: `CONTA_MEDICA`

**FHIR Resource**: `Claim`

**Rate Limit**: 10 req/s

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | TASY billing account ID |

**Request Example**:
```http
GET /api/v1/billing/accounts/ACC-9876 HTTP/1.1
Host: tasy.hospital.com.br
Authorization: Bearer eyJ...
X-Correlation-ID: 7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e
X-Tenant-ID: hospital-saopaulo
Accept: application/json
```

**Response Example** (200 OK):
```json
{
  "id": "ACC-9876",
  "patient_id": "12345",
  "encounter_id": "67890",
  "payer_id": "PAYER-456",
  "status": "pending",
  "total_amount": 15000.00,
  "currency": "BRL",
  "created_date": "2025-01-15T09:00:00Z",
  "submission_date": null,
  "payment_date": null,
  "billing_period": {
    "start": "2025-01-15",
    "end": "2025-01-20"
  }
}
```

---

#### 3.2 Get Billing Items

**Endpoint**: `GET /api/v1/billing/accounts/{id}/items`

**Description**: Retrieve all line items for a billing account.

**TASY Table**: `ITEM_CONTA`

**FHIR Resource**: `Claim.item`

**Rate Limit**: 10 req/s

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | TASY billing account ID |

**Request Example**:
```http
GET /api/v1/billing/accounts/ACC-9876/items HTTP/1.1
Host: tasy.hospital.com.br
Authorization: Bearer eyJ...
X-Correlation-ID: 7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e
X-Tenant-ID: hospital-saopaulo
Accept: application/json
```

**Response Example** (200 OK):
```json
{
  "items": [
    {
      "id": "ITEM-001",
      "account_id": "ACC-9876",
      "sequence": 1,
      "procedure_code": "40301010",
      "procedure_name": "Consulta médica em consultório",
      "quantity": 1,
      "unit_price": 250.00,
      "total_price": 250.00,
      "service_date": "2025-01-15",
      "provider": {
        "id": "DOC-123",
        "name": "Dr. Maria Santos"
      },
      "status": "pending"
    },
    {
      "id": "ITEM-002",
      "account_id": "ACC-9876",
      "sequence": 2,
      "procedure_code": "20104014",
      "procedure_name": "Eletrocardiograma",
      "quantity": 1,
      "unit_price": 80.00,
      "total_price": 80.00,
      "service_date": "2025-01-15",
      "status": "pending"
    }
  ],
  "total": 2,
  "total_amount": 330.00
}
```

---

### 4. Clinical Data

#### 4.1 Get Prescription

**Endpoint**: `GET /api/v1/prescriptions/{id}`

**Description**: Retrieve a prescription (prescrição médica).

**TASY Table**: `PRESCRICAO`

**FHIR Resource**: `MedicationRequest`

**Rate Limit**: 10 req/s

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | TASY prescription ID |

**Request Example**:
```http
GET /api/v1/prescriptions/RX-5678 HTTP/1.1
Host: tasy.hospital.com.br
Authorization: Bearer eyJ...
X-Correlation-ID: 7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e
X-Tenant-ID: hospital-saopaulo
Accept: application/json
```

**Response Example** (200 OK):
```json
{
  "id": "RX-5678",
  "patient_id": "12345",
  "encounter_id": "67890",
  "prescriber": {
    "id": "DOC-123",
    "name": "Dr. Maria Santos",
    "crm": "123456-SP"
  },
  "status": "active",
  "prescribed_date": "2025-01-15T10:00:00Z",
  "medications": [
    {
      "medication_code": "MED-789",
      "medication_name": "Amoxicilina 500mg",
      "dosage": "500mg",
      "route": "oral",
      "frequency": "8/8 horas",
      "duration_days": 7,
      "quantity": 21,
      "instructions": "Tomar com água, após as refeições"
    }
  ]
}
```

---

#### 4.2 Get Vital Signs

**Endpoint**: `GET /api/v1/encounters/{id}/vitals`

**Description**: Retrieve vital signs for an encounter.

**TASY Table**: `SINAL_VITAL`

**FHIR Resource**: `Observation` (vital-signs category)

**Rate Limit**: 10 req/s

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | TASY encounter ID |

**Request Example**:
```http
GET /api/v1/encounters/67890/vitals HTTP/1.1
Host: tasy.hospital.com.br
Authorization: Bearer eyJ...
X-Correlation-ID: 7d4c2a1b-3e5f-4a2c-9d1e-2f3a4b5c6d7e
X-Tenant-ID: hospital-saopaulo
Accept: application/json
```

**Response Example** (200 OK):
```json
{
  "vitals": [
    {
      "id": "VITAL-001",
      "encounter_id": "67890",
      "observation_date": "2025-01-15T09:00:00Z",
      "measurements": [
        {
          "code": "8867-4",
          "display": "Heart rate",
          "value": 78,
          "unit": "bpm"
        },
        {
          "code": "85354-9",
          "display": "Blood pressure",
          "systolic": 120,
          "diastolic": 80,
          "unit": "mmHg"
        },
        {
          "code": "8310-5",
          "display": "Body temperature",
          "value": 36.7,
          "unit": "Cel"
        },
        {
          "code": "9279-1",
          "display": "Respiratory rate",
          "value": 16,
          "unit": "/min"
        },
        {
          "code": "2708-6",
          "display": "Oxygen saturation",
          "value": 98,
          "unit": "%"
        }
      ],
      "recorded_by": {
        "id": "NURSE-456",
        "name": "Enfermeira Ana Costa"
      }
    }
  ],
  "total": 1
}
```

---

## Complete Endpoint Summary

| Endpoint | Method | TASY Table | FHIR Resource | Rate Limit | Description |
|----------|--------|------------|---------------|------------|-------------|
| `/api/v1/patients/{id}` | GET | `PACIENTE` | Patient | 10 req/s | Get patient by ID |
| `/api/v1/patients` | GET | `PACIENTE` | Patient | 10 req/s | Search patients by MRN/CPF |
| `/api/v1/patients/{id}/coverages` | GET | `CONVENIO_PACIENTE` | Coverage | 10 req/s | Get patient insurance coverage |
| `/api/v1/encounters/{id}` | GET | `ATENDIMENTO` | Encounter | 10 req/s | Get encounter by ID |
| `/api/v1/encounters` | GET | `ATENDIMENTO` | Encounter | 10 req/s | Search encounters by patient |
| `/api/v1/billing/accounts/{id}` | GET | `CONTA_MEDICA` | Claim | 10 req/s | Get billing account |
| `/api/v1/billing/accounts/{id}/items` | GET | `ITEM_CONTA` | Claim.item | 10 req/s | Get billing line items |
| `/api/v1/prescriptions/{id}` | GET | `PRESCRICAO` | MedicationRequest | 10 req/s | Get prescription |
| `/api/v1/encounters/{id}/vitals` | GET | `SINAL_VITAL` | Observation | 10 req/s | Get vital signs |

---

## Best Practices

### 1. Error Handling

Always check HTTP status codes and handle errors gracefully:

```python
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClient
from healthcare_platform.shared.domain.exceptions import ExternalServiceException

async def get_patient_safely(client: TasyApiClient, patient_id: str):
    try:
        patient = await client.get_patient(patient_id)
        return patient
    except ExternalServiceException as exc:
        if exc.status_code == 404:
            # Patient not found - handle gracefully
            logger.warning("Patient not found", patient_id=patient_id)
            return None
        elif exc.status_code == 429:
            # Rate limit - retry with backoff
            logger.warning("Rate limit exceeded, will retry")
            raise
        else:
            # Other errors - log and re-raise
            logger.error("TASY API error", error=str(exc))
            raise
```

### 2. Rate Limiting

The client automatically handles rate limiting via token bucket algorithm. No manual rate limiting code needed.

### 3. Correlation IDs

Always propagate correlation IDs for distributed tracing. The client automatically includes `X-Correlation-ID` from the current context.

### 4. Multi-Tenancy

Ensure `TenantContext` is set before making API calls. The client includes `X-Tenant-ID` header automatically.

```python
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant

# Set tenant context
tenant = TenantContext(tenant_id="hospital-saopaulo", ...)
set_current_tenant(tenant)

# Now all API calls include X-Tenant-ID: hospital-saopaulo
patient = await client.get_patient("12345")
```

### 5. Circuit Breaker

The client inherits circuit breaker from `BaseIntegrationClient`. If TASY becomes unavailable:
- After 5 consecutive failures, circuit opens
- Requests fail-fast for 60 seconds (configurable)
- After timeout, circuit enters half-open state
- One successful request closes the circuit

### 6. Metrics

All operations automatically emit Prometheus metrics:
- `tasy_api_calls_total` - Total API calls
- `tasy_api_errors_total` - Total errors
- `tasy_api_latency_seconds` - Request latency histogram
- `tasy_sync_lag_seconds` - Data staleness gauge

### 7. Logging

All logs are LGPD-compliant with PII redaction:
- Patient IDs are logged as `[REDACTED]`
- CPF/MRN are never logged
- Only aggregate metrics are logged

---

## Configuration

### Environment Variables

```bash
# TASY API Base URL
TASY_API_BASE_URL=https://tasy.hospital.com.br

# Authentication Method (oauth2 or api_key)
TASY_AUTH_TYPE=oauth2

# OAuth2 Settings
TASY_CLIENT_ID=your-client-id
TASY_CLIENT_SECRET=your-client-secret
TASY_TOKEN_URL=https://tasy.hospital.com.br/oauth/token

# API Key (if using api_key auth)
TASY_API_KEY=your-api-key

# Rate Limiting
TASY_RATE_LIMIT_RPS=10.0

# Timeouts
TASY_TIMEOUT_SECONDS=30.0
TASY_MAX_RETRIES=3

# Circuit Breaker
TASY_CIRCUIT_BREAKER_THRESHOLD=5
TASY_CIRCUIT_BREAKER_TIMEOUT=60.0
```

### Python Configuration

```python
from healthcare_platform.shared.integrations.tasy_api_client import (
    TasyApiClient,
    TasyApiSettings,
)

# Create settings
settings = TasyApiSettings(
    base_url="https://tasy.hospital.com.br",
    auth_type="oauth2",
    client_id="your-client-id",
    client_secret="your-client-secret",
    token_url="https://tasy.hospital.com.br/oauth/token",
    rate_limit_rps=10.0,
    timeout_seconds=30.0,
    max_retries=3,
)

# Create and initialize client
client = TasyApiClient(settings)
await client.initialize()

# Use client
patient = await client.get_patient("12345")

# Close when done
await client.close()
```

### Context Manager Usage (Recommended)

```python
async with TasyApiClient(settings) as client:
    patient = await client.get_patient("12345")
    encounters = await client.search_encounters(patient["id"])
    # Client automatically closes on exit
```

---

## Monitoring

### Prometheus Metrics

Monitor TASY API integration health:

```promql
# Request rate by endpoint
rate(tasy_api_calls_total[5m])

# Error rate
rate(tasy_api_errors_total[5m]) / rate(tasy_api_calls_total[5m])

# P95 latency
histogram_quantile(0.95, rate(tasy_api_latency_seconds_bucket[5m]))

# Data staleness
max(tasy_sync_lag_seconds) by (table_name)
```

### Alerting Rules

```yaml
groups:
  - name: tasy_api
    rules:
      - alert: TasyApiHighErrorRate
        expr: |
          rate(tasy_api_errors_total[5m]) / rate(tasy_api_calls_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "TASY API error rate above 5%"

      - alert: TasyApiHighLatency
        expr: |
          histogram_quantile(0.95, rate(tasy_api_latency_seconds_bucket[5m])) > 5
        for: 5m
        annotations:
          summary: "TASY API P95 latency above 5 seconds"

      - alert: TasyDataStale
        expr: |
          tasy_sync_lag_seconds > 300
        for: 10m
        annotations:
          summary: "TASY data is stale (>5 minutes old)"
```

---

## Testing

### Unit Testing with Stub Client

```python
from healthcare_platform.shared.integrations.tasy_api_client import StubTasyApiClient

async def test_patient_retrieval():
    # Create stub client
    stub = StubTasyApiClient()

    # Add test data
    stub.add_patient("12345", {
        "id": "12345",
        "mrn": "MRN-TEST-001",
        "name": "Test Patient",
        "birth_date": "1980-01-01",
    })

    # Test
    patient = await stub.get_patient("12345")
    assert patient["mrn"] == "MRN-TEST-001"
```

---

## Support

**Documentation**: This file

**API Support**: api-support@hospital.com.br

**Technical Issues**: Open a ticket in JIRA (project: TASY-INTEGRATION)

**Emergency**: Contact on-call engineer via PagerDuty

---

**Document Version**: 1.0

**Last Updated**: 2025-02-10

**Maintained By**: Integration Team
