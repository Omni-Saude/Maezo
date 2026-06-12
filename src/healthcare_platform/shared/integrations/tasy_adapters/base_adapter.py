"""Base adapter for Tasy to FHIR R4 conversions.

Provides shared utilities for all Tasy adapters:
- FHIR identifier, reference, and coding builders
- LGPD-compliant sanitization for logging
- Prometheus metrics tracking
- Tenant context support
"""

from __future__ import annotations

import copy
from abc import abstractmethod
from typing import Any, Protocol

from prometheus_client import Counter

from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)

# Prometheus metrics for adapter operations
TASY_ADAPTER_CONVERSIONS_TOTAL = Counter(
    "tasy_adapter_conversions_total",
    "Total Tasy to FHIR conversions",
    labelnames=["adapter_type", "resource_type", "tenant_id", "status"],
)

TASY_ADAPTER_ERRORS_TOTAL = Counter(
    "tasy_adapter_errors_total",
    "Total Tasy adapter conversion errors",
    labelnames=["adapter_type", "resource_type", "tenant_id", "error_type"],
)


class FHIRClientProtocol(Protocol):
    """Protocol for FHIR client dependency injection."""

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """Read a FHIR resource by ID."""
        ...

    async def search(
        self, resource_type: str, params: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Search for FHIR resources."""
        ...

    async def create(
        self, resource_type: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new FHIR resource."""
        ...

    async def update(
        self, resource_type: str, resource_id: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing FHIR resource."""
        ...


class TasyToFhirAdapter(Protocol):
    """Protocol defining the Tasy to FHIR adapter interface."""

    @abstractmethod
    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy data to FHIR R4 resource.

        Args:
            tasy_data: Raw data from Tasy ERP system

        Returns:
            FHIR R4 resource as dictionary

        Raises:
            ValueError: If required Tasy fields are missing
            ExternalServiceException: If FHIR operations fail
        """
        ...


class BaseTasyFhirAdapter:
    """Base class for all Tasy to FHIR adapters.

    Provides common utilities:
    - FHIR identifier/reference/coding builders
    - LGPD-compliant PII sanitization for logs
    - Prometheus metrics tracking
    - Tenant context handling
    """

    # Subclasses should override these
    ADAPTER_TYPE: str = "base"
    FHIR_RESOURCE_TYPE: str = "Resource"

    # PII field patterns to strip from logs (LGPD compliance)
    PII_FIELDS = {
        "NM_PACIENTE",
        "DS_ENDERECO",
        "NR_TELEFONE",
        "NR_CPF",
        "DS_EMAIL",
        "NM_MAE",
        "NM_PAI",
        "DS_OBS",
    }

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        tenant_id: str,
    ) -> None:
        """Initialize base adapter.

        Args:
            fhir_client: FHIR client for creating/updating resources
            tenant_id: Tenant identifier for multi-tenancy
        """
        self._fhir_client = fhir_client
        self._tenant_id = tenant_id
        self._logger = get_logger(f"{__name__}.{self.ADAPTER_TYPE}")

    def _build_identifier(
        self, system: str, value: str, type_code: str | None = None
    ) -> dict[str, Any]:
        """Build FHIR Identifier datatype.

        Args:
            system: Identifier system URI
            value: Identifier value
            type_code: Optional identifier type code (e.g., 'MR', 'TAX')

        Returns:
            FHIR Identifier structure
        """
        identifier: dict[str, Any] = {
            "system": system,
            "value": value,
        }

        if type_code:
            identifier["type"] = {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                        "code": type_code,
                    }
                ]
            }

        return identifier

    def _build_reference(
        self, resource_type: str, resource_id: str, display: str | None = None
    ) -> dict[str, Any]:
        """Build FHIR Reference datatype.

        Args:
            resource_type: FHIR resource type (e.g., 'Patient', 'Organization')
            resource_id: Resource logical ID
            display: Optional human-readable display text

        Returns:
            FHIR Reference structure
        """
        reference: dict[str, Any] = {
            "reference": f"{resource_type}/{resource_id}",
        }

        if display:
            reference["display"] = display

        return reference

    def _build_coding(
        self, system: str, code: str, display: str | None = None
    ) -> dict[str, Any]:
        """Build FHIR Coding datatype.

        Args:
            system: Code system URI
            code: Code value
            display: Optional human-readable display text

        Returns:
            FHIR Coding structure
        """
        coding: dict[str, Any] = {
            "system": system,
            "code": code,
        }

        if display:
            coding["display"] = display

        return coding

    def _build_codeable_concept(
        self, codings: list[dict[str, Any]], text: str | None = None
    ) -> dict[str, Any]:
        """Build FHIR CodeableConcept datatype.

        Args:
            codings: List of FHIR Coding structures
            text: Optional plain text representation

        Returns:
            FHIR CodeableConcept structure
        """
        concept: dict[str, Any] = {
            "coding": codings,
        }

        if text:
            concept["text"] = text

        return concept

    def _sanitize_for_lgpd(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sanitize PII fields for LGPD-compliant logging.

        Args:
            data: Original data dictionary

        Returns:
            Sanitized copy with PII fields redacted
        """
        sanitized = copy.deepcopy(data)

        for field in self.PII_FIELDS:
            if field in sanitized:
                sanitized[field] = "[REDACTED]"

        return sanitized

    def _track_conversion_success(self) -> None:
        """Record successful conversion in Prometheus metrics."""
        TASY_ADAPTER_CONVERSIONS_TOTAL.labels(
            adapter_type=self.ADAPTER_TYPE,
            resource_type=self.FHIR_RESOURCE_TYPE,
            tenant_id=self._tenant_id,
            status="success",
        ).inc()

    def _track_conversion_error(self, error_type: str) -> None:
        """Record conversion error in Prometheus metrics.

        Args:
            error_type: Exception class name
        """
        TASY_ADAPTER_CONVERSIONS_TOTAL.labels(
            adapter_type=self.ADAPTER_TYPE,
            resource_type=self.FHIR_RESOURCE_TYPE,
            tenant_id=self._tenant_id,
            status="error",
        ).inc()

        TASY_ADAPTER_ERRORS_TOTAL.labels(
            adapter_type=self.ADAPTER_TYPE,
            resource_type=self.FHIR_RESOURCE_TYPE,
            tenant_id=self._tenant_id,
            error_type=error_type,
        ).inc()

    def _validate_required_fields(
        self, tasy_data: dict[str, Any], required_fields: list[str]
    ) -> None:
        """Validate that required Tasy fields are present.

        Args:
            tasy_data: Tasy data dictionary
            required_fields: List of required field names

        Raises:
            ValueError: If any required field is missing
        """
        missing = [field for field in required_fields if field not in tasy_data]
        if missing:
            self._logger.error(
                "Missing required Tasy fields",
                extra={
                    "adapter_type": self.ADAPTER_TYPE,
                    "missing_fields": missing,
                    "tenant_id": self._tenant_id,
                },
            )
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

    @abstractmethod
    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy data to FHIR R4 resource.

        Subclasses must implement this method.

        Args:
            tasy_data: Raw data from Tasy ERP system

        Returns:
            FHIR R4 resource as dictionary

        Raises:
            ValueError: If required Tasy fields are missing
            ExternalServiceException: If FHIR operations fail
        """
        raise NotImplementedError
