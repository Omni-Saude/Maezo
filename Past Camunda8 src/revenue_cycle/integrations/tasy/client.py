"""TASY ERP integration HTTP client."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import AsyncGenerator, List, Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from revenue_cycle.config import Settings
from revenue_cycle.integrations.tasy.models import (
    TasyBillingItemDTO,
    TasyDiagnosisDTO,
    TasyEncounterDTO,
    TasyMedicalRecord,
    TasyPatientDTO,
    TasyProcedureDTO,
)
from revenue_cycle.multi_tenant.credentials import TasyCredentials, TenantCredentialManager

logger = structlog.get_logger(__name__)


class TasyIntegrationError(Exception):
    """Base exception for TASY integration errors."""

    pass


class TasyAuthenticationError(TasyIntegrationError):
    """TASY authentication failed."""

    pass


class TasyNotFoundError(TasyIntegrationError):
    """Resource not found in TASY."""

    pass


class TasyTimeoutError(TasyIntegrationError):
    """TASY request timeout."""

    pass


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit tripped, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern for TASY integration.

    Prevents cascading failures by temporarily blocking requests
    to a failing service.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        half_open_attempts: int = 3,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Failures before opening circuit
            timeout_seconds: Time to wait before half-open
            half_open_attempts: Attempts in half-open before closing
        """
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._timeout_seconds = timeout_seconds
        self._half_open_attempts = half_open_attempts
        self._last_failure_time: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    async def call(self, func, *args, **kwargs):
        """
        Execute function through circuit breaker.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            TasyIntegrationError: If circuit is open
        """
        async with self._lock:
            # Check if circuit should transition from open to half-open
            if self._state == CircuitState.OPEN:
                if self._last_failure_time:
                    elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                    if elapsed >= self._timeout_seconds:
                        logger.info(
                            "Circuit breaker transitioning to half-open",
                            elapsed_seconds=elapsed,
                        )
                        self._state = CircuitState.HALF_OPEN
                        self._failure_count = 0
                    else:
                        raise TasyIntegrationError(
                            f"Circuit breaker OPEN. Retry in {self._timeout_seconds - elapsed:.0f}s"
                        )

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """Handle successful request."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Successful call in half-open, close circuit
                logger.info("Circuit breaker closing after successful call")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def _on_failure(self) -> None:
        """Handle failed request."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.utcnow()

            if self._state == CircuitState.HALF_OPEN:
                # Failure in half-open, reopen circuit
                logger.warning("Circuit breaker reopening after failed half-open attempt")
                self._state = CircuitState.OPEN
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self._failure_threshold
            ):
                # Too many failures, open circuit
                logger.error(
                    "Circuit breaker opening due to failure threshold",
                    failure_count=self._failure_count,
                    threshold=self._failure_threshold,
                )
                self._state = CircuitState.OPEN


class TasyClient:
    """
    TASY ERP integration client using httpx.

    Features:
    - OAuth authentication with token refresh
    - Automatic retry with exponential backoff
    - Circuit breaker pattern
    - Multi-tenant credential management
    - Structured logging and metrics

    Example:
        async with TasyClient(credential_manager, "tenant-123") as client:
            patient = await client.get_patient("12345")
            procedures = await client.get_procedures("encounter-67890")
    """

    def __init__(
        self,
        credential_manager: TenantCredentialManager,
        tenant_id: str,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize TASY client.

        Args:
            credential_manager: Credential manager instance
            tenant_id: Tenant identifier
            settings: Application settings (optional)
        """
        self._credential_manager = credential_manager
        self._tenant_id = tenant_id
        self._settings = settings or Settings()

        self._credentials: Optional[TasyCredentials] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._circuit_breaker = CircuitBreaker()
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def initialize(self) -> None:
        """Initialize client and authenticate."""
        # Get tenant credentials
        self._credentials = await self._credential_manager.get_tasy_credentials(self._tenant_id)

        # Create HTTP client
        self._client = httpx.AsyncClient(
            base_url=self._credentials.base_url,
            timeout=httpx.Timeout(self._settings.integration.tasy_timeout),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        # Authenticate
        await self._authenticate()

        logger.info(
            "TASY client initialized",
            tenant_id=self._tenant_id,
            base_url=self._credentials.base_url,
        )

    async def _authenticate(self) -> None:
        """Authenticate with TASY and obtain OAuth token."""
        try:
            response = await self._client.post(
                "/auth/token",
                json={
                    "username": self._credentials.username,
                    "password": self._credentials.password.get_secret_value(),
                    "grant_type": "password",
                },
            )
            response.raise_for_status()

            data = response.json()
            self._token = data["access_token"]
            expires_in = data.get("expires_in", 3600)  # Default 1 hour
            self._token_expires_at = datetime.utcnow().timestamp() + expires_in

            # Update client headers with token
            self._client.headers["Authorization"] = f"Bearer {self._token}"

            logger.info("TASY authentication successful", tenant_id=self._tenant_id)

        except httpx.HTTPStatusError as e:
            logger.error(
                "TASY authentication failed",
                tenant_id=self._tenant_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise TasyAuthenticationError(f"Authentication failed: {e}")
        except Exception as e:
            logger.error("TASY authentication error", tenant_id=self._tenant_id, error=str(e))
            raise TasyAuthenticationError(f"Authentication error: {e}")

    async def _ensure_authenticated(self) -> None:
        """Ensure token is valid, refresh if expired."""
        if not self._token or not self._token_expires_at:
            await self._authenticate()
            return

        # Check if token expired or about to expire (5 min buffer)
        if datetime.utcnow().timestamp() + 300 >= self._token_expires_at:
            logger.info("TASY token expired, refreshing", tenant_id=self._tenant_id)
            await self._authenticate()

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """
        Make authenticated HTTP request with retry.

        Args:
            method: HTTP method
            path: Request path
            **kwargs: Additional httpx request parameters

        Returns:
            HTTP response

        Raises:
            TasyIntegrationError: On request failure
        """
        await self._ensure_authenticated()

        try:
            response = await self._circuit_breaker.call(
                self._client.request,
                method,
                path,
                **kwargs,
            )
            response.raise_for_status()
            return response

        except httpx.TimeoutException as e:
            logger.error("TASY request timeout", tenant_id=self._tenant_id, path=path)
            raise TasyTimeoutError(f"Request timeout: {path}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise TasyNotFoundError(f"Resource not found: {path}")
            logger.error(
                "TASY HTTP error",
                tenant_id=self._tenant_id,
                path=path,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise TasyIntegrationError(f"HTTP error {e.response.status_code}: {e}")
        except Exception as e:
            logger.error("TASY request error", tenant_id=self._tenant_id, path=path, error=str(e))
            raise TasyIntegrationError(f"Request error: {e}")

    async def get_patient(self, patient_id: str) -> TasyPatientDTO:
        """
        Get patient data from TASY.

        Args:
            patient_id: TASY patient ID

        Returns:
            Patient data

        Raises:
            TasyNotFoundError: If patient not found
            TasyIntegrationError: On request failure
        """
        response = await self._request("GET", f"/patients/{patient_id}")
        data = response.json()

        logger.info("Retrieved TASY patient", tenant_id=self._tenant_id, patient_id=patient_id)

        return TasyPatientDTO(**data)

    async def get_encounter(self, encounter_id: str) -> TasyEncounterDTO:
        """
        Get encounter data from TASY.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Encounter data

        Raises:
            TasyNotFoundError: If encounter not found
            TasyIntegrationError: On request failure
        """
        response = await self._request("GET", f"/encounters/{encounter_id}")
        data = response.json()

        logger.info("Retrieved TASY encounter", tenant_id=self._tenant_id, encounter_id=encounter_id)

        return TasyEncounterDTO(**data)

    async def get_procedures(self, encounter_id: str) -> List[TasyProcedureDTO]:
        """
        Get procedures for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            List of procedures

        Raises:
            TasyIntegrationError: On request failure
        """
        response = await self._request("GET", f"/encounters/{encounter_id}/procedures")
        data = response.json()

        procedures = [TasyProcedureDTO(**item) for item in data.get("procedures", [])]

        logger.info(
            "Retrieved TASY procedures",
            tenant_id=self._tenant_id,
            encounter_id=encounter_id,
            count=len(procedures),
        )

        return procedures

    async def get_diagnoses(self, encounter_id: str) -> List[TasyDiagnosisDTO]:
        """
        Get diagnoses for encounter.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            List of diagnoses

        Raises:
            TasyIntegrationError: On request failure
        """
        response = await self._request("GET", f"/encounters/{encounter_id}/diagnoses")
        data = response.json()

        diagnoses = [TasyDiagnosisDTO(**item) for item in data.get("diagnoses", [])]

        logger.info(
            "Retrieved TASY diagnoses",
            tenant_id=self._tenant_id,
            encounter_id=encounter_id,
            count=len(diagnoses),
        )

        return diagnoses

    async def get_medical_record(
        self,
        patient_id: str,
        encounter_id: str,
    ) -> TasyMedicalRecord:
        """
        Get complete medical record for glosa appeal evidence.

        Args:
            patient_id: TASY patient ID
            encounter_id: TASY encounter ID

        Returns:
            Complete medical record

        Raises:
            TasyIntegrationError: On request failure
        """
        # Fetch all related data in parallel
        encounter, procedures, diagnoses = await asyncio.gather(
            self.get_encounter(encounter_id),
            self.get_procedures(encounter_id),
            self.get_diagnoses(encounter_id),
        )

        # Get clinical notes
        response = await self._request("GET", f"/encounters/{encounter_id}/clinical-notes")
        notes_data = response.json()

        # Get lab results
        lab_response = await self._request("GET", f"/encounters/{encounter_id}/lab-results")
        lab_data = lab_response.json()

        # Get imaging results
        image_response = await self._request("GET", f"/encounters/{encounter_id}/image-results")
        image_data = image_response.json()

        medical_record = TasyMedicalRecord(
            patient_id=patient_id,
            encounter_id=encounter_id,
            admission_date=encounter.date_admission,
            discharge_date=encounter.date_discharge,
            diagnoses=diagnoses,
            procedures=procedures,
            anamnese=notes_data.get("anamnese"),
            evolucao=notes_data.get("evolucao"),
            exame_fisico=notes_data.get("exame_fisico"),
            prescricoes=notes_data.get("prescricoes", []),
            lab_results=lab_data.get("results", []),
            image_results=image_data.get("results", []),
            discharge_summary=notes_data.get("discharge_summary"),
            complications=notes_data.get("complications", []),
        )

        logger.info(
            "Retrieved TASY medical record",
            tenant_id=self._tenant_id,
            patient_id=patient_id,
            encounter_id=encounter_id,
        )

        return medical_record

    async def get_billing_items(self, encounter_id: str) -> TasyBillingItemDTO:
        """
        Get billing items ready for TISS submission.

        Args:
            encounter_id: TASY encounter ID

        Returns:
            Billing item data

        Raises:
            TasyIntegrationError: On request failure
        """
        # Fetch encounter, patient, procedures, diagnoses
        encounter = await self.get_encounter(encounter_id)
        patient = await self.get_patient(encounter.patient_id)
        procedures = await self.get_procedures(encounter_id)
        diagnoses = await self.get_diagnoses(encounter_id)

        # Calculate total
        total_amount = sum(p.total_price for p in procedures)

        billing_item = TasyBillingItemDTO(
            encounter_id=encounter_id,
            patient_cpf=patient.cpf,
            convenio=encounter.convenio,
            numero_carteirinha=encounter.numero_carteirinha or "",
            procedures=procedures,
            diagnoses=diagnoses,
            total_amount=total_amount,
            date_service_start=encounter.date_admission,
            date_service_end=encounter.date_discharge,
        )

        logger.info(
            "Retrieved TASY billing items",
            tenant_id=self._tenant_id,
            encounter_id=encounter_id,
            total_amount=float(total_amount),
        )

        return billing_item

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("TASY client closed", tenant_id=self._tenant_id)

    @asynccontextmanager
    async def __aenter__(self) -> TasyClient:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def circuit_breaker_state(self) -> CircuitState:
        """Get circuit breaker state."""
        return self._circuit_breaker.state
