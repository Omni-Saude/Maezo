"""
ANS (Agência Nacional de Saúde Suplementar) API client.

Handles Rol de Procedimentos validation and procedure information retrieval.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.base import BaseIntegrationClient
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_api_call

SERVICE_NAME = "ans"
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_ANS_TIMEOUT = 10.0


# DTOs
class ProcedureDTO(BaseModel):
    """ANS procedure information."""

    code: str = Field(..., description="TUSS procedure code")
    name: str = Field(..., description="Procedure name")
    coverage_type: str = Field(..., description="Coverage type (ambulatorial, hospitalar, etc)")
    active: bool = Field(default=True, description="Whether procedure is active in Rol")
    effective_date: datetime | None = Field(None, description="Date when procedure became active")
    termination_date: datetime | None = Field(None, description="Date when procedure was terminated")
    restrictions: list[str] = Field(default_factory=list, description="Coverage restrictions")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class RolValidationResult(BaseModel):
    """Result of Rol validation."""

    code: str = Field(..., description="TUSS procedure code")
    is_valid: bool = Field(..., description="Whether code exists in current Rol")
    is_covered: bool = Field(..., description="Whether procedure is covered")
    coverage_type: str | None = Field(None, description="Type of coverage if covered")
    message: str = Field(..., description="Human-readable validation message")
    procedure: ProcedureDTO | None = Field(None, description="Full procedure details if found")
    cached: bool = Field(default=False, description="Whether result came from cache")
    cache_age_seconds: float | None = Field(None, description="Age of cached data in seconds")


class RolCacheEntry(BaseModel):
    """Cache entry for Rol data."""

    procedure: ProcedureDTO
    timestamp: float = Field(default_factory=time.time)
    ttl_seconds: float = Field(default=DEFAULT_CACHE_TTL_HOURS * 3600)

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return time.time() - self.timestamp > self.ttl_seconds

    def age_seconds(self) -> float:
        """Get age of cache entry in seconds."""
        return time.time() - self.timestamp


# Protocol
class ANSClientProtocol(ABC):
    """Protocol for ANS API clients."""

    @abstractmethod
    async def validate_procedure(self, code: str) -> RolValidationResult:
        """
        Validate if procedure code exists in current Rol.

        Args:
            code: TUSS procedure code

        Returns:
            Validation result with coverage information
        """
        pass

    @abstractmethod
    async def get_procedure(self, code: str) -> ProcedureDTO:
        """
        Get detailed procedure information.

        Args:
            code: TUSS procedure code

        Returns:
            Procedure details

        Raises:
            ValueError: If procedure not found
        """
        pass

    @abstractmethod
    async def check_coverage(self, code: str, coverage_type: str) -> bool:
        """
        Check if procedure is covered under specific coverage type.

        Args:
            code: TUSS procedure code
            coverage_type: Coverage type to check (ambulatorial, hospitalar, etc)

        Returns:
            True if covered, False otherwise
        """
        pass

    @abstractmethod
    async def search_procedures(self, query: str, limit: int = 20) -> list[ProcedureDTO]:
        """
        Search procedures by name or code.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching procedures
        """
        pass


# Production Implementation
class ANSClient(BaseIntegrationClient, ANSClientProtocol):
    """Production ANS API client with caching and fallback."""

    def __init__(
        self,
        base_url: str = "https://www.ans.gov.br/rol-api/v1",
        timeout: float = DEFAULT_ANS_TIMEOUT,
        cache_ttl_hours: float = DEFAULT_CACHE_TTL_HOURS,
    ):
        """
        Initialize ANS client.

        Args:
            base_url: ANS API base URL
            timeout: Request timeout in seconds
            cache_ttl_hours: Cache TTL in hours
        """
        super().__init__(
            service_name=SERVICE_NAME,
            base_url=base_url,
            timeout=timeout,
        )
        self._logger = get_logger(__name__, {"service": SERVICE_NAME})
        self._cache: dict[str, RolCacheEntry] = {}
        self._cache_ttl_seconds = cache_ttl_hours * 3600

    @track_api_call(service_name=SERVICE_NAME)
    async def validate_procedure(self, code: str) -> RolValidationResult:
        """Validate procedure code in Rol."""
        try:
            procedure = await self.get_procedure(code)
            is_covered = procedure.active and procedure.termination_date is None

            return RolValidationResult(
                code=code,
                is_valid=True,
                is_covered=is_covered,
                coverage_type=procedure.coverage_type,
                message=f"Procedure {code} is {'covered' if is_covered else 'not covered'}",
                procedure=procedure,
            )
        except ValueError:
            return RolValidationResult(
                code=code,
                is_valid=False,
                is_covered=False,
                message=f"Procedure {code} not found in Rol",
            )

    @track_api_call(service_name=SERVICE_NAME)
    async def get_procedure(self, code: str) -> ProcedureDTO:
        """Get procedure details with caching and fallback."""
        # Check cache first
        cached_entry = self._cache.get(code)
        if cached_entry and not cached_entry.is_expired():
            self._logger.debug("Cache hit for procedure", extra={"code": code})
            return cached_entry.procedure

        # Attempt API call
        try:
            data = await self.get(f"/procedures/{code}")
            procedure = ProcedureDTO(**data)

            # Update cache
            self._cache[code] = RolCacheEntry(
                procedure=procedure,
                ttl_seconds=self._cache_ttl_seconds,
            )

            self._logger.info("Fetched procedure from API", extra={"code": code})
            return procedure

        except Exception as e:
            # Fallback to expired cache if available
            if cached_entry:
                self._logger.warning(
                    "API unavailable, using expired cache",
                    extra={
                        "code": code,
                        "cache_age_hours": cached_entry.age_seconds() / 3600,
                        "error": str(e),
                    },
                )
                return cached_entry.procedure

            # No cache available
            self._logger.error("Failed to fetch procedure", extra={"code": code, "error": str(e)})
            raise ValueError(_("Procedimento {} não encontrado e sem dados em cache disponíveis").format(code)) from e

    @track_api_call(service_name=SERVICE_NAME)
    async def check_coverage(self, code: str, coverage_type: str) -> bool:
        """Check if procedure is covered under specific coverage type."""
        try:
            procedure = await self.get_procedure(code)
            return (
                procedure.active
                and procedure.coverage_type == coverage_type
                and procedure.termination_date is None
            )
        except ValueError:
            return False

    @track_api_call(service_name=SERVICE_NAME)
    async def search_procedures(self, query: str, limit: int = 20) -> list[ProcedureDTO]:
        """Search procedures by name or code."""
        params = {"q": query, "limit": limit}
        data = await self.get("/procedures/search", params=params)

        procedures = [ProcedureDTO(**item) for item in data.get("results", [])]

        # Update cache with results
        for proc in procedures:
            self._cache[proc.code] = RolCacheEntry(
                procedure=proc,
                ttl_seconds=self._cache_ttl_seconds,
            )

        self._logger.info(
            "Searched procedures",
            extra={"query": query, "results_count": len(procedures)},
        )

        return procedures

    def clear_cache(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._logger.info("Cleared procedure cache")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = len(self._cache)
        expired = sum(1 for entry in self._cache.values() if entry.is_expired())

        return {
            "total_entries": total,
            "expired_entries": expired,
            "valid_entries": total - expired,
            "cache_ttl_hours": self._cache_ttl_seconds / 3600,
        }


# Test Stub
class StubANSClient(ANSClientProtocol):
    """Stub ANS client for testing."""

    def __init__(self):
        """Initialize stub client with predefined test data."""
        self._logger = get_logger(__name__, {"service": f"{SERVICE_NAME}_stub"})
        self._procedures: dict[str, ProcedureDTO] = {
            "40101010": ProcedureDTO(
                code="40101010",
                name="Consulta médica em consultório",
                coverage_type="ambulatorial",
                active=True,
                effective_date=datetime(2022, 1, 1),
                restrictions=["Requires prior appointment"],
            ),
            "31001010": ProcedureDTO(
                code="31001010",
                name="Internação hospitalar em apartamento",
                coverage_type="hospitalar",
                active=True,
                effective_date=datetime(2022, 1, 1),
            ),
            "99999999": ProcedureDTO(
                code="99999999",
                name="Procedimento experimental",
                coverage_type="ambulatorial",
                active=False,
                effective_date=datetime(2020, 1, 1),
                termination_date=datetime(2021, 12, 31),
                restrictions=["Terminated procedure"],
            ),
        }

    async def validate_procedure(self, code: str) -> RolValidationResult:
        """Validate procedure code (stub)."""
        procedure = self._procedures.get(code)

        if not procedure:
            return RolValidationResult(
                code=code,
                is_valid=False,
                is_covered=False,
                message=f"Procedure {code} not found in Rol (stub)",
            )

        is_covered = procedure.active and procedure.termination_date is None

        return RolValidationResult(
            code=code,
            is_valid=True,
            is_covered=is_covered,
            coverage_type=procedure.coverage_type,
            message=f"Procedure {code} is {'covered' if is_covered else 'not covered'} (stub)",
            procedure=procedure,
        )

    async def get_procedure(self, code: str) -> ProcedureDTO:
        """Get procedure details (stub)."""
        procedure = self._procedures.get(code)
        if not procedure:
            raise ValueError(_("Procedimento {} não encontrado nos dados de stub").format(code))
        return procedure

    async def check_coverage(self, code: str, coverage_type: str) -> bool:
        """Check coverage (stub)."""
        procedure = self._procedures.get(code)
        if not procedure:
            return False
        return (
            procedure.active
            and procedure.coverage_type == coverage_type
            and procedure.termination_date is None
        )

    async def search_procedures(self, query: str, limit: int = 20) -> list[ProcedureDTO]:
        """Search procedures (stub)."""
        query_lower = query.lower()
        results = [
            proc
            for proc in self._procedures.values()
            if query_lower in proc.code.lower() or query_lower in proc.name.lower()
        ]
        return results[:limit]

    def add_test_procedure(self, procedure: ProcedureDTO) -> None:
        """Add procedure to stub data for testing."""
        self._procedures[procedure.code] = procedure
