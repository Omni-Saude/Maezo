# Hospital Revenue Cycle - Integration Clients

This directory contains HTTP clients for integrating with external systems in the hospital revenue cycle process.

## 🏥 TASY ERP Integration

**Location:** `tasy/`

The TASY client provides integration with the hospital's TASY ERP system for patient data, encounters, procedures, and medical records.

### Features

- **OAuth Authentication**: Automatic token management with refresh
- **Circuit Breaker**: Prevents cascading failures (5 failures → open for 60s)
- **Retry Logic**: Exponential backoff for network errors (3 attempts)
- **Multi-tenant**: Isolated credentials per tenant via HashiCorp Vault
- **Async Context Manager**: Automatic resource cleanup
- **Structured Logging**: Detailed operational logs with structlog

### Usage

```python
from revenue_cycle.integrations.tasy import TasyClient
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager

async with TasyClient(credential_manager, "tenant-123") as tasy:
    # Get patient data
    patient = await tasy.get_patient("12345")

    # Get encounter
    encounter = await tasy.get_encounter("encounter-67890")

    # Get procedures
    procedures = await tasy.get_procedures("encounter-67890")

    # Get complete medical record for appeals
    medical_record = await tasy.get_medical_record(
        patient_id="12345",
        encounter_id="encounter-67890"
    )

    # Get billing items ready for TISS
    billing = await tasy.get_billing_items("encounter-67890")
```

### Data Models

| Model | Description |
|-------|-------------|
| `TasyPatientDTO` | Patient demographics (CPF, name, DOB, contact) |
| `TasyEncounterDTO` | Encounter details (admission, discharge, type) |
| `TasyProcedureDTO` | Procedure/service data (code, price, quantity) |
| `TasyDiagnosisDTO` | Diagnosis data (CID-10 codes) |
| `TasyMedicalRecord` | Complete medical record for appeals |
| `TasyBillingItemDTO` | Billing data ready for TISS submission |

### Circuit Breaker

The client includes a circuit breaker to prevent overwhelming a failing TASY service:

- **CLOSED**: Normal operation
- **OPEN**: Service failing, requests rejected (after 5 failures)
- **HALF_OPEN**: Testing recovery (after 60s timeout)

Check state with:
```python
state = tasy.circuit_breaker_state
print(f"Circuit breaker: {state}")
```

### Error Handling

| Exception | When Raised |
|-----------|-------------|
| `TasyAuthenticationError` | OAuth authentication failed |
| `TasyNotFoundError` | Resource not found (404) |
| `TasyTimeoutError` | Request timeout (>30s) |
| `TasyIntegrationError` | Generic integration error |

---

## 💳 TISS/ANS Integration

**Location:** `tiss/`

The TISS client provides integration with insurance portals for claim submission, status tracking, and glosa (denial) appeals using ICP-Brasil digital certificates.

### Features

- **ICP-Brasil Certificate**: Secure authentication with digital certificates
- **Certificate Management**: Automatic expiration monitoring (warns at 30 days)
- **Secure Temp Files**: Certificates written to secure temp files (0o600 permissions)
- **XML Submission**: TISS 3.x standard claim submission
- **Retry Logic**: Exponential backoff for network errors (3 attempts)
- **Multi-tenant**: Per-tenant certificates via HashiCorp Vault
- **Async Context Manager**: Automatic cleanup of temp certificate files

### Usage

```python
from revenue_cycle.integrations.tiss import TissClient, TissAppealRequest
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager

async with TissClient(credential_manager, "tenant-123") as tiss:
    # Submit claim
    submission = await tiss.submit_claim(claim_xml)
    print(f"Protocol: {submission.protocol_number}")

    # Check status
    status = await tiss.check_claim_status(submission.protocol_number)
    print(f"Status: {status.status}")
    print(f"Glosas: {status.glosa_count}")

    # Get glosas for batch
    glosas = await tiss.get_glosas(submission.batch_id)
    for glosa in glosas:
        print(f"Glosa: {glosa.reason_description}")
        print(f"Amount: R$ {glosa.denied_amount}")

    # Submit appeal
    if glosas[0].is_appealable:
        appeal = TissAppealRequest(
            glosa_id=glosas[0].glosa_id,
            protocol_number=submission.protocol_number,
            appeal_reason="Clinical justification",
            clinical_justification="Medical necessity documented...",
            supporting_documents=["medical_record.pdf"],
            medical_record_summary="Patient presented with...",
            requested_amount=glosas[0].denied_amount
        )
        appeal_response = await tiss.submit_appeal(appeal)
        print(f"Appeal protocol: {appeal_response.appeal_protocol}")
```

### Data Models

| Model | Description |
|-------|-------------|
| `TissSubmissionResponse` | Claim submission result (protocol, batch ID) |
| `TissStatusResponse` | Current claim status (approved, glosa amounts) |
| `TissGlosaDTO` | Glosa details (type, reason, denied amount) |
| `TissAppealRequest` | Appeal submission data |
| `TissAppealResponse` | Appeal submission result |
| `TissBatchSummary` | Batch summary (total claims, amounts) |
| `TissClaimDTO` | Single claim data structure |

### Certificate Management

The client automatically:
1. Loads ICP-Brasil certificate from Vault
2. Validates certificate not expired
3. Warns if expiring within 30 days
4. Writes cert and key to secure temp files (0o600)
5. Cleans up temp files on close

Check certificate expiration:
```python
days_remaining = tiss.certificate_expires_in_days
if days_remaining < 30:
    print(f"⚠️  Certificate expires in {days_remaining} days!")
```

### Glosa Types

| Type | Description |
|------|-------------|
| `ADMINISTRATIVE` | Documentation issues |
| `TECHNICAL` | Unauthorized procedures |
| `CLINICAL` | Lack of clinical justification |
| `PRICING` | Price discrepancy |

### Error Handling

| Exception | When Raised |
|-----------|-------------|
| `TissCertificateError` | Certificate expired or loading failed |
| `TissSubmissionError` | Claim submission failed |
| `TissTimeoutError` | Request timeout (>60s) |
| `TissIntegrationError` | Generic integration error |

---

## 🔐 Multi-Tenant Credentials

Both clients use `TenantCredentialManager` for secure, isolated credential management:

```python
from revenue_cycle.config import Settings
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager

# Initialize credential manager
settings = Settings()
credential_manager = TenantCredentialManager(settings)
await credential_manager.initialize()

# Credentials are automatically fetched from Vault
# and cached with 5-minute TTL
tasy_creds = await credential_manager.get_tasy_credentials("tenant-123")
tiss_cert = await credential_manager.get_tiss_certificate("tenant-123")
```

Credentials are stored in HashiCorp Vault at:
- TASY: `secret/revenue-cycle/tenants/{tenant_id}/tasy_api`
- TISS: `secret/revenue-cycle/tenants/{tenant_id}/tiss_certificate`

---

## 📊 Integration Flow

### Complete Revenue Cycle Flow

```
1. TASY: Fetch patient, encounter, procedures
   ↓
2. TASY: Get billing items
   ↓
3. Generate TISS XML (standard 3.x)
   ↓
4. TISS: Submit claim
   ↓
5. TISS: Monitor status
   ↓
6. If glosas detected:
   ├─ TASY: Fetch medical record evidence
   ├─ TISS: Submit appeal with documentation
   └─ TISS: Track appeal outcome
```

See `examples/integration_usage.py` for complete examples.

---

## ⚙️ Configuration

### Environment Variables

```bash
# TASY ERP
INTEGRATION_TASY_BASE_URL=https://tasy.hospital.com/api
INTEGRATION_TASY_TIMEOUT=30

# TISS
INTEGRATION_TISS_BASE_URL=https://tiss-portal.insurance.com/api
INTEGRATION_TISS_TIMEOUT=60

# Vault (for credentials)
VAULT_ENABLED=true
VAULT_URL=https://vault.hospital.com:8200
VAULT_TOKEN=s.xxxxxxxxxxxxx
VAULT_MOUNT_POINT=secret
VAULT_PATH_PREFIX=revenue-cycle
```

---

## 🧪 Testing

### Unit Tests

```bash
# Test TASY client
pytest tests/unit/integrations/test_tasy_client.py -v

# Test TISS client
pytest tests/unit/integrations/test_tiss_client.py -v
```

### Integration Tests (with TestContainers)

```bash
# Requires Docker
pytest tests/integration/test_tasy_integration.py -v
pytest tests/integration/test_tiss_integration.py -v
```

### Mock Servers

For local development, use mock servers:

```bash
# TASY mock
docker run -p 8080:8080 hospital/tasy-mock:latest

# TISS mock
docker run -p 8081:8081 hospital/tiss-mock:latest
```

---

## 📈 Observability

Both clients emit structured logs and metrics:

### Logs

```json
{
  "event": "TASY client initialized",
  "tenant_id": "hospital-abc-123",
  "base_url": "https://tasy.hospital.com/api",
  "timestamp": "2024-02-04T12:00:00Z"
}
```

### Metrics (Prometheus)

- `tasy_requests_total{method, status}` - Total TASY requests
- `tasy_request_duration_seconds{method}` - Request latency
- `tasy_circuit_breaker_state{state}` - Circuit breaker state
- `tiss_submissions_total{status}` - Total TISS submissions
- `tiss_glosas_total{type}` - Total glosas by type
- `tiss_certificate_expiry_days` - Days until certificate expires

---

## 🚨 Production Checklist

- [ ] Vault credentials configured for all tenants
- [ ] TISS certificates uploaded and valid (>30 days)
- [ ] TASY OAuth client credentials configured
- [ ] Network connectivity to TASY/TISS verified
- [ ] Circuit breaker thresholds tuned
- [ ] Retry policies configured
- [ ] Monitoring dashboards created
- [ ] Alert rules for certificate expiration
- [ ] Backup credential rotation procedure documented

---

## 📚 References

- [TISS Standard 3.05.00](http://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar)
- [ICP-Brasil Digital Certificates](https://www.gov.br/iti/pt-br/assuntos/icp-brasil)
- [TASY ERP Documentation](https://www.philips.com/healthcare/tasy)
- [HashiCorp Vault](https://www.vaultproject.io/)
- [httpx Documentation](https://www.python-httpx.org/)

---

## 🤝 Support

For issues or questions:
- Internal: #revenue-cycle-integrations
- TASY Support: suporte-tasy@hospital.com
- TISS Support: ans-tiss@insurance.com
