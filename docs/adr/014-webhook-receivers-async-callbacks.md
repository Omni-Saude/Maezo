# ADR-014: Webhook Receivers for Async Callbacks

**Status:** Accepted
**Date:** 2026-02-10
**Implemented:** 2026-02-16
**Deciders:** Tech Lead, Integration Lead, Architecture Team

## Context

The platform integrates with external systems that use asynchronous callback patterns. Unlike CDC-based integration (ADR-004) where we consume database changes, several external systems require **us to expose HTTP endpoints** they can call:

| System | Callback Type | Use Case |
|--------|--------------|----------|
| **TASY TIE** | Regulatory callbacks | APAC/CNES/SUS submission results |
| **TASY TIE** | Authorization callbacks | Insurance auth async responses |
| **Banco Central** | PIX notifications | Payment confirmation, refunds |
| **Meta** | WhatsApp webhook | Inbound messages, delivery receipts |
| **Payers (ANS)** | TISS responses | Claim adjudication results |

The TASY Gap Analysis (Wave 2.5) identified 16 regulatory endpoints using Push+Callback pattern:

```
Submit → POST /api/apacReport (we call TASY)
Success → POST /callback/apacReport/success (TASY calls us)
Error → POST /callback/apacReport/error (TASY calls us)
```

Currently, no infrastructure exists to receive these callbacks. GAP-06 blocks regulatory submission workflows.

### Architectural Constraints

Per existing ADRs:
- **ADR-003:** Workers are REST consumers, not providers
- **ADR-005:** HAPI FHIR is the canonical data store (not custom APIs)
- **ADR-006:** Workers don't consume Kafka directly; bridge translates events

Webhook receivers must integrate with these constraints — they are **not** domain APIs, but thin translation layers that feed the BPM engine.

## Decision

We will create a **webhook receiver service** as a separate deployable that:

1. Exposes HTTP endpoints for external system callbacks
2. Validates signatures/authentication per external system requirements
3. Transforms payloads into BPM correlation messages
4. Calls CIB Seven REST API to correlate or start process instances
5. Contains **zero business logic** — all logic remains in BPMN/DMN/workers

### Location in Monorepo

```text
healthcare_platform/shared/
├── integrations/           # OUTBOUND: We call external systems (existing)
│   ├── tasy_api_client.py
│   ├── fhir_client.py
│   └── ...
│
└── webhooks/               # INBOUND: External systems call us (NEW)
    ├── __init__.py
    ├── app.py              # FastAPI application entry point
    ├── config.py           # Webhook configuration
    ├── security/
    │   ├── __init__.py
    │   ├── signature_validator.py   # HMAC/RSA signature validation
    │   └── idempotency.py           # Idempotency key tracking (Redis)
    ├── models/
    │   ├── __init__.py
    │   └── callback_payloads.py     # Pydantic models for payloads
    ├── handlers/
    │   ├── __init__.py
    │   ├── base_handler.py          # Abstract handler with BPM correlation
    │   ├── tasy_regulatory.py       # APAC, CNES, SUS callbacks
    │   ├── tasy_authorization.py    # Insurance auth callbacks
    │   ├── pix_payment.py           # Banco Central PIX notifications
    │   ├── whatsapp_message.py      # Meta WhatsApp webhook
    │   └── tiss_response.py         # ANS payer responses
    └── tests/
        ├── __init__.py
        ├── test_tasy_regulatory.py
        └── test_pix_payment.py
```

### Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Framework** | FastAPI 0.109+ | Async, OpenAPI docs, Pydantic validation, team familiarity |
| **Idempotency** | Redis | Already in stack (docker-compose), sub-ms lookups |
| **Deployment** | Kubernetes (integration namespace) | Alongside cdc-to-bpm-bridge |
| **Observability** | OpenTelemetry → Tempo/Grafana | Trace correlation with BPM engine |

### Webhook → BPM Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ External System (TASY, PIX, WhatsApp, Payer)                        │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP POST /webhooks/{type}/{event}
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Webhook Receiver Service (FastAPI)                                   │
│                                                                       │
│  1. Validate signature (HMAC-SHA256 or RSA per system)               │
│  2. Check idempotency key (Redis) → reject duplicates                │
│  3. Parse & validate payload (Pydantic)                              │
│  4. Extract correlation keys (e.g., encounter_id, transaction_id)    │
│  5. Call CIB Seven REST API:                                         │
│     - POST /message/{messageName} (correlate waiting process)        │
│     - OR POST /process-definition/key/{key}/start (new process)      │
│  6. Store idempotency key (TTL: 7 days)                              │
│  7. Return 200 OK (or 202 Accepted for async)                        │
│                                                                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ CIB Seven Engine                                                     │
│                                                                       │
│  Process Instance waiting on Message Intermediate Catch Event        │
│  correlates and continues execution                                  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Endpoint Structure

All webhook endpoints follow this pattern:

```
POST /webhooks/{system}/{event_type}
```

| Endpoint | System | Handler |
|----------|--------|---------|
| `/webhooks/tasy/regulatory/apac/success` | TASY TIE | `tasy_regulatory.py` |
| `/webhooks/tasy/regulatory/apac/error` | TASY TIE | `tasy_regulatory.py` |
| `/webhooks/tasy/authorization/approved` | TASY TIE | `tasy_authorization.py` |
| `/webhooks/tasy/authorization/denied` | TASY TIE | `tasy_authorization.py` |
| `/webhooks/pix/payment/confirmed` | Banco Central | `pix_payment.py` |
| `/webhooks/pix/payment/refunded` | Banco Central | `pix_payment.py` |
| `/webhooks/whatsapp/message` | Meta | `whatsapp_message.py` |
| `/webhooks/payer/tiss/response` | ANS Payers | `tiss_response.py` |

### Security Requirements

| System | Auth Method | Validation |
|--------|-------------|------------|
| **TASY TIE** | HMAC-SHA256 | Header `X-TASY-Signature` with shared secret |
| **Banco Central PIX** | mTLS + RSA | Client certificate + signed payload |
| **Meta WhatsApp** | HMAC-SHA256 | Header `X-Hub-Signature-256` |
| **Payers (TISS)** | API Key | Header `X-ANS-API-Key` per payer |

All signatures must be validated **before** processing. Failed validation returns `401 Unauthorized`.

### Idempotency

External systems may retry callbacks. The service must:

1. Extract idempotency key from payload (e.g., `transaction_id`, `message_id`)
2. Check Redis: `webhook:idempotency:{system}:{key}`
3. If exists → return cached response (200 OK), don't re-correlate
4. If not exists → process, then store with 7-day TTL

### Correlation Key Mapping

Webhooks must map external identifiers to BPM correlation keys:

```python
# Example: TASY regulatory callback
class TasyRegulatoryHandler(BaseHandler):
    async def handle_apac_success(self, payload: APACSuccessPayload):
        await self.correlate_message(
            message_name="MSG_APAC_SUBMISSION_RESULT",
            correlation_keys={
                "encounter_id": payload.nr_atendimento,
                "submission_id": payload.protocolo_apac
            },
            variables={
                "apac_status": "APPROVED",
                "apac_protocol": payload.protocolo_apac,
                "approval_date": payload.dt_autorizacao
            }
        )
```

### Configuration

```yaml
# config/webhooks.yaml
webhooks:
  tasy:
    enabled: true
    base_path: /webhooks/tasy
    signature_secret: ${TASY_WEBHOOK_SECRET}
    signature_header: X-TASY-Signature
    
  pix:
    enabled: true
    base_path: /webhooks/pix
    mtls_enabled: true
    client_cert_path: /certs/bcb-client.pem
    
  whatsapp:
    enabled: true
    base_path: /webhooks/whatsapp
    verify_token: ${WHATSAPP_VERIFY_TOKEN}
    app_secret: ${WHATSAPP_APP_SECRET}
    
  payer:
    enabled: true
    base_path: /webhooks/payer
    api_keys:
      unimed: ${UNIMED_API_KEY}
      bradesco_saude: ${BRADESCO_SAUDE_API_KEY}

idempotency:
  redis_url: ${REDIS_URL}
  ttl_days: 7
  key_prefix: "webhook:idempotency"

bpm:
  engine_url: ${CIB_SEVEN_URL}
  auth:
    type: basic
    username: ${CIB7_USER}
    password: ${CIB7_PASSWORD}
```

### Deployment

```yaml
# Kubernetes deployment in integration namespace
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webhook-receiver
  namespace: integration
spec:
  replicas: 2  # HA for callback reliability
  selector:
    matchLabels:
      app: webhook-receiver
  template:
    spec:
      containers:
        - name: webhook-receiver
          image: austa/webhook-receiver:latest
          ports:
            - containerPort: 8080
          env:
            - name: CIB_SEVEN_URL
              value: "http://cib-seven.bpm.svc:8080/engine-rest"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: webhook-receiver
  namespace: integration
spec:
  ports:
    - port: 8080
      targetPort: 8080
  selector:
    app: webhook-receiver
---
# Ingress for external access
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: webhook-receiver
  namespace: integration
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
    - hosts:
        - webhooks.austa.health
      secretName: webhook-tls
  rules:
    - host: webhooks.austa.health
      http:
        paths:
          - path: /webhooks
            pathType: Prefix
            backend:
              service:
                name: webhook-receiver
                port:
                  number: 8080
```

## Consequences

### Positive

- **Unblocks GAP-06:** Regulatory async callbacks can now be received
- **Unblocks PIX integration:** Real-time payment confirmations flow into BPM
- **Consistent pattern:** All external callbacks handled uniformly
- **Zero business logic:** Maintains ADR-003 principle — logic stays in workers/DMN
- **Auditable:** All callbacks logged with trace IDs, correlate with BPM execution
- **Idempotent:** Duplicate callbacks safely ignored

### Negative

- **New deployable:** One more service to maintain. *Mitigation:* Simple stateless service, minimal dependencies.
- **External exposure:** Attack surface increases. *Mitigation:* Signature validation mandatory, WAF in front, rate limiting.
- **Callback URL registration:** Must register webhook URLs with each external system. *Mitigation:* Document in runbooks.

### Neutral

- Adds dependency on Redis for idempotency. Redis already in stack for caching.
- Requer credenciais Basic Auth (CIB7_USER/CIB7_PASSWORD) para acesso ao BPM engine.

## Alternatives Considered

### 1. Workers Expose Webhooks Directly

Rejected. Violates ADR-003 (workers are consumers only). Would require each worker to run an HTTP server, complicating scaling and deployment.

### 2. Kafka as Webhook Target

Some systems support publishing to Kafka instead of HTTP. Considered but:
- Not all systems support it (WhatsApp, Banco Central require HTTP)
- Would fragment integration patterns (some Kafka, some HTTP)
- CDC bridge already handles Kafka → BPM translation

### 3. API Gateway Handles Transformation

Use Kong/Ambassador to validate signatures and transform payloads. Rejected:
- Transformation logic too complex for gateway config
- Correlation key extraction requires business knowledge
- Testing/debugging harder in gateway config vs Python code

## Implementation Plan

| Phase | Scope | Duration |
|-------|-------|----------|
| **Phase 1** | Base infrastructure: FastAPI app, security module, idempotency, base handler | 1 week |
| **Phase 2** | TASY regulatory callbacks (APAC, CNES, SUS) | 1 week |
| **Phase 3** | TASY authorization callbacks | 3 days |
| **Phase 4** | PIX payment notifications | 1 week |
| **Phase 5** | WhatsApp webhook (if Node.js worker not chosen per ADR-003) | 3 days |
| **Phase 6** | Payer TISS responses | 1 week |

## References

- ADR-003: Python External Task Workers
- ADR-004: Debezium CDC for ERP Integration
- ADR-005: HAPI FHIR R4 as Canonical Data Store
- ADR-006: Kafka REST Bridge Only
- TASY Gap Analysis: `docs/integrations/TASY_GAP_ANALYSIS.md` (GAP-06)
- Message Event Catalog: `docs/MESSAGE_EVENT_CATALOG.md`

---

## Appendix A: Base Handler Implementation

```python
# healthcare_platform/shared/webhooks/handlers/base_handler.py

from abc import ABC, abstractmethod
from typing import Dict, Any
import httpx
from opentelemetry import trace

from ..config import settings
from ..security.idempotency import IdempotencyStore

tracer = trace.get_tracer(__name__)

class BaseHandler(ABC):
    """Base class for all webhook handlers."""
    
    def __init__(self):
        self.bpm_client = httpx.AsyncClient(
            base_url=settings.bpm.engine_url,
            headers={"Authorization": f"Bearer {self._get_token()}"}
        )
        self.idempotency = IdempotencyStore()
    
    async def correlate_message(
        self,
        message_name: str,
        correlation_keys: Dict[str, Any],
        variables: Dict[str, Any],
        business_key: str = None
    ):
        """Correlate a message to a waiting process instance."""
        with tracer.start_as_current_span("correlate_message") as span:
            span.set_attribute("message.name", message_name)
            span.set_attribute("correlation.keys", str(correlation_keys))
            
            payload = {
                "messageName": message_name,
                "correlationKeys": {
                    k: {"value": v, "type": self._infer_type(v)}
                    for k, v in correlation_keys.items()
                },
                "processVariables": {
                    k: {"value": v, "type": self._infer_type(v)}
                    for k, v in variables.items()
                }
            }
            
            if business_key:
                payload["businessKey"] = business_key
            
            response = await self.bpm_client.post(
                "/message",
                json=payload
            )
            response.raise_for_status()
            return response.json()
    
    async def start_process(
        self,
        process_key: str,
        variables: Dict[str, Any],
        business_key: str = None,
        tenant_id: str = None
    ):
        """Start a new process instance."""
        with tracer.start_as_current_span("start_process") as span:
            span.set_attribute("process.key", process_key)
            
            payload = {
                "variables": {
                    k: {"value": v, "type": self._infer_type(v)}
                    for k, v in variables.items()
                }
            }
            
            if business_key:
                payload["businessKey"] = business_key
            
            url = f"/process-definition/key/{process_key}"
            if tenant_id:
                url += f"/tenant-id/{tenant_id}"
            url += "/start"
            
            response = await self.bpm_client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
    
    def _infer_type(self, value: Any) -> str:
        """Infer Camunda variable type from Python type."""
        if isinstance(value, bool):
            return "Boolean"
        elif isinstance(value, int):
            return "Integer"
        elif isinstance(value, float):
            return "Double"
        elif isinstance(value, dict) or isinstance(value, list):
            return "Json"
        else:
            return "String"
    
    def _get_token(self) -> str:
        """Get Basic Auth credentials (CIB7_USER/CIB7_PASSWORD)."""
        ...
```

## Appendix B: Example TASY Regulatory Handler

```python
# healthcare_platform/shared/webhooks/handlers/tasy_regulatory.py

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from .base_handler import BaseHandler
from ..security.signature_validator import validate_tasy_signature

router = APIRouter(prefix="/webhooks/tasy/regulatory", tags=["tasy-regulatory"])

class APACSuccessPayload(BaseModel):
    nr_atendimento: int
    protocolo_apac: str
    dt_autorizacao: datetime
    vl_autorizado: float
    cd_procedimento: str
    
class APACErrorPayload(BaseModel):
    nr_atendimento: int
    cd_erro: str
    ds_erro: str
    dt_rejeicao: datetime

class TasyRegulatoryHandler(BaseHandler):
    
    async def handle_apac_success(self, payload: APACSuccessPayload):
        await self.correlate_message(
            message_name="MSG_REGULATORY_SUBMISSION_RESULT",
            correlation_keys={
                "encounter_id": str(payload.nr_atendimento)
            },
            variables={
                "regulatory_status": "APPROVED",
                "regulatory_type": "APAC",
                "protocol_number": payload.protocolo_apac,
                "authorized_amount": payload.vl_autorizado,
                "procedure_code": payload.cd_procedimento,
                "authorization_date": payload.dt_autorizacao.isoformat()
            }
        )
    
    async def handle_apac_error(self, payload: APACErrorPayload):
        await self.correlate_message(
            message_name="MSG_REGULATORY_SUBMISSION_RESULT",
            correlation_keys={
                "encounter_id": str(payload.nr_atendimento)
            },
            variables={
                "regulatory_status": "REJECTED",
                "regulatory_type": "APAC",
                "error_code": payload.cd_erro,
                "error_message": payload.ds_erro,
                "rejection_date": payload.dt_rejeicao.isoformat()
            }
        )

handler = TasyRegulatoryHandler()

@router.post("/apac/success")
async def apac_success(
    request: Request,
    payload: APACSuccessPayload,
    x_tasy_signature: str = Header(...)
):
    body = await request.body()
    if not validate_tasy_signature(body, x_tasy_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    await handler.handle_apac_success(payload)
    return {"status": "processed"}

@router.post("/apac/error")
async def apac_error(
    request: Request,
    payload: APACErrorPayload,
    x_tasy_signature: str = Header(...)
):
    body = await request.body()
    if not validate_tasy_signature(body, x_tasy_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    await handler.handle_apac_error(payload)
    return {"status": "processed"}
```
