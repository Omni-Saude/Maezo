"""FastAPI webhook receiver application (ADR-014).

Entry point for all inbound webhook callbacks from external systems.
Routes: POST /webhooks/{system}/{event_type}
Health: GET /health, GET /ready
Metrics: GET /metrics (Prometheus)
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest

from healthcare_platform.shared.multi_tenant.context import clear_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.webhooks.config import WebhookSettings
from healthcare_platform.shared.webhooks.security.idempotency import IdempotencyManager
from healthcare_platform.shared.webhooks.handlers.pix_payment import PixPaymentHandler
from healthcare_platform.shared.webhooks.handlers.tasy_authorization import (
    TasyAuthorizationHandler,
)
from healthcare_platform.shared.webhooks.handlers.tasy_regulatory import (
    TasyRegulatoryHandler,
)
from healthcare_platform.shared.webhooks.handlers.tiss_response import TissResponseHandler
from healthcare_platform.shared.webhooks.handlers.whatsapp_message import (
    WhatsAppMessageHandler,
)
from healthcare_platform.shared.webhooks.security.signature_validator import (
    SignatureValidationError,
    SignatureValidator,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

WEBHOOK_REQUESTS_TOTAL = Counter(
    "webhook_requests_total",
    "Total webhook requests received",
    labelnames=["system", "event_type", "status"],
)

WEBHOOK_LATENCY_SECONDS = Histogram(
    "webhook_latency_seconds",
    "Webhook processing latency",
    labelnames=["system", "event_type"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


# ---------------------------------------------------------------------------
# Application state (populated during lifespan)
# ---------------------------------------------------------------------------


class _AppState:
    redis: aioredis.Redis
    idempotency: IdempotencyManager
    http_client: httpx.AsyncClient
    config: WebhookSettings
    signature_validator: SignatureValidator
    tasy_regulatory: TasyRegulatoryHandler
    tasy_authorization: TasyAuthorizationHandler
    pix_payment: PixPaymentHandler
    whatsapp_message: WhatsAppMessageHandler
    tiss_response: TissResponseHandler


state = _AppState()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage Redis connection and HTTP client lifecycle."""
    state.config = WebhookSettings()
    state.redis = aioredis.from_url(state.config.redis_url, decode_responses=False)
    state.idempotency = IdempotencyManager(state.redis)
    state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    state.signature_validator = SignatureValidator()
    handler_args = (state.config, state.idempotency, state.http_client, state.signature_validator)
    state.tasy_regulatory = TasyRegulatoryHandler(*handler_args)
    state.tasy_authorization = TasyAuthorizationHandler(*handler_args)
    state.pix_payment = PixPaymentHandler(*handler_args)
    state.whatsapp_message = WhatsAppMessageHandler(*handler_args)
    state.tiss_response = TissResponseHandler(*handler_args)
    logger.info("Webhook service started", cib7_url=state.config.cib7_engine_url)
    yield
    await state.http_client.aclose()
    await state.redis.aclose()
    logger.info("Webhook service stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Healthcare Webhook Receiver",
    description="Inbound webhook callbacks from external systems (ADR-014)",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Middleware: Request ID & Tenant Context
# ---------------------------------------------------------------------------


@app.middleware("http")
async def request_context_middleware(request: Request, call_next: Any) -> Response:
    """Inject request ID and extract tenant context."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    request.state.tenant_id = request.headers.get(
        "X-Tenant-ID", state.config.default_tenant_id
    )
    start = time.monotonic()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        clear_tenant()
        elapsed = time.monotonic() - start
        logger.info(
            "Request completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            elapsed_ms=round(elapsed * 1000, 2),
        )


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(SignatureValidationError)
async def signature_error_handler(
    _request: Request, exc: SignatureValidationError
) -> JSONResponse:
    logger.warning("Signature validation failed", error=str(exc))
    return JSONResponse(status_code=401, content={"error": "Invalid signature"})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/webhooks/{system}/{event_type}")
async def receive_webhook(
    system: str, event_type: str, request: Request
) -> dict[str, Any]:
    """Generic webhook receiver endpoint.

    Concrete handler registration is done by system-specific modules
    that import and extend this app. This endpoint provides the
    framework: metrics, idempotency check, and error handling.
    """
    start = time.monotonic()
    try:
        body = await request.body()
        logger.info(
            "Webhook received",
            system=system,
            event_type=event_type,
            content_length=len(body),
            request_id=getattr(request.state, "request_id", ""),
        )
        WEBHOOK_REQUESTS_TOTAL.labels(
            system=system, event_type=event_type, status="received"
        ).inc()
        return {"status": "accepted", "system": system, "event_type": event_type}
    except HTTPException:
        WEBHOOK_REQUESTS_TOTAL.labels(
            system=system, event_type=event_type, status="error"
        ).inc()
        raise
    finally:
        elapsed = time.monotonic() - start
        WEBHOOK_LATENCY_SECONDS.labels(system=system, event_type=event_type).observe(
            elapsed
        )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness probe — checks Redis connectivity."""
    try:
        await state.redis.ping()
        return {"status": "ready"}
    except Exception:
        raise HTTPException(status_code=503, detail="Redis not available")


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# Handler-specific routes (ADR-014 Wave 3.7c)
# ---------------------------------------------------------------------------


@app.post("/webhooks/tasy/regulatory/{report_type}/{status}")
async def tasy_regulatory_webhook(
    report_type: str, status: str, request: Request
) -> dict[str, Any]:
    return await state.tasy_regulatory.handle_regulatory(request, report_type, status)


@app.post("/webhooks/tasy/authorization/{status}")
async def tasy_authorization_webhook(
    status: str, request: Request
) -> dict[str, Any]:
    return await state.tasy_authorization.handle_authorization(request, status)


@app.post("/webhooks/pix/payment/{event}")
async def pix_payment_webhook(event: str, request: Request) -> dict[str, Any]:
    return await state.pix_payment.handle_payment(request, event)


@app.get("/webhooks/whatsapp/message")
async def whatsapp_verification(
    request: Request,
) -> Response:
    params = request.query_params
    return await state.whatsapp_message.handle_verification(
        hub_mode=params.get("hub.mode", ""),
        hub_verify_token=params.get("hub.verify_token", ""),
        hub_challenge=params.get("hub.challenge", ""),
    )


@app.post("/webhooks/whatsapp/message")
async def whatsapp_message_webhook(request: Request) -> dict[str, Any]:
    return await state.whatsapp_message.handle_message(request)


@app.post("/webhooks/payer/tiss/{event}")
async def tiss_response_webhook(event: str, request: Request) -> dict[str, Any]:
    return await state.tiss_response.handle_tiss(request, event)
