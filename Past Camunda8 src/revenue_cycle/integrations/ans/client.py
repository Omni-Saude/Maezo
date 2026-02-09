"""ANS Rol de Procedimentos HTTP client with caching support."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import AsyncGenerator, Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from revenue_cycle.config import Settings
from revenue_cycle.integrations.ans.models import (
    CoverageType,
    ProcedureDTO,
    ProcedureStatus,
    RolCacheEntry,
    RolSearchRequest,
    RolSearchResponse,
    RolValidationResult,
)

logger = structlog.get_logger(__name__)


class RolIntegrationError(Exception):
    """Base exception for ANS Rol integration errors."""

    pass


class RolValidationError(RolIntegrationError):
    """Procedure validation error."""

    pass


class RolTimeoutError(RolIntegrationError):
    """Request timeout."""

    pass


class RolClient:
    """
    ANS Rol de Procedimentos client for procedure coverage validation.

    Features:
    - Validates TUSS procedure codes against ANS Rol database
    - Checks procedure coverage status (mandatory/optional/excluded)
    - In-memory cache with configurable TTL (default 24h)
    - Automatic retry with exponential backoff
    - Fallback to cached data when API unavailable
    - Multi-tenant support

    Example:
        async with RolClient(settings, tenant_id="hospital-001") as client:
            # Validate single procedure
            result = await client.validate_procedure("10101012")

            # Search procedures
            response = await client.search_procedures(
                RolSearchRequest(category="Consulta", status=ProcedureStatus.ACTIVE)
            )

            # Get procedure details
            procedure = await client.get_procedure("10101012")
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        tenant_id: Optional[str] = None,
        cache_ttl_hours: int = 24,
    ):
        """
        Initialize ANS Rol client.

        Args:
            settings: Application settings
            tenant_id: Tenant identifier for multi-tenant support
            cache_ttl_hours: Cache TTL in hours (default: 24)
        """
        self._settings = settings or Settings()
        self._tenant_id = tenant_id
        self._cache_ttl = timedelta(hours=cache_ttl_hours)

        # In-memory cache: procedure_code -> RolCacheEntry
        self._cache: dict[str, RolCacheEntry] = {}

        self._client: Optional[httpx.AsyncClient] = None
        self._logger = logger.bind(
            integration="ans_rol",
            tenant_id=tenant_id,
        )

    async def initialize(self) -> None:
        """Initialize HTTP client."""
        # ANS Rol API configuration
        # In production, this would be the official ANS API endpoint
        # For now, using configurable endpoint that could be a local database or proxy
        base_url = getattr(
            self._settings.integration,
            "ans_rol_base_url",
            "https://api.ans.gov.br/rol",
        )

        timeout = getattr(
            self._settings.integration,
            "ans_rol_timeout",
            30.0,
        )

        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Hospital-Revenue-Cycle/1.0",
            },
        )

        self._logger.info(
            "ANS Rol client initialized",
            base_url=base_url,
            cache_ttl_hours=self._cache_ttl.total_seconds() / 3600,
        )

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
        Make HTTP request with retry.

        Args:
            method: HTTP method
            path: Request path
            **kwargs: Additional httpx request parameters

        Returns:
            HTTP response

        Raises:
            RolIntegrationError: On request failure
        """
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response

        except httpx.TimeoutException as e:
            self._logger.error("ANS Rol request timeout", path=path)
            raise RolTimeoutError(f"Request timeout: {path}")
        except httpx.HTTPStatusError as e:
            self._logger.error(
                "ANS Rol HTTP error",
                path=path,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise RolIntegrationError(
                f"HTTP error {e.response.status_code}: {e}"
            )
        except Exception as e:
            self._logger.error("ANS Rol request error", path=path, error=str(e))
            raise RolIntegrationError(f"Request error: {e}")

    def _get_from_cache(self, procedure_code: str) -> Optional[ProcedureDTO]:
        """
        Get procedure from cache if available and not expired.

        Args:
            procedure_code: TUSS procedure code

        Returns:
            Cached procedure data or None
        """
        cache_key = f"{self._tenant_id or 'global'}:{procedure_code}"

        if cache_key not in self._cache:
            return None

        entry = self._cache[cache_key]

        # Check if expired
        if entry.is_expired:
            self._logger.debug(
                "Cache entry expired",
                procedure_code=procedure_code,
                cached_at=entry.cached_at.isoformat(),
            )
            del self._cache[cache_key]
            return None

        self._logger.debug(
            "Cache hit",
            procedure_code=procedure_code,
            age_seconds=(datetime.now() - entry.cached_at).total_seconds(),
        )

        return entry.procedure_data

    def _store_in_cache(
        self,
        procedure_code: str,
        procedure_data: ProcedureDTO,
    ) -> None:
        """
        Store procedure in cache.

        Args:
            procedure_code: TUSS procedure code
            procedure_data: Procedure details to cache
        """
        cache_key = f"{self._tenant_id or 'global'}:{procedure_code}"

        entry = RolCacheEntry(
            procedure_code=procedure_code,
            procedure_data=procedure_data,
            cached_at=datetime.now(),
            expires_at=datetime.now() + self._cache_ttl,
            tenant_id=self._tenant_id,
        )

        self._cache[cache_key] = entry

        self._logger.debug(
            "Cached procedure",
            procedure_code=procedure_code,
            expires_at=entry.expires_at.isoformat(),
        )

    async def validate_procedure(
        self,
        procedure_code: str,
        use_cache: bool = True,
    ) -> RolValidationResult:
        """
        Validate procedure code against ANS Rol.

        Args:
            procedure_code: TUSS procedure code to validate
            use_cache: Whether to use cached data (default: True)

        Returns:
            Validation result with coverage information

        Raises:
            RolValidationError: If validation fails
        """
        self._logger.info(
            "Validating procedure against ANS Rol",
            procedure_code=procedure_code,
        )

        # Check cache first
        if use_cache:
            cached = self._get_from_cache(procedure_code)
            if cached:
                return RolValidationResult(
                    procedure_code=procedure_code,
                    is_valid=cached.status == ProcedureStatus.ACTIVE,
                    is_covered=cached.coverage_type == CoverageType.MANDATORY,
                    status=cached.status,
                    coverage_type=cached.coverage_type,
                    validation_date=datetime.now(),
                    cached=True,
                )

        # Try to get from API
        try:
            procedure = await self.get_procedure(procedure_code)

            # Store in cache for future use
            if use_cache:
                self._store_in_cache(procedure_code, procedure)

            result = RolValidationResult(
                procedure_code=procedure_code,
                is_valid=procedure.status == ProcedureStatus.ACTIVE,
                is_covered=procedure.coverage_type == CoverageType.MANDATORY,
                status=procedure.status,
                coverage_type=procedure.coverage_type,
                validation_date=datetime.now(),
                cached=False,
            )

            self._logger.info(
                "Procedure validated",
                procedure_code=procedure_code,
                is_valid=result.is_valid,
                is_covered=result.is_covered,
            )

            return result

        except RolIntegrationError as e:
            # API unavailable - try to use any cached data even if expired
            self._logger.warning(
                "ANS Rol API unavailable, attempting fallback to cache",
                procedure_code=procedure_code,
                error=str(e),
            )

            # Check cache without expiration check
            cache_key = f"{self._tenant_id or 'global'}:{procedure_code}"
            if cache_key in self._cache:
                entry = self._cache[cache_key]
                self._logger.warning(
                    "Using expired cache data due to API unavailability",
                    procedure_code=procedure_code,
                    age_hours=(datetime.now() - entry.cached_at).total_seconds() / 3600,
                )

                return RolValidationResult(
                    procedure_code=procedure_code,
                    is_valid=entry.procedure_data.status == ProcedureStatus.ACTIVE,
                    is_covered=entry.procedure_data.coverage_type == CoverageType.MANDATORY,
                    status=entry.procedure_data.status,
                    coverage_type=entry.procedure_data.coverage_type,
                    validation_date=datetime.now(),
                    cached=True,
                    error_message=f"Using cached data: {str(e)}",
                )

            # No cache available - return validation failure
            return RolValidationResult(
                procedure_code=procedure_code,
                is_valid=False,
                is_covered=False,
                validation_date=datetime.now(),
                cached=False,
                error_message=f"ANS Rol API unavailable and no cache available: {str(e)}",
            )

    async def get_procedure(self, procedure_code: str) -> ProcedureDTO:
        """
        Get procedure details from ANS Rol.

        Args:
            procedure_code: TUSS procedure code

        Returns:
            Procedure details

        Raises:
            RolIntegrationError: On API failure
        """
        response = await self._request(
            "GET",
            f"/procedures/{procedure_code}",
        )

        data = response.json()

        # Map API response to ProcedureDTO
        # Note: This is a simplified mapping. Real ANS API may have different structure
        procedure = ProcedureDTO(
            procedure_code=data["codigo"],
            description=data["descricao"],
            status=ProcedureStatus(data.get("status", "active")),
            coverage_type=CoverageType(data.get("cobertura", "mandatory")),
            effective_date=datetime.fromisoformat(data["data_inicio"]).date(),
            termination_date=datetime.fromisoformat(data["data_fim"]).date()
            if data.get("data_fim")
            else None,
            category=data.get("categoria", ""),
            specialty=data.get("especialidade"),
            requires_authorization=data.get("requer_autorizacao", False),
            rol_version=data.get("versao_rol", "2024"),
            resolution_number=data.get("numero_resolucao", "RN 465/2021"),
        )

        self._logger.debug(
            "Procedure retrieved from ANS Rol",
            procedure_code=procedure_code,
            status=procedure.status.value,
        )

        return procedure

    async def search_procedures(
        self,
        request: RolSearchRequest,
    ) -> RolSearchResponse:
        """
        Search ANS Rol procedures.

        Args:
            request: Search criteria

        Returns:
            Search results

        Raises:
            RolIntegrationError: On API failure
        """
        # Build query parameters
        params = {}
        if request.query:
            params["q"] = request.query
        if request.procedure_code:
            params["codigo"] = request.procedure_code
        if request.category:
            params["categoria"] = request.category
        if request.status:
            params["status"] = request.status.value
        if request.coverage_type:
            params["cobertura"] = request.coverage_type.value
        if request.rol_version:
            params["versao"] = request.rol_version
        params["limit"] = request.limit

        response = await self._request(
            "GET",
            "/procedures",
            params=params,
        )

        data = response.json()

        # Map API response
        procedures = [
            ProcedureDTO(
                procedure_code=item["codigo"],
                description=item["descricao"],
                status=ProcedureStatus(item.get("status", "active")),
                coverage_type=CoverageType(item.get("cobertura", "mandatory")),
                effective_date=datetime.fromisoformat(item["data_inicio"]).date(),
                termination_date=datetime.fromisoformat(item["data_fim"]).date()
                if item.get("data_fim")
                else None,
                category=item.get("categoria", ""),
                specialty=item.get("especialidade"),
                requires_authorization=item.get("requer_autorizacao", False),
                rol_version=item.get("versao_rol", "2024"),
                resolution_number=item.get("numero_resolucao", "RN 465/2021"),
            )
            for item in data.get("procedimentos", [])
        ]

        search_response = RolSearchResponse(
            total_count=data.get("total", len(procedures)),
            procedures=procedures,
            rol_version=data.get("versao_rol", "2024"),
            query_timestamp=datetime.now(),
            cached=False,
        )

        self._logger.info(
            "ANS Rol search completed",
            total_count=search_response.total_count,
            returned_count=len(procedures),
        )

        return search_response

    def clear_cache(self) -> int:
        """
        Clear all cached procedures.

        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()

        self._logger.info("Cache cleared", entries_cleared=count)

        return count

    def get_cache_stats(self) -> dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics
        """
        total = len(self._cache)
        expired = sum(1 for entry in self._cache.values() if entry.is_expired)
        active = total - expired

        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": expired,
        }

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

        self._logger.info("ANS Rol client closed")

    async def __aenter__(self) -> RolClient:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
