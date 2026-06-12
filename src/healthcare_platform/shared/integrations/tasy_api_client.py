"""TASY REST API client for direct ERP integration.

This module provides direct REST API access to TASY ERP system for real-time
clinical and billing data operations. Complements tasy_client.py CDC integration.

Features:
- OAuth2 client credentials AND API key authentication
- Token bucket rate limiting (configurable, default 10 req/s)
- Circuit breaker pattern via BaseIntegrationClient
- LGPD-compliant logging (no PII)
- Multi-tenant aware via TenantContext
- Prometheus metrics for all operations
- Correlation ID propagation (X-Correlation-ID header)

Protocol:
    TasyApiClientProtocol: Abstract protocol defining TASY API operations

Implementations:
    TasyApiClient: Production client for TASY REST API
    StubTasyApiClient: Test stub for integration testing
"""

from __future__ import annotations

import asyncio
import time
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx
from prometheus_client import Counter, Gauge, Histogram

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.base import BaseIntegrationClient, IntegrationSettings
from healthcare_platform.shared.multi_tenant.context import get_current_tenant
from healthcare_platform.shared.observability.correlation import get_current_context
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_api_call

SERVICE_NAME = "tasy_api"

# ---------------------------------------------------------------------------
# TASY-Specific Prometheus Metrics
# ---------------------------------------------------------------------------

TASY_API_CALLS_TOTAL = Counter(
    "tasy_api_calls_total",
    "Total TASY API calls",
    labelnames=["endpoint", "method", "status_code", "tenant_id"],
)

TASY_API_ERRORS_TOTAL = Counter(
    "tasy_api_errors_total",
    "Total TASY API errors",
    labelnames=["endpoint", "error_type", "tenant_id"],
)

TASY_API_LATENCY_SECONDS = Histogram(
    "tasy_api_latency_seconds",
    "TASY API request latency",
    labelnames=["endpoint", "method"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

TASY_SYNC_LAG_SECONDS = Gauge(
    "tasy_sync_lag_seconds",
    "How stale TASY data is (seconds since last update)",
    labelnames=["table_name"],
)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TasyApiSettings(IntegrationSettings):
    """Configuration for TASY REST API client."""

    auth_type: Literal["oauth2", "api_key"] = "oauth2"
    client_id: str = ""
    client_secret: str = ""
    api_key: str = ""
    token_url: str = ""
    rate_limit_rps: float = 10.0


# ---------------------------------------------------------------------------
# Token Bucket Rate Limiter
# ---------------------------------------------------------------------------


class TokenBucketRateLimiter:
    """Token bucket algorithm for rate limiting.

    Refills tokens at a steady rate (rate_limit_rps).
    Each API call consumes one token.
    """

    def __init__(self, rate_limit_rps: float) -> None:
        self._rate = rate_limit_rps
        self._capacity = rate_limit_rps
        self._tokens = rate_limit_rps
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        async with self._lock:
            while self._tokens < 1.0:
                await self._refill()
                if self._tokens < 1.0:
                    await asyncio.sleep(0.1)
            self._tokens -= 1.0

    async def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class TasyApiClientProtocol(Protocol):
    """Protocol defining TASY API client operations."""

    @abstractmethod
    async def get_patient(self, patient_id: str) -> dict[str, Any]:
        """Get patient by ID from TASY PACIENTE table."""
        ...

    @abstractmethod
    async def search_patients(
        self, mrn: str | None = None, cpf: str | None = None
    ) -> list[dict[str, Any]]:
        """Search patients by MRN or CPF."""
        ...

    @abstractmethod
    async def get_encounter(self, encounter_id: str) -> dict[str, Any]:
        """Get encounter by ID from TASY ATENDIMENTO table."""
        ...

    @abstractmethod
    async def search_encounters(
        self, patient_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Search encounters for a patient."""
        ...

    @abstractmethod
    async def get_billing_account(self, account_id: str) -> dict[str, Any]:
        """Get billing account by ID from TASY CONTA_MEDICA table."""
        ...

    @abstractmethod
    async def get_billing_items(self, account_id: str) -> list[dict[str, Any]]:
        """Get billing line items from TASY ITEM_CONTA table."""
        ...

    @abstractmethod
    async def get_prescription(self, prescription_id: str) -> dict[str, Any]:
        """Get prescription by ID from TASY PRESCRICAO table."""
        ...

    @abstractmethod
    async def get_vital_signs(self, encounter_id: str) -> list[dict[str, Any]]:
        """Get vital signs for an encounter from TASY SINAL_VITAL table."""
        ...

    @abstractmethod
    async def get_coverage(self, patient_id: str) -> list[dict[str, Any]]:
        """Get insurance coverage for a patient from TASY CONVENIO_PACIENTE."""
        ...

    @abstractmethod
    async def post_billing_sync(self, account_id: str, billing_data: dict[str, Any]) -> dict[str, Any]:
        """Sync billing data to ERP system."""
        ...

    @abstractmethod
    async def get_payments(
        self, date_from: str, date_to: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Get payment records for reconciliation."""
        ...

    @abstractmethod
    async def get_receivables(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        """Get receivable records for reconciliation."""
        ...

    @abstractmethod
    async def post_pix_payment(self, payment_data: dict[str, Any]) -> dict[str, Any]:
        """Create PIX payment transaction."""
        ...

    @abstractmethod
    async def get_pix_status(self, pix_id: str) -> dict[str, Any]:
        """Get PIX payment status."""
        ...

    @abstractmethod
    async def get_material_price(
        self, material_id: str, edition: str | None = None
    ) -> dict[str, Any]:
        """Get material price from Brasindice/SIMPRO."""
        ...

    @abstractmethod
    async def get_price_strategy(self, contract_id: str) -> dict[str, Any]:
        """Get pricing strategy for a contract."""
        ...

    @abstractmethod
    async def resolve_price(
        self, material_id: str, sources: list[str]
    ) -> dict[str, Any]:
        """Resolve price from multiple sources with priority."""
        ...

    @abstractmethod
    async def get_brasindice_medicines(
        self, search: str | None = None
    ) -> list[dict[str, Any]]:
        """Get medicines from Brasindice catalog."""
        ...

    @abstractmethod
    async def get_simpro_materials(
        self, search: str | None = None
    ) -> list[dict[str, Any]]:
        """Get materials from SIMPRO catalog."""
        ...

    @abstractmethod
    async def get_procedure_price(
        self, procedure_code: str, table: str = "tuss"
    ) -> dict[str, Any]:
        """Get procedure price from TUSS or custom tables."""
        ...

    @abstractmethod
    async def post_glosa(self, glosa_data: dict[str, Any]) -> dict[str, Any]:
        """Create glosa record in TASY."""
        ...

    @abstractmethod
    async def get_glosa(self, claim_id: str) -> dict[str, Any]:
        """Get glosa by claim ID from TASY."""
        ...

    @abstractmethod
    async def update_glosa_status(
        self, glosa_id: str, status: str, reason: str | None = None
    ) -> dict[str, Any]:
        """Update glosa status in TASY."""
        ...

    @abstractmethod
    async def submit_glosa_appeal(
        self, glosa_id: str, appeal_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Submit glosa appeal to TASY."""
        ...

    @abstractmethod
    async def get_glosa_appeal_status(self, glosa_id: str) -> dict[str, Any]:
        """Get glosa appeal status from TASY."""
        ...

    @abstractmethod
    async def resolve_glosa(
        self, glosa_id: str, resolution_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve glosa in TASY."""
        ...

    @abstractmethod
    async def get_glosa_statistics(
        self, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get glosa statistics from TASY."""
        ...

    @abstractmethod
    async def batch_glosa(self, glosa_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create multiple glosas in batch."""
        ...

    @abstractmethod
    async def submit_authorization(self, auth_data: dict[str, Any]) -> dict[str, Any]:
        """Submit insurance authorization request."""
        ...

    @abstractmethod
    async def get_authorization_status(self, auth_id: str) -> dict[str, Any]:
        """Get authorization status."""
        ...

    @abstractmethod
    async def get_authorization_details(self, auth_id: str) -> dict[str, Any]:
        """Get authorization details."""
        ...

    @abstractmethod
    async def renew_authorization(self, auth_id: str, renewal_data: dict[str, Any]) -> dict[str, Any]:
        """Renew authorization."""
        ...

    @abstractmethod
    async def cancel_authorization(self, auth_id: str, reason: str) -> dict[str, Any]:
        """Cancel authorization."""
        ...

    @abstractmethod
    async def appeal_authorization(self, auth_id: str, appeal_data: dict[str, Any]) -> dict[str, Any]:
        """Appeal authorization denial."""
        ...

    @abstractmethod
    async def batch_authorization(self, auth_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Submit batch authorization requests."""
        ...

    @abstractmethod
    async def get_authorization_audit(self, auth_id: str) -> list[dict[str, Any]]:
        """Get authorization audit trail."""
        ...

    @abstractmethod
    async def attach_authorization_document(
        self, auth_id: str, document_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Attach document to authorization."""
        ...

    # TISS Data Methods
    @abstractmethod
    async def get_tiss_header(self, account_id: str) -> dict[str, Any]:
        """Get TISS header data for billing account."""
        ...

    @abstractmethod
    async def get_tiss_procedures(self, account_id: str) -> list[dict[str, Any]]:
        """Get TISS procedures for billing account."""
        ...

    @abstractmethod
    async def get_tiss_materials(self, account_id: str) -> list[dict[str, Any]]:
        """Get TISS materials for billing account."""
        ...

    @abstractmethod
    async def get_tiss_professional(self, account_id: str) -> dict[str, Any]:
        """Get TISS professional data for billing account."""
        ...

    @abstractmethod
    async def validate_tiss(self, account_id: str) -> dict[str, Any]:
        """Validate TISS data for billing account."""
        ...

    # Contract Rules Methods
    @abstractmethod
    async def get_contract_rules(self, contract_id: str) -> dict[str, Any]:
        """Get contract rules."""
        ...

    @abstractmethod
    async def get_contract_pricing(self, contract_id: str) -> dict[str, Any]:
        """Get contract pricing configuration."""
        ...

    @abstractmethod
    async def get_contract_coverage(self, contract_id: str) -> dict[str, Any]:
        """Get contract coverage details."""
        ...

    @abstractmethod
    async def get_contract_exclusions(self, contract_id: str) -> list[dict[str, Any]]:
        """Get contract exclusions."""
        ...

    @abstractmethod
    async def get_contract_modifiers(self, contract_id: str) -> list[dict[str, Any]]:
        """Get contract modifiers."""
        ...

    @abstractmethod
    async def validate_contract(self, contract_id: str, claim_data: dict[str, Any]) -> dict[str, Any]:
        """Validate claim data against contract rules."""
        ...
    @abstractmethod
    async def export_to_mvsoul(self, export_data: dict[str, Any]) -> dict[str, Any]:
        """Export data to MV Soul ERP system."""
        ...

    @abstractmethod
    async def get_mvsoul_export_status(self, export_id: str) -> dict[str, Any]:
        """Get MV Soul export status by export_id."""
        ...

    @abstractmethod
    async def reconcile_mvsoul(self, reconcile_data: dict[str, Any]) -> dict[str, Any]:
        """Reconcile data with MV Soul ERP system."""
        ...

    @abstractmethod
    async def post_pix_refund(self, pix_id: str, refund_data: dict[str, Any]) -> dict[str, Any]:
        """Create PIX payment refund."""
        ...

    @abstractmethod
    async def get_pix_receipt(self, pix_id: str) -> dict[str, Any]:
        """Get PIX payment receipt."""
        ...

    @abstractmethod
    async def post_pix_e2e_lookup(self, e2e_id: str) -> dict[str, Any]:
        """Lookup PIX payment by E2E ID."""
        ...

    @abstractmethod
    async def get_pix_settlement(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get PIX settlement report for date range."""
        ...

    # Extended Reconciliation Methods
    @abstractmethod
    async def get_reconciliation_summary(
        self, period: str, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get reconciliation summary for a period."""
        ...

    @abstractmethod
    async def close_reconciliation_period(
        self, period_id: str, close_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Close a reconciliation period."""
        ...

    @abstractmethod
    async def get_reconciliation_discrepancies(
        self, date_from: str, date_to: str
    ) -> list[dict[str, Any]]:
        """Get reconciliation discrepancies in date range."""
        ...

    # Financial Reporting Methods
    @abstractmethod
    async def get_aging_report(self, date: str | None = None) -> dict[str, Any]:
        """Get accounts receivable aging report."""
        ...

    @abstractmethod
    async def get_dso_metric(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get Days Sales Outstanding (DSO) metric."""
        ...

    @abstractmethod
    async def get_collection_rate(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get collection rate for a period."""
        ...

    @abstractmethod
    async def get_revenue_cycle_time(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get average revenue cycle time."""
        ...

    @abstractmethod
    async def get_payer_performance(
        self, payer_id: str, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get payer performance metrics."""
        ...

    @abstractmethod
    async def get_revenue_leakage(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get revenue leakage opportunities."""
        ...




    @abstractmethod
    async def search_tuss_procedures(
        self, search: str | None = None, code: str | None = None
    ) -> list[dict[str, Any]]:
        """Search TUSS procedures by name or code."""
        ...

    @abstractmethod
    async def get_tuss_procedure_details(self, procedure_code: str) -> dict[str, Any]:
        """Get detailed TUSS procedure information."""
        ...

    @abstractmethod
    async def get_compatible_procedures(self, procedure_code: str) -> list[dict[str, Any]]:
        """Get procedures compatible with the given TUSS code."""
        ...

    @abstractmethod
    async def get_cbhpm_procedure(self, procedure_code: str) -> dict[str, Any]:
        """Get CBHPM procedure details."""
        ...

    # Clinical Scoring Methods (Wave 4 - GAP-01)
    @abstractmethod
    async def get_early_warning_score(self, encounter_id: str) -> dict[str, Any]:
        """Get Early Warning Score (EWS/NEWS) for encounter."""
        ...

    @abstractmethod
    async def get_sepsis_score(self, encounter_id: str) -> dict[str, Any]:
        """Get sepsis risk score (qSOFA/SOFA) for encounter."""
        ...

    @abstractmethod
    async def get_sentry_score(self, encounter_id: str) -> dict[str, Any]:
        """Get Sentry deterioration score for encounter."""
        ...

    @abstractmethod
    async def get_sentry_smart_alert(self, encounter_id: str) -> dict[str, Any]:
        """Get Sentry smart alert for clinical deterioration."""
        ...

    @abstractmethod
    async def get_risk_of_death_score(self, encounter_id: str) -> dict[str, Any]:
        """Get risk of death score (APACHE/SAPS) for encounter."""
        ...

    @abstractmethod
    async def get_risk_of_readmission_score(self, encounter_id: str) -> dict[str, Any]:
        """Get risk of readmission score for encounter."""
        ...

    @abstractmethod
    async def get_automated_acuity(self, encounter_id: str) -> dict[str, Any]:
        """Get automated acuity classification for encounter."""
        ...

    @abstractmethod
    async def get_vent_management_score(self, encounter_id: str) -> dict[str, Any]:
        """Get ventilator management score for encounter."""
        ...

    @abstractmethod
    async def get_sepsis_alert(self, encounter_id: str) -> dict[str, Any]:
        """Get sepsis alert status for encounter."""
        ...


# ---------------------------------------------------------------------------
# Production Client
# ---------------------------------------------------------------------------


class TasyApiClient(BaseIntegrationClient, TasyApiClientProtocol):
    """Production TASY REST API client with OAuth2/API key auth and rate limiting.

    Provides direct access to TASY ERP system for real-time clinical and billing data.
    All methods track Prometheus metrics and respect rate limits.
    """

    SERVICE_NAME = SERVICE_NAME

    def __init__(self, settings: TasyApiSettings) -> None:
        """Initialize TASY API client.

        Args:
            settings: TASY API configuration including auth and rate limiting
        """
        super().__init__(settings)
        self._settings = settings
        self._rate_limiter = TokenBucketRateLimiter(settings.rate_limit_rps)
        self._oauth_token: str | None = None
        self._oauth_expires_at: float = 0.0
        self._logger = get_logger(__name__)

    async def initialize(self) -> None:
        """Create HTTP client and authenticate."""
        await super().initialize()
        if self._settings.auth_type == "oauth2":
            await self._authenticate()

    async def _authenticate(self) -> None:
        """Get OAuth2 access token using client credentials flow."""
        if (
            self._oauth_token
            and time.monotonic() < self._oauth_expires_at - 60  # Refresh 1 min early
        ):
            return

        if not self._settings.token_url:
            raise ExternalServiceException(
                _("Token URL obrigatório para autenticação OAuth2"),
                service_name=SERVICE_NAME,
                operation="authenticate",
            )

        self._logger.info("Authenticating with TASY OAuth2", auth_type="oauth2")

        try:
            async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
                response = await client.post(
                    self._settings.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._settings.client_id,
                        "client_secret": self._settings.client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()

                token_data = response.json()
                self._oauth_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                self._oauth_expires_at = time.monotonic() + expires_in

                self._logger.info(
                    "OAuth2 authentication successful", expires_in_seconds=expires_in
                )

        except httpx.HTTPStatusError as exc:
            raise ExternalServiceException(
                _("Autenticação OAuth2 falhou: HTTP {}").format(exc.response.status_code),
                service_name=SERVICE_NAME,
                operation="authenticate",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise ExternalServiceException(
                _("Erro de conexão durante autenticação OAuth2"),
                service_name=SERVICE_NAME,
                operation="authenticate",
            ) from exc

    def _get_headers(self) -> dict[str, str]:
        """Build HTTP headers with authentication and correlation ID."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        # Add authentication
        if self._settings.auth_type == "oauth2":
            if not self._oauth_token:
                raise ExternalServiceException(
                    _("Cliente não autenticado. Chame initialize() primeiro."),
                    service_name=SERVICE_NAME,
                    operation="get_headers",
                )
            headers["Authorization"] = f"Bearer {self._oauth_token}"
        elif self._settings.auth_type == "api_key":
            if not self._settings.api_key:
                raise ExternalServiceException(
                    _("API key obrigatória quando auth_type='api_key'"),
                    service_name=SERVICE_NAME,
                    operation="get_headers",
                )
            headers["X-API-Key"] = self._settings.api_key

        # Add correlation ID
        ctx = get_current_context()
        headers["X-Correlation-ID"] = ctx.trace_id

        # Add tenant ID for multi-tenant TASY installations
        tenant_ctx = get_current_tenant()
        if tenant_ctx:
            headers["X-Tenant-ID"] = tenant_ctx.tenant_id

        return headers

    async def _rate_limit(self) -> None:
        """Apply rate limiting before making API calls."""
        await self._rate_limiter.acquire()

    async def _request_with_metrics(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Make HTTP request with rate limiting and metrics tracking."""
        # Get tenant for metrics
        tenant_ctx = get_current_tenant()
        tenant_id = tenant_ctx.tenant_id if tenant_ctx else "unknown"

        # Apply rate limiting
        await self._rate_limit()

        # Re-authenticate if using OAuth2
        if self._settings.auth_type == "oauth2":
            await self._authenticate()

        # Track latency
        start = time.monotonic()
        status_code = "error"

        try:
            # Use BaseIntegrationClient's _request with circuit breaker
            response = await self._request(method, endpoint, headers=self._get_headers(), **kwargs)
            status_code = str(response.status_code)

            # Track metrics
            elapsed = time.monotonic() - start
            TASY_API_LATENCY_SECONDS.labels(endpoint=endpoint, method=method).observe(elapsed)
            TASY_API_CALLS_TOTAL.labels(
                endpoint=endpoint, method=method, status_code=status_code, tenant_id=tenant_id
            ).inc()

            return response.json()

        except ExternalServiceException as exc:
            # Track errors
            TASY_API_ERRORS_TOTAL.labels(
                endpoint=endpoint,
                error_type=type(exc).__name__,
                tenant_id=tenant_id,
            ).inc()
            elapsed = time.monotonic() - start
            TASY_API_LATENCY_SECONDS.labels(endpoint=endpoint, method=method).observe(elapsed)
            TASY_API_CALLS_TOTAL.labels(
                endpoint=endpoint, method=method, status_code=status_code, tenant_id=tenant_id
            ).inc()
            raise

    @track_api_call(service_name=SERVICE_NAME, operation="get_patient")
    async def get_patient(self, patient_id: str) -> dict[str, Any]:
        """Get patient by ID from TASY PACIENTE table.

        Args:
            patient_id: TASY patient ID

        Returns:
            Patient data dictionary from TASY

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/patients/{patient_id}"
        self._logger.debug("Getting TASY patient", patient_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="search_patients")
    async def search_patients(
        self, mrn: str | None = None, cpf: str | None = None
    ) -> list[dict[str, Any]]:
        """Search patients by MRN or CPF.

        Args:
            mrn: Medical record number
            cpf: Brazilian tax ID (CPF)

        Returns:
            List of matching patient records

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/patients"
        params = {}
        if mrn:
            params["mrn"] = mrn
        if cpf:
            params["cpf"] = cpf

        self._logger.debug("Searching TASY patients", has_mrn=bool(mrn), has_cpf=bool(cpf))
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result if isinstance(result, list) else result.get("results", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_encounter")
    async def get_encounter(self, encounter_id: str) -> dict[str, Any]:
        """Get encounter by ID from TASY ATENDIMENTO table.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Encounter data dictionary

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/encounters/{encounter_id}"
        self._logger.debug("Getting TASY encounter", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="search_encounters")
    async def search_encounters(
        self, patient_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Search encounters for a patient.

        Args:
            patient_id: TASY patient ID
            status: Optional encounter status filter

        Returns:
            List of matching encounters

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/encounters"
        params = {"patient": patient_id}
        if status:
            params["status"] = status

        self._logger.debug("Searching TASY encounters", patient_id="[REDACTED]", status=status)
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result if isinstance(result, list) else result.get("results", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_billing_account")
    async def get_billing_account(self, account_id: str) -> dict[str, Any]:
        """Get billing account by ID from TASY CONTA_MEDICA table.

        Args:
            account_id: TASY billing account ID

        Returns:
            Billing account data

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/accounts/{account_id}"
        self._logger.debug("Getting TASY billing account", account_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_billing_items")
    async def get_billing_items(self, account_id: str) -> list[dict[str, Any]]:
        """Get billing line items from TASY ITEM_CONTA table.

        Args:
            account_id: TASY billing account ID

        Returns:
            List of billing line items

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/accounts/{account_id}/items"
        self._logger.debug("Getting TASY billing items", account_id="[REDACTED]")
        result = await self._request_with_metrics("GET", endpoint)
        return result if isinstance(result, list) else result.get("items", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_prescription")
    async def get_prescription(self, prescription_id: str) -> dict[str, Any]:
        """Get prescription by ID from TASY PRESCRICAO table.

        Args:
            prescription_id: TASY prescription ID

        Returns:
            Prescription data

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/prescriptions/{prescription_id}"
        self._logger.debug("Getting TASY prescription", prescription_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_vital_signs")
    async def get_vital_signs(self, encounter_id: str) -> list[dict[str, Any]]:
        """Get vital signs for an encounter from TASY SINAL_VITAL table.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            List of vital sign observations

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/encounters/{encounter_id}/vitals"
        self._logger.debug("Getting TASY vital signs", encounter_id="[REDACTED]")
        result = await self._request_with_metrics("GET", endpoint)
        return result if isinstance(result, list) else result.get("vitals", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_coverage")
    async def get_coverage(self, patient_id: str) -> list[dict[str, Any]]:
        """Get insurance coverage for a patient from TASY CONVENIO_PACIENTE.

        Args:
            patient_id: TASY patient ID

        Returns:
            List of coverage/convênio records

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/patients/{patient_id}/coverages"
        self._logger.debug("Getting TASY coverage", patient_id="[REDACTED]")
        result = await self._request_with_metrics("GET", endpoint)
        return result if isinstance(result, list) else result.get("coverages", [])

    @track_api_call(service_name=SERVICE_NAME, operation="post_billing_sync")
    async def post_billing_sync(self, account_id: str, billing_data: dict[str, Any]) -> dict[str, Any]:
        """Sync billing data to ERP system.

        Args:
            account_id: TASY billing account ID
            billing_data: Billing data to sync

        Returns:
            Sync result with transaction_id, status, synced_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/sync"
        self._logger.debug("Syncing billing data to TASY", account_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=billing_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_payments")
    async def get_payments(
        self, date_from: str, date_to: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Get payment records for reconciliation.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)
            status: Optional payment status filter

        Returns:
            List of payment records

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/payments"
        params = {"date_from": date_from, "date_to": date_to}
        if status:
            params["status"] = status

        self._logger.debug("Getting TASY payments", date_from=date_from, date_to=date_to, status=status)
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result if isinstance(result, list) else result.get("payments", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_receivables")
    async def get_receivables(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        """Get receivable records for reconciliation.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            List of receivable records

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/receivables"
        params = {"date_from": date_from, "date_to": date_to}

        self._logger.debug("Getting TASY receivables", date_from=date_from, date_to=date_to)
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result if isinstance(result, list) else result.get("receivables", [])

    @track_api_call(service_name=SERVICE_NAME, operation="post_pix_payment")
    async def post_pix_payment(self, payment_data: dict[str, Any]) -> dict[str, Any]:
        """Create PIX payment transaction.

        Args:
            payment_data: PIX payment data including amount, recipient, etc.

        Returns:
            PIX payment result with pix_id, e2e_id, status

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/pix/payments"
        self._logger.debug("Creating PIX payment", amount="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=payment_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_pix_status")
    async def get_pix_status(self, pix_id: str) -> dict[str, Any]:
        """Get PIX payment status.

        Args:
            pix_id: PIX payment ID

        Returns:
            PIX payment status with status, confirmed_at, etc.

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/pix/payments/{pix_id}/status"
        self._logger.debug("Getting PIX payment status", pix_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="post_glosa")
    async def post_glosa(self, glosa_data: dict[str, Any]) -> dict[str, Any]:
        """Create glosa record in TASY.

        Args:
            glosa_data: Glosa data including claim_id, denied_amount, reason_code

        Returns:
            Created glosa with glosa_id, status, created_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/glosa"
        self._logger.debug("Creating TASY glosa", claim_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=glosa_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_glosa")
    async def get_glosa(self, claim_id: str) -> dict[str, Any]:
        """Get glosa by claim ID from TASY.

        Args:
            claim_id: TASY claim/account ID

        Returns:
            Glosa data with items, status, amounts

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{claim_id}"
        self._logger.debug("Getting TASY glosa", claim_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="update_glosa_status")
    async def update_glosa_status(
        self, glosa_id: str, status: str, reason: str | None = None
    ) -> dict[str, Any]:
        """Update glosa status in TASY.

        Args:
            glosa_id: TASY glosa ID
            status: New status (e.g., 'in_progress', 'resolved', 'closed')
            reason: Optional reason for status change

        Returns:
            Updated glosa with new status

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{glosa_id}/status"
        payload = {"status": status}
        if reason:
            payload["reason"] = reason
        self._logger.debug("Updating TASY glosa status", glosa_id="[REDACTED]", status=status)
        return await self._request_with_metrics("PUT", endpoint, json=payload)

    @track_api_call(service_name=SERVICE_NAME, operation="submit_glosa_appeal")
    async def submit_glosa_appeal(
        self, glosa_id: str, appeal_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Submit glosa appeal to TASY.

        Args:
            glosa_id: TASY glosa ID
            appeal_data: Appeal data including justification, documents

        Returns:
            Appeal submission result with appeal_id, protocol

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{glosa_id}/appeal"
        self._logger.debug("Submitting TASY glosa appeal", glosa_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=appeal_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_glosa_appeal_status")
    async def get_glosa_appeal_status(self, glosa_id: str) -> dict[str, Any]:
        """Get glosa appeal status from TASY.

        Args:
            glosa_id: TASY glosa ID

        Returns:
            Appeal status with protocol, payer_response, updated_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{glosa_id}/appeal/status"
        self._logger.debug("Getting TASY glosa appeal status", glosa_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="resolve_glosa")
    async def resolve_glosa(
        self, glosa_id: str, resolution_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve glosa in TASY.

        Args:
            glosa_id: TASY glosa ID
            resolution_data: Resolution data including recovered_amount, resolution_type

        Returns:
            Resolution result with final_status, resolved_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{glosa_id}/resolve"
        self._logger.debug("Resolving TASY glosa", glosa_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=resolution_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_glosa_statistics")
    async def get_glosa_statistics(
        self, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get glosa statistics from TASY.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            Statistics with total_glosas, total_denied_amount, recovery_rate

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/glosa/statistics"
        params = {"date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting TASY glosa statistics", date_from=date_from, date_to=date_to)
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result

    @track_api_call(service_name=SERVICE_NAME, operation="batch_glosa")
    async def batch_glosa(self, glosa_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create multiple glosas in batch.

        Args:
            glosa_list: List of glosa data dictionaries

        Returns:
            List of created glosas with IDs

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/glosa/batch"
        self._logger.debug("Batch creating TASY glosas", count=len(glosa_list))
        result = await self._request_with_metrics("POST", endpoint, json={"glosas": glosa_list})
        return result if isinstance(result, list) else result.get("results", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_material_price")
    async def get_material_price(
        self, material_id: str, edition: str | None = None
    ) -> dict[str, Any]:
        """Get material price from Brasindice/SIMPRO.

        Args:
            material_id: Material or medicine ID
            edition: Optional Brasindice edition (e.g., "2024-01")

        Returns:
            Price data with unit_price, currency, source, effective_date

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/pricing/materials/{material_id}"
        params = {}
        if edition:
            params["edition"] = edition

        self._logger.debug(
            "Getting material price", material_id="[REDACTED]", edition=edition
        )
        return await self._request_with_metrics("GET", endpoint, params=params)

    @track_api_call(service_name=SERVICE_NAME, operation="get_price_strategy")
    async def get_price_strategy(self, contract_id: str) -> dict[str, Any]:
        """Get pricing strategy for a contract.

        Args:
            contract_id: Contract ID

        Returns:
            Strategy data with priority_sources, markup_rules, fallback_strategy

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/pricing/strategy/{contract_id}"
        self._logger.debug("Getting price strategy", contract_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="resolve_price")
    async def resolve_price(
        self, material_id: str, sources: list[str]
    ) -> dict[str, Any]:
        """Resolve price from multiple sources with priority.

        Args:
            material_id: Material or medicine ID
            sources: List of price sources (e.g., ["brasindice", "simpro", "contract"])

        Returns:
            Resolved price with selected_source, unit_price, currency, confidence

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/pricing/resolve"
        payload = {"material_id": material_id, "sources": sources}

        self._logger.debug(
            "Resolving price", material_id="[REDACTED]", source_count=len(sources)
        )
        return await self._request_with_metrics("POST", endpoint, json=payload)

    @track_api_call(service_name=SERVICE_NAME, operation="get_brasindice_medicines")
    async def get_brasindice_medicines(
        self, search: str | None = None
    ) -> list[dict[str, Any]]:
        """Get medicines from Brasindice catalog.

        Args:
            search: Optional search query (medicine name or code)

        Returns:
            List of medicine records with codes, prices, editions

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/pricing/brasindice/medicines"
        params = {}
        if search:
            params["search"] = search

        self._logger.debug("Searching Brasindice medicines", has_search=bool(search))
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result if isinstance(result, list) else result.get("medicines", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_simpro_materials")
    async def get_simpro_materials(
        self, search: str | None = None
    ) -> list[dict[str, Any]]:
        """Get materials from SIMPRO catalog.

        Args:
            search: Optional search query (material name or code)

        Returns:
            List of material records with codes, prices, specifications

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/pricing/simpro/materials"
        params = {}
        if search:
            params["search"] = search

        self._logger.debug("Searching SIMPRO materials", has_search=bool(search))
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result if isinstance(result, list) else result.get("materials", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_procedure_price")
    async def get_procedure_price(
        self, procedure_code: str, table: str = "tuss"
    ) -> dict[str, Any]:
        """Get procedure price from TUSS or custom tables.

        Args:
            procedure_code: Procedure code (TUSS or internal)
            table: Price table name (default: "tuss")

        Returns:
            Price data with unit_price, currency, table_edition, effective_date

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/pricing/procedures/{procedure_code}"
        params = {"table": table}

        self._logger.debug(
            "Getting procedure price", procedure_code="[REDACTED]", table=table
        )
        return await self._request_with_metrics("GET", endpoint, params=params)

    @track_api_call(service_name=SERVICE_NAME, operation="search_tuss_procedures")
    async def search_tuss_procedures(
        self, search: str | None = None, code: str | None = None
    ) -> list[dict[str, Any]]:
        """Search TUSS procedures by name or code.

        Args:
            search: Optional procedure name search
            code: Optional procedure code search

        Returns:
            List of matching TUSS procedure records

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/procedures/tuss/search"
        params = {}
        if search:
            params["search"] = search
        if code:
            params["code"] = code

        self._logger.debug("Searching TUSS procedures", has_search=bool(search), has_code=bool(code))
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result if isinstance(result, list) else result.get("procedures", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_tuss_procedure_details")
    async def get_tuss_procedure_details(self, procedure_code: str) -> dict[str, Any]:
        """Get detailed TUSS procedure information.

        Args:
            procedure_code: TUSS procedure code

        Returns:
            Detailed procedure data including description, coverage, etc.

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/procedures/tuss/{procedure_code}/details"
        self._logger.debug("Getting TUSS procedure details", procedure_code="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_compatible_procedures")
    async def get_compatible_procedures(self, procedure_code: str) -> list[dict[str, Any]]:
        """Get procedures compatible with the given TUSS code.

        Args:
            procedure_code: TUSS procedure code

        Returns:
            List of compatible procedure codes

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/procedures/tuss/{procedure_code}/compatible"
        self._logger.debug("Getting compatible procedures", procedure_code="[REDACTED]")
        result = await self._request_with_metrics("GET", endpoint)
        return result if isinstance(result, list) else result.get("procedures", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_cbhpm_procedure")
    async def get_cbhpm_procedure(self, procedure_code: str) -> dict[str, Any]:
        """Get CBHPM procedure details.

        Args:
            procedure_code: CBHPM procedure code

        Returns:
            CBHPM procedure data

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/procedures/cbhpm/{procedure_code}/details"
        self._logger.debug("Getting CBHPM procedure", procedure_code="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="submit_authorization")
    async def submit_authorization(self, auth_data: dict[str, Any]) -> dict[str, Any]:
        """Submit insurance authorization request.

        Args:
            auth_data: Authorization request data including patient_id, payer_id,
                      procedure_codes, diagnosis_codes, requested_start_date, etc.

        Returns:
            Authorization response with auth_id, status, auth_number

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/insurance/authorization/submit"
        self._logger.debug("Submitting authorization request")
        return await self._request_with_metrics("POST", endpoint, json=auth_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_authorization_status")
    async def get_authorization_status(self, auth_id: str) -> dict[str, Any]:
        """Get authorization status.

        Args:
            auth_id: Authorization ID

        Returns:
            Authorization status with status, auth_number, approved_date, etc.

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/insurance/authorization/{auth_id}/status"
        self._logger.debug("Getting authorization status", auth_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_authorization_details")
    async def get_authorization_details(self, auth_id: str) -> dict[str, Any]:
        """Get authorization details.

        Args:
            auth_id: Authorization ID

        Returns:
            Full authorization details including procedures, diagnoses, dates

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/insurance/authorization/{auth_id}/details"
        self._logger.debug("Getting authorization details", auth_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="renew_authorization")
    async def renew_authorization(self, auth_id: str, renewal_data: dict[str, Any]) -> dict[str, Any]:
        """Renew authorization.

        Args:
            auth_id: Authorization ID to renew
            renewal_data: Renewal request data with new dates, procedures, etc.

        Returns:
            Renewed authorization with new auth_id, status, expiration_date

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/insurance/authorization/{auth_id}/renew"
        self._logger.debug("Renewing authorization", auth_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=renewal_data)

    @track_api_call(service_name=SERVICE_NAME, operation="cancel_authorization")
    async def cancel_authorization(self, auth_id: str, reason: str) -> dict[str, Any]:
        """Cancel authorization.

        Args:
            auth_id: Authorization ID to cancel
            reason: Cancellation reason

        Returns:
            Cancellation result with status, cancelled_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/insurance/authorization/{auth_id}/cancel"
        self._logger.debug("Cancelling authorization", auth_id="[REDACTED]")
        return await self._request_with_metrics("DELETE", endpoint, json={"reason": reason})

    @track_api_call(service_name=SERVICE_NAME, operation="appeal_authorization")
    async def appeal_authorization(self, auth_id: str, appeal_data: dict[str, Any]) -> dict[str, Any]:
        """Appeal authorization denial.

        Args:
            auth_id: Authorization ID to appeal
            appeal_data: Appeal request data with justification, supporting_docs, etc.

        Returns:
            Appeal result with appeal_id, status, submitted_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/insurance/authorization/{auth_id}/appeal"
        self._logger.debug("Appealing authorization", auth_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=appeal_data)

    @track_api_call(service_name=SERVICE_NAME, operation="batch_authorization")
    async def batch_authorization(self, auth_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Submit batch authorization requests.

        Args:
            auth_requests: List of authorization request data dictionaries

        Returns:
            List of authorization results with auth_id, status for each request

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/insurance/authorization/batch"
        self._logger.debug("Submitting batch authorization", count=len(auth_requests))
        result = await self._request_with_metrics("POST", endpoint, json={"requests": auth_requests})
        return result if isinstance(result, list) else result.get("results", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_authorization_audit")
    async def get_authorization_audit(self, auth_id: str) -> list[dict[str, Any]]:
        """Get authorization audit trail.

        Args:
            auth_id: Authorization ID

        Returns:
            List of audit entries with timestamp, action, user, details

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/insurance/authorization/{auth_id}/audit"
        self._logger.debug("Getting authorization audit", auth_id="[REDACTED]")
        result = await self._request_with_metrics("GET", endpoint)
        return result if isinstance(result, list) else result.get("audit_trail", [])

    @track_api_call(service_name=SERVICE_NAME, operation="attach_authorization_document")
    async def attach_authorization_document(
        self, auth_id: str, document_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Attach document to authorization.

        Args:
            auth_id: Authorization ID
            document_data: Document data with file_name, content_type, base64_content

        Returns:
            Attachment result with document_id, attached_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/insurance/authorization/{auth_id}/attachment"
        self._logger.debug("Attaching document to authorization", auth_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=document_data)




    @track_api_call(service_name=SERVICE_NAME, operation="export_to_mvsoul")
    async def export_to_mvsoul(self, export_data: dict[str, Any]) -> dict[str, Any]:
        """Export data to MV Soul ERP system.

        Args:
            export_data: Export data with entity_type, operation, data fields

        Returns:
            Export result with export_id, status, timestamp

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/erp/mvsoul/export"
        self._logger.debug("Exporting to MV Soul ERP", entity_type=export_data.get("entity_type"))
        return await self._request_with_metrics("POST", endpoint, json=export_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_mvsoul_export_status")
    async def get_mvsoul_export_status(self, export_id: str) -> dict[str, Any]:
        """Get MV Soul export status by export_id.

        Args:
            export_id: MV Soul export ID

        Returns:
            Status data with export_id, status, processed_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/erp/mvsoul/status/{export_id}"
        self._logger.debug("Getting MV Soul export status", export_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="reconcile_mvsoul")
    async def reconcile_mvsoul(self, reconcile_data: dict[str, Any]) -> dict[str, Any]:
        """Reconcile data with MV Soul ERP system.

        Args:
            reconcile_data: Reconciliation data with account_id, items, etc.

        Returns:
            Reconciliation result with reconcile_id, status, matched_items

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/erp/mvsoul/reconcile"
        self._logger.debug("Reconciling with MV Soul ERP", account_id=reconcile_data.get("account_id"))
        return await self._request_with_metrics("POST", endpoint, json=reconcile_data)

    @track_api_call(service_name=SERVICE_NAME, operation="post_pix_refund")
    async def post_pix_refund(self, pix_id: str, refund_data: dict[str, Any]) -> dict[str, Any]:
        """Create PIX payment refund.

        Args:
            pix_id: PIX payment ID to refund
            refund_data: Refund data with amount, reason, etc.

        Returns:
            Refund result with refund_id, status, refund_e2e_id

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/pix/payments/{pix_id}/refund"
        self._logger.debug("Creating PIX refund", pix_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=refund_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_pix_receipt")
    async def get_pix_receipt(self, pix_id: str) -> dict[str, Any]:
        """Get PIX payment receipt.

        Args:
            pix_id: PIX payment ID

        Returns:
            Receipt data with pix_id, e2e_id, amount, receipt_url

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/pix/payments/{pix_id}/receipt"
        self._logger.debug("Getting PIX receipt", pix_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="post_pix_e2e_lookup")
    async def post_pix_e2e_lookup(self, e2e_id: str) -> dict[str, Any]:
        """Lookup PIX payment by E2E ID.

        Args:
            e2e_id: PIX End-to-End ID

        Returns:
            Payment data with pix_id, status, amount, confirmed_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/pix/e2e-lookup"
        payload = {"e2e_id": e2e_id}
        self._logger.debug("Looking up PIX by E2E ID", e2e_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=payload)

    @track_api_call(service_name=SERVICE_NAME, operation="get_pix_settlement")
    async def get_pix_settlement(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get PIX settlement report for date range.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            Settlement report with total_amount, transaction_count, settlements list

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/pix/settlement"
        params = {"date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting PIX settlement", date_from=date_from, date_to=date_to)
        return await self._request_with_metrics("GET", endpoint, params=params)

    @track_api_call(service_name=SERVICE_NAME, operation="get_reconciliation_summary")
    async def get_reconciliation_summary(
        self, period: str, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get reconciliation summary for a period.

        Args:
            period: Period type (daily, weekly, monthly)
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            Summary data with total_expected, total_received, variance, status

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/reconciliation/summary"
        params = {"period": period, "date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting reconciliation summary", period=period)
        return await self._request_with_metrics("GET", endpoint, params=params)

    @track_api_call(service_name=SERVICE_NAME, operation="close_reconciliation_period")
    async def close_reconciliation_period(
        self, period_id: str, close_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Close a reconciliation period.

        Args:
            period_id: Period identifier
            close_data: Closing data including closed_by, notes, etc.

        Returns:
            Close result with status, closed_at, etc.

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/reconciliation/close"
        payload = {"period_id": period_id, **close_data}
        self._logger.debug("Closing reconciliation period", period_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=payload)

    @track_api_call(service_name=SERVICE_NAME, operation="get_reconciliation_discrepancies")
    async def get_reconciliation_discrepancies(
        self, date_from: str, date_to: str
    ) -> list[dict[str, Any]]:
        """Get reconciliation discrepancies in date range.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            List of discrepancy records with type, amount, severity, etc.

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/reconciliation/discrepancies"
        params = {"date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting reconciliation discrepancies", date_from=date_from, date_to=date_to)
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result if isinstance(result, list) else result.get("discrepancies", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_aging_report")
    async def get_aging_report(self, date: str | None = None) -> dict[str, Any]:
        """Get accounts receivable aging report.

        Args:
            date: Report date (ISO format, defaults to today)

        Returns:
            Aging report with buckets (current, 30, 60, 90, 120, 180, over_180)

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/financial/aging-report"
        params = {}
        if date:
            params["date"] = date
        self._logger.debug("Getting aging report", date=date or "today")
        return await self._request_with_metrics("GET", endpoint, params=params)

    @track_api_call(service_name=SERVICE_NAME, operation="get_dso_metric")
    async def get_dso_metric(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get Days Sales Outstanding (DSO) metric.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            DSO metric with dso_days, accounts_receivable, net_revenue, benchmark_status

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/financial/dso"
        params = {"date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting DSO metric", date_from=date_from, date_to=date_to)
        return await self._request_with_metrics("GET", endpoint, params=params)

    @track_api_call(service_name=SERVICE_NAME, operation="get_collection_rate")
    async def get_collection_rate(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get collection rate for a period.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            Collection rate with rate_percentage, collected_amount, expected_amount

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/financial/collection-rate"
        params = {"date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting collection rate", date_from=date_from, date_to=date_to)
        return await self._request_with_metrics("GET", endpoint, params=params)

    @track_api_call(service_name=SERVICE_NAME, operation="get_revenue_cycle_time")
    async def get_revenue_cycle_time(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get average revenue cycle time.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            Cycle time metrics with avg_days, median_days, by_payer, etc.

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/financial/revenue-cycle-time"
        params = {"date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting revenue cycle time", date_from=date_from, date_to=date_to)
        return await self._request_with_metrics("GET", endpoint, params=params)

    @track_api_call(service_name=SERVICE_NAME, operation="get_payer_performance")
    async def get_payer_performance(
        self, payer_id: str, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get payer performance metrics.

        Args:
            payer_id: Payer/insurance company ID
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            Performance metrics with approval_rate, denial_rate, avg_payment_time

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/financial/payer-performance/{payer_id}"
        params = {"date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting payer performance", payer_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint, params=params)

    @track_api_call(service_name=SERVICE_NAME, operation="get_revenue_leakage")
    async def get_revenue_leakage(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get revenue leakage opportunities.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            Leakage data with unbilled_encounters, undercoded_procedures, etc.

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/financial/revenue-leakage"
        params = {"date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting revenue leakage", date_from=date_from, date_to=date_to)
        return await self._request_with_metrics("GET", endpoint, params=params)


    @track_api_call(service_name=SERVICE_NAME, operation="get_tiss_header")
    async def get_tiss_header(self, account_id: str) -> dict[str, Any]:
        """Get TISS header data for billing account.

        Args:
            account_id: TASY billing account ID

        Returns:
            TISS header data with patient info, provider info, admission data

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/tiss/{account_id}/header"
        self._logger.debug("Getting TISS header", account_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_tiss_procedures")
    async def get_tiss_procedures(self, account_id: str) -> list[dict[str, Any]]:
        """Get TISS procedures for billing account.

        Args:
            account_id: TASY billing account ID

        Returns:
            List of TISS procedures with codes, quantities, dates

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/tiss/{account_id}/procedures"
        self._logger.debug("Getting TISS procedures", account_id="[REDACTED]")
        result = await self._request_with_metrics("GET", endpoint)
        return result if isinstance(result, list) else result.get("procedures", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_tiss_materials")
    async def get_tiss_materials(self, account_id: str) -> list[dict[str, Any]]:
        """Get TISS materials for billing account.

        Args:
            account_id: TASY billing account ID

        Returns:
            List of TISS materials/medications with codes, quantities, prices

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/tiss/{account_id}/materials"
        self._logger.debug("Getting TISS materials", account_id="[REDACTED]")
        result = await self._request_with_metrics("GET", endpoint)
        return result if isinstance(result, list) else result.get("materials", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_tiss_professional")
    async def get_tiss_professional(self, account_id: str) -> dict[str, Any]:
        """Get TISS professional data for billing account.

        Args:
            account_id: TASY billing account ID

        Returns:
            Professional data including name, CRM, specialty, role

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/tiss/{account_id}/professional"
        self._logger.debug("Getting TISS professional", account_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="validate_tiss")
    async def validate_tiss(self, account_id: str) -> dict[str, Any]:
        """Validate TISS data for billing account.

        Args:
            account_id: TASY billing account ID

        Returns:
            Validation result with is_valid, errors, warnings

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/tiss/{account_id}/validate"
        self._logger.debug("Validating TISS data", account_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_contract_rules")
    async def get_contract_rules(self, contract_id: str) -> dict[str, Any]:
        """Get contract rules.

        Args:
            contract_id: Contract ID

        Returns:
            Contract rules including coverage limits, authorization requirements

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/contracts/{contract_id}/rules"
        self._logger.debug("Getting contract rules", contract_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_contract_pricing")
    async def get_contract_pricing(self, contract_id: str) -> dict[str, Any]:
        """Get contract pricing configuration.

        Args:
            contract_id: Contract ID

        Returns:
            Pricing configuration with discount_rules, price_tables, modifiers

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/contracts/{contract_id}/pricing"
        self._logger.debug("Getting contract pricing", contract_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_contract_coverage")
    async def get_contract_coverage(self, contract_id: str) -> dict[str, Any]:
        """Get contract coverage details.

        Args:
            contract_id: Contract ID

        Returns:
            Coverage details with procedures, materials, limits, copays

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/contracts/{contract_id}/coverage"
        self._logger.debug("Getting contract coverage", contract_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_contract_exclusions")
    async def get_contract_exclusions(self, contract_id: str) -> list[dict[str, Any]]:
        """Get contract exclusions.

        Args:
            contract_id: Contract ID

        Returns:
            List of excluded procedures, materials, or conditions

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/contracts/{contract_id}/exclusions"
        self._logger.debug("Getting contract exclusions", contract_id="[REDACTED]")
        result = await self._request_with_metrics("GET", endpoint)
        return result if isinstance(result, list) else result.get("exclusions", [])

    @track_api_call(service_name=SERVICE_NAME, operation="get_contract_modifiers")
    async def get_contract_modifiers(self, contract_id: str) -> list[dict[str, Any]]:
        """Get contract modifiers.

        Args:
            contract_id: Contract ID

        Returns:
            List of price modifiers and adjustment rules

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/contracts/{contract_id}/modifiers"
        self._logger.debug("Getting contract modifiers", contract_id="[REDACTED]")
        result = await self._request_with_metrics("GET", endpoint)
        return result if isinstance(result, list) else result.get("modifiers", [])

    @track_api_call(service_name=SERVICE_NAME, operation="validate_contract")
    async def validate_contract(self, contract_id: str, claim_data: dict[str, Any]) -> dict[str, Any]:
        """Validate claim data against contract rules.

        Args:
            contract_id: Contract ID
            claim_data: Claim data to validate

        Returns:
            Validation result with is_valid, errors, warnings, suggested_changes

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/contracts/{contract_id}/validate"
        self._logger.debug("Validating contract claim", contract_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=claim_data)

    # Clinical Scoring Methods (Wave 4 - GAP-01)
    @track_api_call(service_name=SERVICE_NAME, operation="get_early_warning_score")
    async def get_early_warning_score(self, encounter_id: str) -> dict[str, Any]:
        """Get Early Warning Score (EWS/NEWS) for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Early warning score data with score, risk_level, parameters

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/clinical/encounters/{encounter_id}/ews"
        self._logger.debug("Getting early warning score", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_sepsis_score")
    async def get_sepsis_score(self, encounter_id: str) -> dict[str, Any]:
        """Get sepsis risk score (qSOFA/SOFA) for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Sepsis score data with score, qsofa, sofa, risk_level

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/clinical/encounters/{encounter_id}/sepsis-score"
        self._logger.debug("Getting sepsis score", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_sentry_score")
    async def get_sentry_score(self, encounter_id: str) -> dict[str, Any]:
        """Get Sentry deterioration score for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Sentry score data with score, trend, risk_level

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/clinical/encounters/{encounter_id}/sentry-score"
        self._logger.debug("Getting Sentry score", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_sentry_smart_alert")
    async def get_sentry_smart_alert(self, encounter_id: str) -> dict[str, Any]:
        """Get Sentry smart alert for clinical deterioration.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Sentry smart alert data with alert_active, last_check, criteria_met

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/clinical/encounters/{encounter_id}/sentry-smart-alert"
        self._logger.debug("Getting Sentry smart alert", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_risk_of_death_score")
    async def get_risk_of_death_score(self, encounter_id: str) -> dict[str, Any]:
        """Get risk of death score (APACHE/SAPS) for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Risk of death score with apache_ii, saps_ii, predicted_mortality

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/clinical/encounters/{encounter_id}/risk-of-death"
        self._logger.debug("Getting risk of death score", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_risk_of_readmission_score")
    async def get_risk_of_readmission_score(self, encounter_id: str) -> dict[str, Any]:
        """Get risk of readmission score for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Risk of readmission score with score, risk_level, factors

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/clinical/encounters/{encounter_id}/risk-of-readmission"
        self._logger.debug("Getting risk of readmission score", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_automated_acuity")
    async def get_automated_acuity(self, encounter_id: str) -> dict[str, Any]:
        """Get automated acuity classification for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Automated acuity data with level, manchester_category, color

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/clinical/encounters/{encounter_id}/automated-acuity"
        self._logger.debug("Getting automated acuity", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_vent_management_score")
    async def get_vent_management_score(self, encounter_id: str) -> dict[str, Any]:
        """Get ventilator management score for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Ventilator management score with compliance, fio2, peep, recommendations

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/clinical/encounters/{encounter_id}/vent-management"
        self._logger.debug("Getting ventilator management score", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="get_sepsis_alert")
    async def get_sepsis_alert(self, encounter_id: str) -> dict[str, Any]:
        """Get sepsis alert status for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Sepsis alert data with alert_active, last_check, criteria_met

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/clinical/encounters/{encounter_id}/sepsis-alert"
        self._logger.debug("Getting sepsis alert", encounter_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)


# ---------------------------------------------------------------------------
# Stub Client for Testing
# ---------------------------------------------------------------------------


class StubTasyApiClient(TasyApiClientProtocol):
    """Test stub for TASY API client.

    Returns predefined responses for integration testing.
    Does not make real HTTP requests or track metrics.
    """

    def __init__(self) -> None:
        """Initialize stub client with in-memory storage."""
        self._patients: dict[str, dict[str, Any]] = {}
        self._encounters: dict[str, dict[str, Any]] = {}
        self._billing_accounts: dict[str, dict[str, Any]] = {}
        self._prescriptions: dict[str, dict[str, Any]] = {}
        self._payments: dict[str, dict[str, Any]] = {}
        self._receivables: dict[str, dict[str, Any]] = {}
        self._pix_payments: dict[str, dict[str, Any]] = {}
        self._glosas: dict[str, dict[str, Any]] = {}
        self._authorizations: dict[str, dict[str, Any]] = {}
        self._pricing_data: dict[str, dict[str, Any]] = {
            "materials": {},
            "procedures": {},
            "strategies": {},
            "brasindice": [],
            "simpro": [],
        }
        self._reconciliation_summaries: dict[str, dict[str, Any]] = {}
        self._discrepancies: list[dict[str, Any]] = []
        self._aging_reports: dict[str, dict[str, Any]] = {}
        self._dso_metrics: dict[str, dict[str, Any]] = {}
        self._tiss_data: dict[str, dict[str, Any]] = {}
        self._contracts: dict[str, dict[str, Any]] = {}
        self._scoring_data: dict[str, dict[str, Any]] = {}
        self._logger = get_logger(__name__)

    def add_patient(self, patient_id: str, data: dict[str, Any]) -> None:
        """Add a patient to the stub store."""
        self._patients[patient_id] = data

    def add_encounter(self, encounter_id: str, data: dict[str, Any]) -> None:
        """Add an encounter to the stub store."""
        self._encounters[encounter_id] = data

    def add_billing_account(self, account_id: str, data: dict[str, Any]) -> None:
        """Add a billing account to the stub store."""
        self._billing_accounts[account_id] = data

    def add_prescription(self, prescription_id: str, data: dict[str, Any]) -> None:
        """Add a prescription to the stub store."""
        self._prescriptions[prescription_id] = data

    def add_payment(self, payment_id: str, data: dict[str, Any]) -> None:
        """Add a payment to the stub store."""
        self._payments[payment_id] = data

    def add_receivable(self, receivable_id: str, data: dict[str, Any]) -> None:
        """Add a receivable to the stub store."""
        self._receivables[receivable_id] = data

    def add_pix_payment(self, pix_id: str, data: dict[str, Any]) -> None:
        """Add a PIX payment to the stub store."""
        self._pix_payments[pix_id] = data

    def add_material_price(self, material_id: str, data: dict[str, Any]) -> None:
        """Add a material price to the stub store."""
        self._pricing_data["materials"][material_id] = data

    def add_procedure_price(self, procedure_code: str, data: dict[str, Any]) -> None:
        """Add a procedure price to the stub store."""
        self._pricing_data["procedures"][procedure_code] = data

    def add_price_strategy(self, contract_id: str, data: dict[str, Any]) -> None:
        """Add a price strategy to the stub store."""
        self._pricing_data["strategies"][contract_id] = data

    def add_procedure(self, procedure_code: str, data: dict[str, Any]) -> None:
        """Add a procedure to the stub store."""
        self._procedures[procedure_code] = data

    def add_brasindice_medicine(self, data: dict[str, Any]) -> None:
        """Add a Brasindice medicine to the stub store."""
        self._pricing_data["brasindice"].append(data)

    def add_simpro_material(self, data: dict[str, Any]) -> None:
        """Add a SIMPRO material to the stub store."""
        self._pricing_data["simpro"].append(data)

    def add_reconciliation_summary(self, key: str, data: dict[str, Any]) -> None:
        """Add a reconciliation summary to the stub store."""
        self._reconciliation_summaries[key] = data

    def add_discrepancy(self, data: dict[str, Any]) -> None:
        """Add a discrepancy to the stub store."""
        self._discrepancies.append(data)

    def add_aging_report(self, date: str, data: dict[str, Any]) -> None:
        """Add an aging report to the stub store."""
        self._aging_reports[date] = data

    def add_dso_metric(self, key: str, data: dict[str, Any]) -> None:
        """Add a DSO metric to the stub store."""
        self._dso_metrics[key] = data

    async def get_patient(self, patient_id: str) -> dict[str, Any]:
        """Get patient from stub store."""
        await asyncio.sleep(0.01)  # Simulate network delay
        if patient_id not in self._patients:
            raise ExternalServiceException(
                _("Paciente não encontrado: {}").format(patient_id),
                service_name=SERVICE_NAME,
                operation="get_patient",
                status_code=404,
            )
        return self._patients[patient_id]

    async def search_patients(
        self, mrn: str | None = None, cpf: str | None = None
    ) -> list[dict[str, Any]]:
        """Search patients in stub store."""
        await asyncio.sleep(0.01)
        results = []
        for patient in self._patients.values():
            if mrn and patient.get("mrn") == mrn or cpf and patient.get("cpf") == cpf:
                results.append(patient)
        return results

    async def get_encounter(self, encounter_id: str) -> dict[str, Any]:
        """Get encounter from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id not in self._encounters:
            raise ExternalServiceException(
                _("Atendimento não encontrado: {}").format(encounter_id),
                service_name=SERVICE_NAME,
                operation="get_encounter",
                status_code=404,
            )
        return self._encounters[encounter_id]

    async def search_encounters(
        self, patient_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Search encounters in stub store."""
        await asyncio.sleep(0.01)
        results = []
        for encounter in self._encounters.values():
            if encounter.get("patient_id") == patient_id:
                if status is None or encounter.get("status") == status:
                    results.append(encounter)
        return results

    async def get_billing_account(self, account_id: str) -> dict[str, Any]:
        """Get billing account from stub store."""
        await asyncio.sleep(0.01)
        if account_id not in self._billing_accounts:
            raise ExternalServiceException(
                _("Conta médica não encontrada: {}").format(account_id),
                service_name=SERVICE_NAME,
                operation="get_billing_account",
                status_code=404,
            )
        return self._billing_accounts[account_id]

    async def get_billing_items(self, account_id: str) -> list[dict[str, Any]]:
        """Get billing items from stub store."""
        await asyncio.sleep(0.01)
        if account_id not in self._billing_accounts:
            raise ExternalServiceException(
                _("Conta médica não encontrada: {}").format(account_id),
                service_name=SERVICE_NAME,
                operation="get_billing_items",
                status_code=404,
            )
        return self._billing_accounts[account_id].get("items", [])

    async def get_prescription(self, prescription_id: str) -> dict[str, Any]:
        """Get prescription from stub store."""
        await asyncio.sleep(0.01)
        if prescription_id not in self._prescriptions:
            raise ExternalServiceException(
                _("Prescrição não encontrada: {}").format(prescription_id),
                service_name=SERVICE_NAME,
                operation="get_prescription",
                status_code=404,
            )
        return self._prescriptions[prescription_id]

    async def get_vital_signs(self, encounter_id: str) -> list[dict[str, Any]]:
        """Get vital signs from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id not in self._encounters:
            raise ExternalServiceException(
                _("Atendimento não encontrado: {}").format(encounter_id),
                service_name=SERVICE_NAME,
                operation="get_vital_signs",
                status_code=404,
            )
        return self._encounters[encounter_id].get("vital_signs", [])

    async def get_coverage(self, patient_id: str) -> list[dict[str, Any]]:
        """Get coverage from stub store."""
        await asyncio.sleep(0.01)
        if patient_id not in self._patients:
            raise ExternalServiceException(
                _("Paciente não encontrado: {}").format(patient_id),
                service_name=SERVICE_NAME,
                operation="get_coverage",
                status_code=404,
            )
        return self._patients[patient_id].get("coverages", [])

    async def post_billing_sync(self, account_id: str, billing_data: dict[str, Any]) -> dict[str, Any]:
        """Sync billing data in stub store."""
        await asyncio.sleep(0.01)
        if account_id not in self._billing_accounts:
            raise ExternalServiceException(
                _("Conta médica não encontrada: {}").format(account_id),
                service_name=SERVICE_NAME,
                operation="post_billing_sync",
                status_code=404,
            )
        # Simulate sync response
        from datetime import datetime
        return {
            "transaction_id": f"TXN-{account_id}-{int(time.time())}",
            "status": "synced",
            "synced_at": datetime.utcnow().isoformat(),
            "account_id": account_id,
        }

    async def get_payments(
        self, date_from: str, date_to: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Get payments from stub store."""
        await asyncio.sleep(0.01)
        results = []
        for payment in self._payments.values():
            payment_date = payment.get("payment_date", "")
            if date_from <= payment_date <= date_to:
                if status is None or payment.get("status") == status:
                    results.append(payment)
        return results

    async def get_receivables(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        """Get receivables from stub store."""
        await asyncio.sleep(0.01)
        results = []
        for receivable in self._receivables.values():
            receivable_date = receivable.get("due_date", "")
            if date_from <= receivable_date <= date_to:
                results.append(receivable)
        return results

    async def post_pix_payment(self, payment_data: dict[str, Any]) -> dict[str, Any]:
        """Create PIX payment in stub store."""
        await asyncio.sleep(0.01)
        # Simulate PIX payment creation
        pix_id = f"PIX-{int(time.time())}"
        e2e_id = f"E2E-{int(time.time())}"
        pix_payment = {
            "pix_id": pix_id,
            "e2e_id": e2e_id,
            "status": "pending",
            "amount": payment_data.get("amount"),
            "created_at": time.time(),
        }
        self._pix_payments[pix_id] = pix_payment
        return pix_payment

    async def get_pix_status(self, pix_id: str) -> dict[str, Any]:
        """Get PIX payment status from stub store."""
        await asyncio.sleep(0.01)
        if pix_id not in self._pix_payments:
            raise ExternalServiceException(
                _("Pagamento PIX não encontrado: {}").format(pix_id),
                service_name=SERVICE_NAME,
                operation="get_pix_status",
                status_code=404,
            )
        return self._pix_payments[pix_id]

    async def get_material_price(
        self, material_id: str, edition: str | None = None
    ) -> dict[str, Any]:
        """Get material price from stub store."""
        await asyncio.sleep(0.01)
        if material_id not in self._pricing_data["materials"]:
            raise ExternalServiceException(
                _("Preço de material não encontrado: {}").format(material_id),
                service_name=SERVICE_NAME,
                operation="get_material_price",
                status_code=404,
            )
        return self._pricing_data["materials"][material_id]

    async def get_price_strategy(self, contract_id: str) -> dict[str, Any]:
        """Get price strategy from stub store."""
        await asyncio.sleep(0.01)
        if contract_id not in self._pricing_data["strategies"]:
            raise ExternalServiceException(
                _("Estratégia de preço não encontrada: {}").format(contract_id),
                service_name=SERVICE_NAME,
                operation="get_price_strategy",
                status_code=404,
            )
        return self._pricing_data["strategies"][contract_id]

    async def resolve_price(
        self, material_id: str, sources: list[str]
    ) -> dict[str, Any]:
        """Resolve price from stub store with priority."""
        await asyncio.sleep(0.01)
        # Try sources in order
        for source in sources:
            if source == "brasindice":
                for med in self._pricing_data["brasindice"]:
                    if med.get("material_id") == material_id:
                        return {
                            "material_id": material_id,
                            "selected_source": "brasindice",
                            "unit_price": med.get("unit_price", "0.00"),
                            "currency": med.get("currency", "BRL"),
                            "confidence": 0.95,
                        }
            elif source == "simpro":
                for mat in self._pricing_data["simpro"]:
                    if mat.get("material_id") == material_id:
                        return {
                            "material_id": material_id,
                            "selected_source": "simpro",
                            "unit_price": mat.get("unit_price", "0.00"),
                            "currency": mat.get("currency", "BRL"),
                            "confidence": 0.90,
                        }
            elif source == "contract" and material_id in self._pricing_data["materials"]:
                mat_data = self._pricing_data["materials"][material_id]
                return {
                    "material_id": material_id,
                    "selected_source": "contract",
                    "unit_price": mat_data.get("unit_price", "0.00"),
                    "currency": mat_data.get("currency", "BRL"),
                    "confidence": 1.0,
                }

        # No price found in any source
        raise ExternalServiceException(
            _("Preço não encontrado para material {} nas fontes {}").format(
                material_id, ", ".join(sources)
            ),
            service_name=SERVICE_NAME,
            operation="resolve_price",
            status_code=404,
        )

    async def get_brasindice_medicines(
        self, search: str | None = None
    ) -> list[dict[str, Any]]:
        """Get Brasindice medicines from stub store."""
        await asyncio.sleep(0.01)
        if search:
            results = []
            search_lower = search.lower()
            for med in self._pricing_data["brasindice"]:
                name = med.get("name", "").lower()
                code = med.get("code", "").lower()
                if search_lower in name or search_lower in code:
                    results.append(med)
            return results
        return self._pricing_data["brasindice"]

    async def get_simpro_materials(
        self, search: str | None = None
    ) -> list[dict[str, Any]]:
        """Get SIMPRO materials from stub store."""
        await asyncio.sleep(0.01)
        if search:
            results = []
            search_lower = search.lower()
            for mat in self._pricing_data["simpro"]:
                name = mat.get("name", "").lower()
                code = mat.get("code", "").lower()
                if search_lower in name or search_lower in code:
                    results.append(mat)
            return results
        return self._pricing_data["simpro"]

    async def get_procedure_price(
        self, procedure_code: str, table: str = "tuss"
    ) -> dict[str, Any]:
        """Get procedure price from stub store."""
        await asyncio.sleep(0.01)
        # TODO: key sera usado na busca em cache de precos de procedimentos
        # key = f"{table}:{procedure_code}"
        if procedure_code not in self._pricing_data["procedures"]:
            raise ExternalServiceException(
                _("Preço de procedimento não encontrado: {}").format(procedure_code),
                service_name=SERVICE_NAME,
                operation="get_procedure_price",
                status_code=404,
            )
        return self._pricing_data["procedures"][procedure_code]

    async def search_tuss_procedures(
        self, search: str | None = None, code: str | None = None
    ) -> list[dict[str, Any]]:
        """Search TUSS procedures in stub store."""
        await asyncio.sleep(0.01)
        results = []
        for _proc_code, proc_data in self._procedures.items():
            if code and proc_data.get("code") == code:
                results.append(proc_data)
            elif search:
                search_lower = search.lower()
                name = proc_data.get("name", "").lower()
                desc = proc_data.get("description", "").lower()
                if search_lower in name or search_lower in desc:
                    results.append(proc_data)
        return results

    async def get_tuss_procedure_details(self, procedure_code: str) -> dict[str, Any]:
        """Get TUSS procedure details from stub store."""
        await asyncio.sleep(0.01)
        if procedure_code not in self._procedures:
            raise ExternalServiceException(
                _("Procedimento TUSS não encontrado: {}").format(procedure_code),
                service_name=SERVICE_NAME,
                operation="get_tuss_procedure_details",
                status_code=404,
            )
        return self._procedures[procedure_code]

    async def get_compatible_procedures(self, procedure_code: str) -> list[dict[str, Any]]:
        """Get compatible procedures from stub store."""
        await asyncio.sleep(0.01)
        if procedure_code not in self._procedures:
            raise ExternalServiceException(
                _("Procedimento TUSS não encontrado: {}").format(procedure_code),
                service_name=SERVICE_NAME,
                operation="get_compatible_procedures",
                status_code=404,
            )
        return self._procedures[procedure_code].get("compatible_procedures", [])

    async def get_cbhpm_procedure(self, procedure_code: str) -> dict[str, Any]:
        """Get CBHPM procedure from stub store."""
        await asyncio.sleep(0.01)
        if procedure_code not in self._procedures:
            raise ExternalServiceException(
                _("Procedimento CBHPM não encontrado: {}").format(procedure_code),
                service_name=SERVICE_NAME,
                operation="get_cbhpm_procedure",
                status_code=404,
            )
        return self._procedures[procedure_code]

    async def export_to_mvsoul(self, export_data: dict[str, Any]) -> dict[str, Any]:
        """Export to MV Soul in stub store."""
        await asyncio.sleep(0.01)
        export_id = f"MVSOUL-EXP-{int(time.time())}"
        return {
            "export_id": export_id,
            "status": "success",
            "timestamp": time.time(),
            "entity_type": export_data.get("entity_type"),
        }

    async def get_mvsoul_export_status(self, export_id: str) -> dict[str, Any]:
        """Get MV Soul export status from stub store."""
        await asyncio.sleep(0.01)
        return {
            "export_id": export_id,
            "status": "processed",
            "processed_at": time.time() - 60,
        }

    async def reconcile_mvsoul(self, reconcile_data: dict[str, Any]) -> dict[str, Any]:
        """Reconcile with MV Soul in stub store."""
        await asyncio.sleep(0.01)
        reconcile_id = f"MVSOUL-REC-{int(time.time())}"
        return {
            "reconcile_id": reconcile_id,
            "status": "matched",
            "matched_items": len(reconcile_data.get("items", [])),
            "unmatched_items": 0,
        }

    async def post_pix_refund(self, pix_id: str, refund_data: dict[str, Any]) -> dict[str, Any]:
        """Create PIX refund in stub store."""
        await asyncio.sleep(0.01)
        if pix_id not in self._pix_payments:
            raise ExternalServiceException(
                _("Pagamento PIX não encontrado: {}").format(pix_id),
                service_name=SERVICE_NAME,
                operation="post_pix_refund",
                status_code=404,
            )
        refund_id = f"REFUND-{pix_id}-{int(time.time())}"
        return {
            "refund_id": refund_id,
            "pix_id": pix_id,
            "status": "pending",
            "refund_e2e_id": f"E2E-REFUND-{int(time.time())}",
            "amount": refund_data.get("amount"),
        }

    async def get_pix_receipt(self, pix_id: str) -> dict[str, Any]:
        """Get PIX receipt from stub store."""
        await asyncio.sleep(0.01)
        if pix_id not in self._pix_payments:
            raise ExternalServiceException(
                _("Pagamento PIX não encontrado: {}").format(pix_id),
                service_name=SERVICE_NAME,
                operation="get_pix_receipt",
                status_code=404,
            )
        pix_data = self._pix_payments[pix_id]
        return {
            "pix_id": pix_id,
            "e2e_id": pix_data.get("e2e_id"),
            "amount": pix_data.get("amount"),
            "receipt_url": f"https://stub.example.com/receipt/{pix_id}",
            "created_at": pix_data.get("created_at"),
        }

    async def post_pix_e2e_lookup(self, e2e_id: str) -> dict[str, Any]:
        """Lookup PIX by E2E ID in stub store."""
        await asyncio.sleep(0.01)
        for pix_id, pix_data in self._pix_payments.items():
            if pix_data.get("e2e_id") == e2e_id:
                return {
                    "pix_id": pix_id,
                    "e2e_id": e2e_id,
                    "status": pix_data.get("status"),
                    "amount": pix_data.get("amount"),
                    "confirmed_at": pix_data.get("created_at"),
                }
        raise ExternalServiceException(
            _("Pagamento PIX não encontrado para E2E: {}").format(e2e_id),
            service_name=SERVICE_NAME,
            operation="post_pix_e2e_lookup",
            status_code=404,
        )

    async def get_pix_settlement(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get PIX settlement from stub store."""
        await asyncio.sleep(0.01)
        settlements = []
        total_amount = 0.0
        for pix_data in self._pix_payments.values():
            settlements.append({
                "pix_id": pix_data.get("pix_id"),
                "amount": pix_data.get("amount", 0.0),
                "status": pix_data.get("status"),
            })
            total_amount += float(pix_data.get("amount", 0.0))
        return {
            "date_from": date_from,
            "date_to": date_to,
            "total_amount": total_amount,
            "transaction_count": len(settlements),
            "settlements": settlements,
        }

    async def post_glosa(self, glosa_data: dict[str, Any]) -> dict[str, Any]:
        """Create glosa in stub store."""
        await asyncio.sleep(0.01)
        glosa_id = f"GLOSA-{int(time.time())}"
        from datetime import datetime
        glosa = {
            "glosa_id": glosa_id,
            "claim_id": glosa_data.get("claim_id"),
            "denied_amount": glosa_data.get("denied_amount"),
            "reason_code": glosa_data.get("reason_code"),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
        self._glosas[glosa_id] = glosa
        return glosa

    async def get_glosa(self, claim_id: str) -> dict[str, Any]:
        """Get glosa from stub store."""
        await asyncio.sleep(0.01)
        for glosa in self._glosas.values():
            if glosa.get("claim_id") == claim_id:
                return glosa
        raise ExternalServiceException(
            _("Glosa não encontrada para conta: {}").format(claim_id),
            service_name=SERVICE_NAME,
            operation="get_glosa",
            status_code=404,
        )

    async def update_glosa_status(
        self, glosa_id: str, status: str, reason: str | None = None
    ) -> dict[str, Any]:
        """Update glosa status in stub store."""
        await asyncio.sleep(0.01)
        if glosa_id not in self._glosas:
            raise ExternalServiceException(
                _("Glosa não encontrada: {}").format(glosa_id),
                service_name=SERVICE_NAME,
                operation="update_glosa_status",
                status_code=404,
            )
        from datetime import datetime
        self._glosas[glosa_id]["status"] = status
        self._glosas[glosa_id]["updated_at"] = datetime.utcnow().isoformat()
        if reason:
            self._glosas[glosa_id]["status_reason"] = reason
        return self._glosas[glosa_id]

    async def submit_glosa_appeal(
        self, glosa_id: str, appeal_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Submit glosa appeal in stub store."""
        await asyncio.sleep(0.01)
        if glosa_id not in self._glosas:
            raise ExternalServiceException(
                _("Glosa não encontrada: {}").format(glosa_id),
                service_name=SERVICE_NAME,
                operation="submit_glosa_appeal",
                status_code=404,
            )
        from datetime import datetime
        appeal_id = f"APPEAL-{int(time.time())}"
        self._glosas[glosa_id]["appeal_id"] = appeal_id
        self._glosas[glosa_id]["appeal_protocol"] = f"PROT-{int(time.time())}"
        self._glosas[glosa_id]["appeal_submitted_at"] = datetime.utcnow().isoformat()
        self._glosas[glosa_id]["appeal_status"] = "submitted"
        return {
            "appeal_id": appeal_id,
            "protocol": self._glosas[glosa_id]["appeal_protocol"],
            "submitted_at": self._glosas[glosa_id]["appeal_submitted_at"],
        }

    async def get_glosa_appeal_status(self, glosa_id: str) -> dict[str, Any]:
        """Get glosa appeal status from stub store."""
        await asyncio.sleep(0.01)
        if glosa_id not in self._glosas:
            raise ExternalServiceException(
                _("Glosa não encontrada: {}").format(glosa_id),
                service_name=SERVICE_NAME,
                operation="get_glosa_appeal_status",
                status_code=404,
            )
        glosa = self._glosas[glosa_id]
        return {
            "appeal_id": glosa.get("appeal_id"),
            "protocol": glosa.get("appeal_protocol"),
            "status": glosa.get("appeal_status", "not_submitted"),
            "submitted_at": glosa.get("appeal_submitted_at"),
            "updated_at": glosa.get("updated_at"),
        }

    async def resolve_glosa(
        self, glosa_id: str, resolution_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve glosa in stub store."""
        await asyncio.sleep(0.01)
        if glosa_id not in self._glosas:
            raise ExternalServiceException(
                _("Glosa não encontrada: {}").format(glosa_id),
                service_name=SERVICE_NAME,
                operation="resolve_glosa",
                status_code=404,
            )
        from datetime import datetime
        self._glosas[glosa_id]["status"] = "resolved"
        self._glosas[glosa_id]["resolved_at"] = datetime.utcnow().isoformat()
        self._glosas[glosa_id]["recovered_amount"] = resolution_data.get("recovered_amount", 0)
        self._glosas[glosa_id]["resolution_type"] = resolution_data.get("resolution_type")
        return self._glosas[glosa_id]

    async def get_glosa_statistics(
        self, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get glosa statistics from stub store."""
        await asyncio.sleep(0.01)
        from datetime import datetime
        date_from_dt = datetime.fromisoformat(date_from)
        date_to_dt = datetime.fromisoformat(date_to)

        filtered_glosas = []
        for glosa in self._glosas.values():
            created_at = datetime.fromisoformat(glosa.get("created_at", ""))
            if date_from_dt <= created_at <= date_to_dt:
                filtered_glosas.append(glosa)

        total_denied = sum(float(g.get("denied_amount", 0)) for g in filtered_glosas)
        total_recovered = sum(float(g.get("recovered_amount", 0)) for g in filtered_glosas)

        return {
            "total_glosas": len(filtered_glosas),
            "total_denied_amount": total_denied,
            "total_recovered_amount": total_recovered,
            "recovery_rate": (total_recovered / total_denied * 100) if total_denied > 0 else 0,
            "date_from": date_from,
            "date_to": date_to,
        }

    async def batch_glosa(self, glosa_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create multiple glosas in stub store."""
        await asyncio.sleep(0.01)
        results = []
        for glosa_data in glosa_list:
            result = await self.post_glosa(glosa_data)
            results.append(result)
        return results


    def add_authorization(self, auth_id: str, data: dict[str, Any]) -> None:
        """Add an authorization to the stub store."""
        self._authorizations[auth_id] = data

    async def submit_authorization(self, auth_data: dict[str, Any]) -> dict[str, Any]:
        """Submit authorization request in stub store."""
        await asyncio.sleep(0.01)
        # Simulate authorization creation
        auth_id = f"AUTH-{int(time.time())}"
        authorization = {
            "auth_id": auth_id,
            "auth_number": f"AUTHNUM-{int(time.time())}",
            "status": "approved",
            "patient_id": auth_data.get("patient_id"),
            "payer_id": auth_data.get("payer_id"),
            "procedure_codes": auth_data.get("procedure_codes", []),
            "diagnosis_codes": auth_data.get("diagnosis_codes", []),
            "requested_start_date": auth_data.get("requested_start_date"),
            "quantity": auth_data.get("quantity", 1),
            "created_at": time.time(),
            "approved_date": time.time(),
        }
        self._authorizations[auth_id] = authorization
        return authorization

    async def get_authorization_status(self, auth_id: str) -> dict[str, Any]:
        """Get authorization status from stub store."""
        await asyncio.sleep(0.01)
        if auth_id not in self._authorizations:
            raise ExternalServiceException(
                _("Autorização não encontrada: {}").format(auth_id),
                service_name=SERVICE_NAME,
                operation="get_authorization_status",
                status_code=404,
            )
        auth = self._authorizations[auth_id]
        return {
            "auth_id": auth_id,
            "auth_number": auth.get("auth_number"),
            "status": auth.get("status", "approved"),
            "approved_date": auth.get("approved_date"),
            "expiration_date": auth.get("expiration_date"),
        }

    async def get_authorization_details(self, auth_id: str) -> dict[str, Any]:
        """Get authorization details from stub store."""
        await asyncio.sleep(0.01)
        if auth_id not in self._authorizations:
            raise ExternalServiceException(
                _("Autorização não encontrada: {}").format(auth_id),
                service_name=SERVICE_NAME,
                operation="get_authorization_details",
                status_code=404,
            )
        return self._authorizations[auth_id]

    async def renew_authorization(self, auth_id: str, renewal_data: dict[str, Any]) -> dict[str, Any]:
        """Renew authorization in stub store."""
        await asyncio.sleep(0.01)
        if auth_id not in self._authorizations:
            raise ExternalServiceException(
                _("Autorização não encontrada: {}").format(auth_id),
                service_name=SERVICE_NAME,
                operation="renew_authorization",
                status_code=404,
            )
        # Create new authorization for renewal
        new_auth_id = f"AUTH-RENEW-{int(time.time())}"
        renewed_auth = {
            **self._authorizations[auth_id],
            "auth_id": new_auth_id,
            "auth_number": f"AUTHNUM-RENEW-{int(time.time())}",
            "renewed_from": auth_id,
            "renewed_at": time.time(),
            **renewal_data,
        }
        self._authorizations[new_auth_id] = renewed_auth
        return renewed_auth

    async def cancel_authorization(self, auth_id: str, reason: str) -> dict[str, Any]:
        """Cancel authorization in stub store."""
        await asyncio.sleep(0.01)
        if auth_id not in self._authorizations:
            raise ExternalServiceException(
                _("Autorização não encontrada: {}").format(auth_id),
                service_name=SERVICE_NAME,
                operation="cancel_authorization",
                status_code=404,
            )
        self._authorizations[auth_id]["status"] = "cancelled"
        self._authorizations[auth_id]["cancelled_at"] = time.time()
        self._authorizations[auth_id]["cancellation_reason"] = reason
        return {
            "auth_id": auth_id,
            "status": "cancelled",
            "cancelled_at": self._authorizations[auth_id]["cancelled_at"],
            "reason": reason,
        }

    async def appeal_authorization(self, auth_id: str, appeal_data: dict[str, Any]) -> dict[str, Any]:
        """Appeal authorization in stub store."""
        await asyncio.sleep(0.01)
        if auth_id not in self._authorizations:
            raise ExternalServiceException(
                _("Autorização não encontrada: {}").format(auth_id),
                service_name=SERVICE_NAME,
                operation="appeal_authorization",
                status_code=404,
            )
        appeal_id = f"APPEAL-{int(time.time())}"
        appeal = {
            "appeal_id": appeal_id,
            "auth_id": auth_id,
            "status": "pending",
            "justification": appeal_data.get("justification"),
            "supporting_docs": appeal_data.get("supporting_docs", []),
            "submitted_at": time.time(),
        }
        if "appeals" not in self._authorizations[auth_id]:
            self._authorizations[auth_id]["appeals"] = []
        self._authorizations[auth_id]["appeals"].append(appeal)
        return appeal

    async def batch_authorization(self, auth_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Submit batch authorization requests in stub store."""
        await asyncio.sleep(0.01)
        results = []
        for auth_data in auth_requests:
            # Simulate individual authorization
            auth_id = f"AUTH-BATCH-{int(time.time())}-{len(results)}"
            authorization = {
                "auth_id": auth_id,
                "auth_number": f"AUTHNUM-{int(time.time())}-{len(results)}",
                "status": "approved",
                "patient_id": auth_data.get("patient_id"),
                "procedure_codes": auth_data.get("procedure_codes", []),
                "created_at": time.time(),
            }
            self._authorizations[auth_id] = authorization
            results.append(authorization)
        return results

    async def get_authorization_audit(self, auth_id: str) -> list[dict[str, Any]]:
        """Get authorization audit trail from stub store."""
        await asyncio.sleep(0.01)
        if auth_id not in self._authorizations:
            raise ExternalServiceException(
                _("Autorização não encontrada: {}").format(auth_id),
                service_name=SERVICE_NAME,
                operation="get_authorization_audit",
                status_code=404,
            )
        auth = self._authorizations[auth_id]
        # Build audit trail from authorization data
        audit_trail = [
            {
                "timestamp": auth.get("created_at"),
                "action": "created",
                "user": "system",
                "details": {"status": auth.get("status")},
            }
        ]
        if auth.get("approved_date"):
            audit_trail.append({
                "timestamp": auth.get("approved_date"),
                "action": "approved",
                "user": "system",
                "details": {"auth_number": auth.get("auth_number")},
            })
        if auth.get("cancelled_at"):
            audit_trail.append({
                "timestamp": auth.get("cancelled_at"),
                "action": "cancelled",
                "user": "system",
                "details": {"reason": auth.get("cancellation_reason")},
            })
        return audit_trail

    async def attach_authorization_document(
        self, auth_id: str, document_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Attach document to authorization in stub store."""
        await asyncio.sleep(0.01)
        if auth_id not in self._authorizations:
            raise ExternalServiceException(
                _("Autorização não encontrada: {}").format(auth_id),
                service_name=SERVICE_NAME,
                operation="attach_authorization_document",
                status_code=404,
            )
        document_id = f"DOC-{int(time.time())}"
        attachment = {
            "document_id": document_id,
            "file_name": document_data.get("file_name"),
            "content_type": document_data.get("content_type"),
            "attached_at": time.time(),
            "size_bytes": len(document_data.get("base64_content", "")),
        }
        if "documents" not in self._authorizations[auth_id]:
            self._authorizations[auth_id]["documents"] = []
        self._authorizations[auth_id]["documents"].append(attachment)
        return attachment
    async def get_reconciliation_summary(
        self, period: str, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get reconciliation summary from stub store."""
        await asyncio.sleep(0.01)
        key = f"{period}_{date_from}_{date_to}"
        if key in self._reconciliation_summaries:
            return self._reconciliation_summaries[key]
        from datetime import datetime
        return {
            "period": period,
            "date_from": date_from,
            "date_to": date_to,
            "total_expected": 350000.00,
            "total_received": 332500.75,
            "variance": -17499.25,
            "status": "balanced",
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def close_reconciliation_period(
        self, period_id: str, close_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Close reconciliation period in stub store."""
        await asyncio.sleep(0.01)
        from datetime import datetime
        return {
            "period_id": period_id,
            "status": "closed",
            "closed_at": datetime.utcnow().isoformat(),
            "closed_by": close_data.get("closed_by", "system"),
        }

    async def get_reconciliation_discrepancies(
        self, date_from: str, date_to: str
    ) -> list[dict[str, Any]]:
        """Get reconciliation discrepancies from stub store."""
        await asyncio.sleep(0.01)
        results = []
        for disc in self._discrepancies:
            disc_date = disc.get("date", "")
            if date_from <= disc_date <= date_to:
                results.append(disc)
        return results

    async def get_aging_report(self, date: str | None = None) -> dict[str, Any]:
        """Get aging report from stub store."""
        await asyncio.sleep(0.01)
        report_date = date or "today"
        if report_date in self._aging_reports:
            return self._aging_reports[report_date]
        from datetime import datetime
        return {
            "report_date": report_date,
            "total_ar": 720000.00,
            "aging_buckets": {
                "current": {"amount": 250000.00, "count": 45, "percentage": 34.7},
                "30_days": {"amount": 180000.00, "count": 32, "percentage": 25.0},
                "60_days": {"amount": 120000.00, "count": 28, "percentage": 16.7},
                "90_days": {"amount": 85000.00, "count": 18, "percentage": 11.8},
                "120_days": {"amount": 45000.00, "count": 12, "percentage": 6.3},
                "180_days": {"amount": 25000.00, "count": 8, "percentage": 3.5},
                "over_180_days": {"amount": 15000.00, "count": 5, "percentage": 2.1},
            },
            "total_claims": 148,
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def get_dso_metric(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get DSO metric from stub store."""
        await asyncio.sleep(0.01)
        key = f"{date_from}_{date_to}"
        if key in self._dso_metrics:
            return self._dso_metrics[key]
        from datetime import datetime
        return {
            "dso": 51.4,
            "accounts_receivable": 720000.00,
            "net_revenue": 1400000.00,
            "period_days": 30,
            "benchmark_status": "good",
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_collection_rate(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get collection rate from stub store."""
        await asyncio.sleep(0.01)
        from datetime import datetime
        return {
            "rate_percentage": 94.5,
            "collected_amount": 1323000.00,
            "expected_amount": 1400000.00,
            "period_start": date_from,
            "period_end": date_to,
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_revenue_cycle_time(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get revenue cycle time from stub store."""
        await asyncio.sleep(0.01)
        from datetime import datetime
        return {
            "avg_days": 38.5,
            "median_days": 35.0,
            "min_days": 15,
            "max_days": 90,
            "by_payer": {
                "sus": 45.2,
                "unimed": 28.3,
                "bradesco_saude": 32.1,
            },
            "period_start": date_from,
            "period_end": date_to,
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_payer_performance(
        self, payer_id: str, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get payer performance from stub store."""
        await asyncio.sleep(0.01)
        from datetime import datetime
        return {
            "payer_id": payer_id,
            "approval_rate": 92.5,
            "denial_rate": 7.5,
            "avg_payment_time_days": 28.3,
            "claims_submitted": 150,
            "claims_approved": 139,
            "claims_denied": 11,
            "total_approved_amount": 425000.00,
            "period_start": date_from,
            "period_end": date_to,
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_revenue_leakage(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Get revenue leakage from stub store."""
        await asyncio.sleep(0.01)
        from datetime import datetime
        return {
            "total_potential_recovery": 85000.00,
            "unbilled_encounters": {
                "count": 12,
                "amount": 35000.00,
            },
            "undercoded_procedures": {
                "count": 8,
                "amount": 18000.00,
            },
            "uncollected_approvals": {
                "count": 5,
                "amount": 22000.00,
            },
            "expired_authorizations": {
                "count": 3,
                "amount": 10000.00,
            },
            "period_start": date_from,
            "period_end": date_to,
            "calculated_at": datetime.utcnow().isoformat(),
        }

    def add_tiss_data(self, account_id: str, data: dict[str, Any]) -> None:
        """Add TISS data to the stub store."""
        self._tiss_data[account_id] = data

    def add_contract(self, contract_id: str, data: dict[str, Any]) -> None:
        """Add contract data to the stub store."""
        self._contracts[contract_id] = data

    async def get_tiss_header(self, account_id: str) -> dict[str, Any]:
        """Get TISS header from stub store."""
        await asyncio.sleep(0.01)
        if account_id not in self._tiss_data:
            raise ExternalServiceException(
                _("Dados TISS não encontrados: {}").format(account_id),
                service_name=SERVICE_NAME,
                operation="get_tiss_header",
                status_code=404,
            )
        return self._tiss_data[account_id].get("header", {})

    async def get_tiss_procedures(self, account_id: str) -> list[dict[str, Any]]:
        """Get TISS procedures from stub store."""
        await asyncio.sleep(0.01)
        if account_id not in self._tiss_data:
            raise ExternalServiceException(
                _("Dados TISS não encontrados: {}").format(account_id),
                service_name=SERVICE_NAME,
                operation="get_tiss_procedures",
                status_code=404,
            )
        return self._tiss_data[account_id].get("procedures", [])

    async def get_tiss_materials(self, account_id: str) -> list[dict[str, Any]]:
        """Get TISS materials from stub store."""
        await asyncio.sleep(0.01)
        if account_id not in self._tiss_data:
            raise ExternalServiceException(
                _("Dados TISS não encontrados: {}").format(account_id),
                service_name=SERVICE_NAME,
                operation="get_tiss_materials",
                status_code=404,
            )
        return self._tiss_data[account_id].get("materials", [])

    async def get_tiss_professional(self, account_id: str) -> dict[str, Any]:
        """Get TISS professional from stub store."""
        await asyncio.sleep(0.01)
        if account_id not in self._tiss_data:
            raise ExternalServiceException(
                _("Dados TISS não encontrados: {}").format(account_id),
                service_name=SERVICE_NAME,
                operation="get_tiss_professional",
                status_code=404,
            )
        return self._tiss_data[account_id].get("professional", {})

    async def validate_tiss(self, account_id: str) -> dict[str, Any]:
        """Validate TISS data in stub store."""
        await asyncio.sleep(0.01)
        if account_id not in self._tiss_data:
            raise ExternalServiceException(
                _("Dados TISS não encontrados: {}").format(account_id),
                service_name=SERVICE_NAME,
                operation="validate_tiss",
                status_code=404,
            )
        # Simple validation - check if header and procedures exist
        tiss_data = self._tiss_data[account_id]
        errors = []
        warnings = []
        if not tiss_data.get("header"):
            errors.append("Missing TISS header")
        if not tiss_data.get("procedures"):
            warnings.append("No procedures found")
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    async def get_contract_rules(self, contract_id: str) -> dict[str, Any]:
        """Get contract rules from stub store."""
        await asyncio.sleep(0.01)
        if contract_id not in self._contracts:
            raise ExternalServiceException(
                _("Contrato não encontrado: {}").format(contract_id),
                service_name=SERVICE_NAME,
                operation="get_contract_rules",
                status_code=404,
            )
        return self._contracts[contract_id].get("rules", {})

    async def get_contract_pricing(self, contract_id: str) -> dict[str, Any]:
        """Get contract pricing from stub store."""
        await asyncio.sleep(0.01)
        if contract_id not in self._contracts:
            raise ExternalServiceException(
                _("Contrato não encontrado: {}").format(contract_id),
                service_name=SERVICE_NAME,
                operation="get_contract_pricing",
                status_code=404,
            )
        return self._contracts[contract_id].get("pricing", {})

    async def get_contract_coverage(self, contract_id: str) -> dict[str, Any]:
        """Get contract coverage from stub store."""
        await asyncio.sleep(0.01)
        if contract_id not in self._contracts:
            raise ExternalServiceException(
                _("Contrato não encontrado: {}").format(contract_id),
                service_name=SERVICE_NAME,
                operation="get_contract_coverage",
                status_code=404,
            )
        return self._contracts[contract_id].get("coverage", {})

    async def get_contract_exclusions(self, contract_id: str) -> list[dict[str, Any]]:
        """Get contract exclusions from stub store."""
        await asyncio.sleep(0.01)
        if contract_id not in self._contracts:
            raise ExternalServiceException(
                _("Contrato não encontrado: {}").format(contract_id),
                service_name=SERVICE_NAME,
                operation="get_contract_exclusions",
                status_code=404,
            )
        return self._contracts[contract_id].get("exclusions", [])

    async def get_contract_modifiers(self, contract_id: str) -> list[dict[str, Any]]:
        """Get contract modifiers from stub store."""
        await asyncio.sleep(0.01)
        if contract_id not in self._contracts:
            raise ExternalServiceException(
                _("Contrato não encontrado: {}").format(contract_id),
                service_name=SERVICE_NAME,
                operation="get_contract_modifiers",
                status_code=404,
            )
        return self._contracts[contract_id].get("modifiers", [])

    async def validate_contract(self, contract_id: str, claim_data: dict[str, Any]) -> dict[str, Any]:
        """Validate contract claim in stub store."""
        await asyncio.sleep(0.01)
        if contract_id not in self._contracts:
            raise ExternalServiceException(
                _("Contrato não encontrado: {}").format(contract_id),
                service_name=SERVICE_NAME,
                operation="validate_contract",
                status_code=404,
            )
        # Simple validation
        contract = self._contracts[contract_id]
        errors = []
        warnings = []
        suggested_changes = []
        
        # Check against exclusions
        exclusions = contract.get("exclusions", [])
        for item in claim_data.get("items", []):
            item_code = item.get("code")
            for exclusion in exclusions:
                if exclusion.get("code") == item_code:
                    errors.append(f"Procedure {item_code} is excluded from contract")
        
        # Check coverage limits
        coverage = contract.get("coverage", {})
        limits = coverage.get("limits", {})
        total_amount = sum(float(item.get("total_price", 0)) for item in claim_data.get("items", []))
        max_amount = float(limits.get("max_claim_amount", 999999))
        if total_amount > max_amount:
            errors.append(f"Claim amount {total_amount} exceeds contract limit {max_amount}")
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "suggested_changes": suggested_changes,
        }

    def add_scoring_data(self, encounter_id: str, data: dict[str, Any]) -> None:
        """Add scoring data to the stub store."""
        self._scoring_data[encounter_id] = data

    # Clinical Scoring Methods (Wave 4 - GAP-01)
    async def get_early_warning_score(self, encounter_id: str) -> dict[str, Any]:
        """Get early warning score from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id in self._scoring_data and "ews" in self._scoring_data[encounter_id]:
            return self._scoring_data[encounter_id]["ews"]
        from datetime import datetime
        return {
            "score": 3,
            "risk_level": "medium",
            "parameters": {
                "respiratory_rate": 22,
                "oxygen_saturation": 94,
                "temperature": 38.2,
                "systolic_bp": 105,
                "heart_rate": 95,
                "consciousness": "alert",
            },
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_sepsis_score(self, encounter_id: str) -> dict[str, Any]:
        """Get sepsis score from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id in self._scoring_data and "sepsis" in self._scoring_data[encounter_id]:
            return self._scoring_data[encounter_id]["sepsis"]
        from datetime import datetime
        return {
            "score": 2,
            "qsofa": 1,
            "sofa": 4,
            "risk_level": "moderate",
            "criteria": {
                "altered_mentation": False,
                "respiratory_rate_high": True,
                "systolic_bp_low": False,
            },
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_sentry_score(self, encounter_id: str) -> dict[str, Any]:
        """Get Sentry score from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id in self._scoring_data and "sentry" in self._scoring_data[encounter_id]:
            return self._scoring_data[encounter_id]["sentry"]
        from datetime import datetime
        return {
            "score": 45,
            "trend": "stable",
            "risk_level": "low",
            "components": {
                "vital_signs": 15,
                "laboratory": 10,
                "clinical_context": 20,
            },
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_sentry_smart_alert(self, encounter_id: str) -> dict[str, Any]:
        """Get Sentry smart alert from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id in self._scoring_data and "sentry_alert" in self._scoring_data[encounter_id]:
            return self._scoring_data[encounter_id]["sentry_alert"]
        from datetime import datetime
        return {
            "alert_active": False,
            "last_check": datetime.utcnow().isoformat(),
            "criteria_met": 0,
            "total_criteria": 5,
            "triggered_criteria": [],
            "next_check": datetime.utcnow().isoformat(),
        }

    async def get_risk_of_death_score(self, encounter_id: str) -> dict[str, Any]:
        """Get risk of death score from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id in self._scoring_data and "risk_of_death" in self._scoring_data[encounter_id]:
            return self._scoring_data[encounter_id]["risk_of_death"]
        from datetime import datetime
        return {
            "apache_ii": 12,
            "saps_ii": 28,
            "predicted_mortality": 0.15,
            "risk_category": "moderate",
            "factors": [
                "age",
                "chronic_conditions",
                "acute_physiology",
            ],
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_risk_of_readmission_score(self, encounter_id: str) -> dict[str, Any]:
        """Get risk of readmission score from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id in self._scoring_data and "risk_of_readmission" in self._scoring_data[encounter_id]:
            return self._scoring_data[encounter_id]["risk_of_readmission"]
        from datetime import datetime
        return {
            "score": 0.23,
            "risk_level": "low",
            "factors": [
                "previous_admissions",
                "comorbidities",
                "social_determinants",
                "medication_adherence",
            ],
            "interventions_recommended": [
                "discharge_planning",
                "follow_up_scheduling",
            ],
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_automated_acuity(self, encounter_id: str) -> dict[str, Any]:
        """Get automated acuity from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id in self._scoring_data and "acuity" in self._scoring_data[encounter_id]:
            return self._scoring_data[encounter_id]["acuity"]
        from datetime import datetime
        return {
            "level": 3,
            "manchester_category": "urgent",
            "color": "yellow",
            "max_wait_time_minutes": 60,
            "discriminators": [
                "pain_level",
                "vital_signs",
                "presenting_complaint",
            ],
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_vent_management_score(self, encounter_id: str) -> dict[str, Any]:
        """Get ventilator management score from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id in self._scoring_data and "vent_management" in self._scoring_data[encounter_id]:
            return self._scoring_data[encounter_id]["vent_management"]
        from datetime import datetime
        return {
            "compliance": 85,
            "fio2": 0.4,
            "peep": 8,
            "tidal_volume": 450,
            "respiratory_rate": 16,
            "recommendations": [
                "Consider PEEP reduction trial",
                "Monitor plateau pressure",
                "Assess readiness for weaning",
            ],
            "alert_conditions": [],
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_sepsis_alert(self, encounter_id: str) -> dict[str, Any]:
        """Get sepsis alert from stub store."""
        await asyncio.sleep(0.01)
        if encounter_id in self._scoring_data and "sepsis_alert" in self._scoring_data[encounter_id]:
            return self._scoring_data[encounter_id]["sepsis_alert"]
        from datetime import datetime
        return {
            "alert_active": False,
            "last_check": datetime.utcnow().isoformat(),
            "criteria_met": 0,
            "total_criteria": 6,
            "triggered_criteria": [],
            "bundle_compliance": {
                "lactate_measured": True,
                "blood_cultures_obtained": True,
                "antibiotics_administered": False,
                "fluid_resuscitation": False,
            },
            "next_check": datetime.utcnow().isoformat(),
        }
