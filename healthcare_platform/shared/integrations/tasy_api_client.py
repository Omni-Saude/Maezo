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
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

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
            if mrn and patient.get("mrn") == mrn:
                results.append(patient)
            elif cpf and patient.get("cpf") == cpf:
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
