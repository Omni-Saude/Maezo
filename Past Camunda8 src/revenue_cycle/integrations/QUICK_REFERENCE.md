# Integration Clients - Quick Reference Card

## 🚀 Quick Start (30 seconds)

### TASY Client

```python
from revenue_cycle.integrations.tasy import TasyClient

async with TasyClient(credential_manager, tenant_id) as tasy:
    patient = await tasy.get_patient("12345")
    procedures = await tasy.get_procedures("encounter-123")
```

### TISS Client

```python
from revenue_cycle.integrations.tiss import TissClient

async with TissClient(credential_manager, tenant_id) as tiss:
    response = await tiss.submit_claim(claim_xml)
    status = await tiss.check_claim_status(response.protocol_number)
```

---

## 📋 TASY API Cheat Sheet

| Method | Returns | Use Case |
|--------|---------|----------|
| `get_patient(id)` | `TasyPatientDTO` | Get patient demographics |
| `get_encounter(id)` | `TasyEncounterDTO` | Get encounter details |
| `get_procedures(id)` | `List[TasyProcedureDTO]` | List procedures/services |
| `get_diagnoses(id)` | `List[TasyDiagnosisDTO]` | List diagnoses (CID-10) |
| `get_medical_record(pid, eid)` | `TasyMedicalRecord` | Full medical record for appeals |
| `get_billing_items(id)` | `TasyBillingItemDTO` | Aggregated billing data for TISS |

**Circuit Breaker State:** `tasy.circuit_breaker_state` → `CLOSED`, `OPEN`, or `HALF_OPEN`

---

## 📋 TISS API Cheat Sheet

| Method | Returns | Use Case |
|--------|---------|----------|
| `submit_claim(xml)` | `TissSubmissionResponse` | Submit claim to insurance portal |
| `check_claim_status(protocol)` | `TissStatusResponse` | Check claim status and payment |
| `get_glosas(batch_id)` | `List[TissGlosaDTO]` | Get denials for batch |
| `submit_appeal(request)` | `TissAppealResponse` | Submit appeal with justification |
| `get_batch_summary(batch_id)` | `TissBatchSummary` | Get batch financial summary |

**Certificate Expiration:** `tiss.certificate_expires_in_days` → Days until expiry

---

## 🔥 Common Patterns

### Pattern 1: Fetch and Submit

```python
# 1. Get billing data from TASY
async with TasyClient(cred_mgr, tenant) as tasy:
    billing = await tasy.get_billing_items(encounter_id)

# 2. Submit to TISS
claim_xml = generate_tiss_xml(billing)
async with TissClient(cred_mgr, tenant) as tiss:
    response = await tiss.submit_claim(claim_xml)
```

### Pattern 2: Handle Glosas

```python
async with TissClient(cred_mgr, tenant) as tiss:
    # Get glosas
    glosas = await tiss.get_glosas(batch_id)

    # Submit appeals for appealable glosas
    for glosa in glosas:
        if glosa.is_appealable:
            appeal = TissAppealRequest(
                glosa_id=glosa.glosa_id,
                protocol_number=glosa.protocol_number,
                appeal_reason="Clinical justification",
                clinical_justification="...",
                supporting_documents=["medical_record.pdf"],
                medical_record_summary="...",
                requested_amount=glosa.denied_amount
            )
            await tiss.submit_appeal(appeal)
```

### Pattern 3: Get Evidence for Appeal

```python
async with TasyClient(cred_mgr, tenant) as tasy:
    # Get complete medical record with evidence
    medical_record = await tasy.get_medical_record(
        patient_id="12345",
        encounter_id="encounter-123"
    )

    # Use medical_record data for appeal justification
    clinical_notes = medical_record.evolucao
    diagnoses = medical_record.diagnoses
    procedures = medical_record.procedures
```

---

## ⚠️ Error Handling

### TASY Errors

```python
from revenue_cycle.integrations.tasy import (
    TasyAuthenticationError,  # OAuth failed
    TasyNotFoundError,        # Resource not found (404)
    TasyTimeoutError,         # Request timeout (>30s)
    TasyIntegrationError      # Generic error
)

try:
    patient = await tasy.get_patient("12345")
except TasyNotFoundError:
    # Handle patient not found
    pass
except TasyTimeoutError:
    # Handle timeout
    pass
except TasyAuthenticationError:
    # Handle auth failure
    pass
```

### TISS Errors

```python
from revenue_cycle.integrations.tiss import (
    TissCertificateError,    # Certificate expired/invalid
    TissSubmissionError,     # Claim submission failed
    TissTimeoutError,        # Request timeout (>60s)
    TissIntegrationError     # Generic error
)

try:
    response = await tiss.submit_claim(claim_xml)
except TissCertificateError as e:
    # Handle certificate issue
    if "expired" in str(e):
        # Request new certificate
        pass
```

---

## 🔐 Multi-Tenant Setup

### Initialize Credential Manager

```python
from revenue_cycle.config import Settings
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager

settings = Settings()
cred_mgr = TenantCredentialManager(settings)
await cred_mgr.initialize()
```

### Vault Configuration

```bash
# TASY credentials
vault kv put secret/revenue-cycle/tenants/{tenant_id}/tasy_api \
  username="user" \
  password="pass" \
  base_url="https://tasy.hospital.com/api"

# TISS certificate
vault kv put secret/revenue-cycle/tenants/{tenant_id}/tiss_certificate \
  certificate_pem="$(cat cert.pem)" \
  private_key_pem="$(cat key.pem)" \
  valid_until="2025-12-31T23:59:59Z" \
  issuer="ICP-Brasil"
```

---

## 🎨 DTOs Quick Reference

### TASY DTOs

```python
TasyPatientDTO(
    patient_id="12345",
    cpf="12345678900",
    nome="João Silva",
    data_nascimento=date(1980, 1, 1),
    # ... more fields
)

TasyEncounterDTO(
    encounter_id="enc-123",
    patient_id="12345",
    date_admission=datetime.now(),
    tipo_atendimento="internacao",
    convenio="Unimed",
    # ... more fields
)
```

### TISS DTOs

```python
TissSubmissionResponse(
    protocol_number="ANS-2024-12345",
    batch_id="batch-123",
    submission_date=datetime.now(),
    status="submitted"
)

TissGlosaDTO(
    glosa_id="glosa-456",
    glosa_type="clinical",
    procedure_code="10101012",
    denied_amount=Decimal("150.00"),
    reason_description="Falta justificativa clinica",
    is_appealable=True
)
```

---

## ⚡ Performance Tips

### 1. Parallel Requests

```python
# Fetch multiple resources in parallel
patient, encounter, procedures = await asyncio.gather(
    tasy.get_patient(patient_id),
    tasy.get_encounter(encounter_id),
    tasy.get_procedures(encounter_id)
)
```

### 2. Reuse Client Connections

```python
# Use context manager to reuse connection
async with TasyClient(cred_mgr, tenant) as tasy:
    for encounter_id in encounter_ids:
        billing = await tasy.get_billing_items(encounter_id)
        # Process billing...
```

### 3. Monitor Circuit Breaker

```python
if tasy.circuit_breaker_state == "OPEN":
    logger.warning("TASY circuit breaker is OPEN, service may be down")
    # Use fallback or retry later
```

---

## 📊 Observability

### Structured Logging

```python
import structlog
logger = structlog.get_logger(__name__)

# Logs are automatically structured
# {"event": "TASY client initialized", "tenant_id": "abc-123", ...}
```

### Metrics (Prometheus)

```python
# Metrics are automatically exported
# tasy_requests_total{method="GET", status="200"}
# tiss_certificate_expiry_days
```

---

## 🐛 Debugging

### Enable Debug Logging

```bash
export OBSERVABILITY_LOG_LEVEL=DEBUG
```

### Check Circuit Breaker

```python
state = tasy.circuit_breaker_state
logger.info(f"Circuit breaker state: {state}")
```

### Verify Certificate

```python
days = tiss.certificate_expires_in_days
if days < 30:
    logger.warning(f"Certificate expires in {days} days!")
```

---

## 📚 Full Documentation

- **Complete Guide:** `src/revenue_cycle/integrations/README.md`
- **Examples:** `src/revenue_cycle/integrations/examples/integration_usage.py`
- **Implementation Summary:** `INTEGRATION_CLIENTS_SUMMARY.md`

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| `TasyAuthenticationError` | Check Vault credentials for tenant |
| `TissCertificateError: expired` | Renew ICP-Brasil certificate |
| Circuit breaker OPEN | Wait 60s or check TASY service health |
| Timeout errors | Check network connectivity, increase timeout |
| Vault not available | Check VAULT_ENABLED=true in env |

---

**Quick Links:**
- [TASY Models](tasy/models.py)
- [TASY Client](tasy/client.py)
- [TISS Models](tiss/models.py)
- [TISS Client](tiss/client.py)
