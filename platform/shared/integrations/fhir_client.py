"""HAPI FHIR R4 client for canonical data store integration.

This module provides the canonical integration with HAPI FHIR R4 per ADR-005.
All workers should query FHIR rather than directly accessing ERP systems.

Protocol:
    FHIRClientProtocol: Abstract protocol defining FHIR operations

Implementations:
    FHIRClient: Production client for HAPI FHIR R4 7.4.0
    StubFHIRClient: Test stub for integration testing
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import Any, Protocol

import httpx

from platform.shared.domain.exceptions import ExternalServiceException
from platform.shared.integrations.base import BaseIntegrationClient
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_api_call

SERVICE_NAME = "fhir"


class FHIRClientProtocol(Protocol):
    """Protocol defining FHIR client operations."""

    @abstractmethod
    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """Read a single FHIR resource by ID.

        Args:
            resource_type: FHIR resource type (e.g., 'Patient', 'Claim')
            resource_id: Resource logical ID

        Returns:
            FHIR resource as dictionary

        Raises:
            ExternalServiceException: On FHIR errors or connectivity issues
        """
        ...

    @abstractmethod
    async def search(
        self, resource_type: str, params: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Search for FHIR resources.

        Args:
            resource_type: FHIR resource type to search
            params: Search parameters (e.g., {'patient': 'P123', 'status': 'active'})

        Returns:
            List of matching FHIR resources

        Raises:
            ExternalServiceException: On FHIR errors or connectivity issues
        """
        ...

    @abstractmethod
    async def create(
        self, resource_type: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new FHIR resource.

        Args:
            resource_type: FHIR resource type
            resource: FHIR resource content

        Returns:
            Created resource with server-assigned ID

        Raises:
            ExternalServiceException: On FHIR errors or connectivity issues
        """
        ...

    @abstractmethod
    async def update(
        self, resource_type: str, resource_id: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing FHIR resource.

        Args:
            resource_type: FHIR resource type
            resource_id: Resource logical ID
            resource: Updated resource content

        Returns:
            Updated resource

        Raises:
            ExternalServiceException: On FHIR errors or connectivity issues
        """
        ...

    @abstractmethod
    async def get_patient(self, patient_id: str) -> dict[str, Any]:
        """Get patient resource by ID.

        Args:
            patient_id: Patient logical ID

        Returns:
            Patient FHIR resource

        Raises:
            ExternalServiceException: On FHIR errors or connectivity issues
        """
        ...

    @abstractmethod
    async def get_coverage(self, patient_id: str) -> list[dict[str, Any]]:
        """Get all coverage resources for a patient.

        Args:
            patient_id: Patient logical ID

        Returns:
            List of Coverage resources

        Raises:
            ExternalServiceException: On FHIR errors or connectivity issues
        """
        ...

    @abstractmethod
    async def get_encounter(self, encounter_id: str) -> dict[str, Any]:
        """Get encounter resource by ID.

        Args:
            encounter_id: Encounter logical ID

        Returns:
            Encounter FHIR resource

        Raises:
            ExternalServiceException: On FHIR errors or connectivity issues
        """
        ...

    @abstractmethod
    async def get_claim(self, claim_id: str) -> dict[str, Any]:
        """Get claim resource by ID.

        Args:
            claim_id: Claim logical ID

        Returns:
            Claim FHIR resource

        Raises:
            ExternalServiceException: On FHIR errors or connectivity issues
        """
        ...


class FHIRClient(BaseIntegrationClient, FHIRClientProtocol):
    """Production FHIR client for HAPI FHIR R4 7.4.0.

    Communicates with HAPI FHIR server via REST API.
    Handles FHIR OperationOutcome errors and connection issues.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        api_key: str | None = None,
    ) -> None:
        """Initialize FHIR client.

        Args:
            base_url: HAPI FHIR base URL (e.g., 'https://fhir.example.org/fhir')
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for transient failures
            api_key: Optional API key for authentication
        """
        super().__init__(
            service_name=SERVICE_NAME,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._api_key = api_key
        self._logger = get_logger(__name__)

    def _get_headers(self) -> dict[str, str]:
        """Build HTTP headers for FHIR requests."""
        headers = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _handle_fhir_error(self, response: httpx.Response) -> None:
        """Handle FHIR OperationOutcome errors.

        Args:
            response: HTTP response from FHIR server

        Raises:
            ExternalServiceException: Always raises with FHIR error details
        """
        try:
            outcome = response.json()
            if outcome.get("resourceType") == "OperationOutcome":
                issues = outcome.get("issue", [])
                error_msg = "; ".join(
                    issue.get("diagnostics", "Unknown error") for issue in issues
                )
                self._logger.error(
                    "FHIR OperationOutcome error",
                    extra={
                        "status_code": response.status_code,
                        "issues_count": len(issues),
                    },
                )
                raise ExternalServiceException(
                    service=SERVICE_NAME,
                    operation="fhir_request",
                    message=f"FHIR error: {error_msg}",
                    status_code=response.status_code,
                )
        except Exception as e:
            if isinstance(e, ExternalServiceException):
                raise
            self._logger.error(
                "Failed to parse FHIR error response",
                extra={"status_code": response.status_code},
            )

        raise ExternalServiceException(
            service=SERVICE_NAME,
            operation="fhir_request",
            message=f"HTTP {response.status_code}: {response.text[:200]}",
            status_code=response.status_code,
        )

    @track_api_call(service_name=SERVICE_NAME)
    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """Read a single FHIR resource by ID."""
        url = f"{self._base_url}/{resource_type}/{resource_id}"
        self._logger.debug(
            "Reading FHIR resource",
            extra={"resource_type": resource_type, "resource_id": "[REDACTED]"},
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=self._get_headers())

                if response.status_code == 200:
                    return response.json()

                self._handle_fhir_error(response)

        except httpx.TimeoutException as e:
            self._logger.error("FHIR read timeout", extra={"resource_type": resource_type})
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="read",
                message=f"Timeout reading {resource_type}",
            ) from e
        except httpx.RequestError as e:
            self._logger.error(
                "FHIR read connection error", extra={"resource_type": resource_type}
            )
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="read",
                message=f"Connection error: {str(e)}",
            ) from e

    @track_api_call(service_name=SERVICE_NAME)
    async def search(
        self, resource_type: str, params: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Search for FHIR resources."""
        url = f"{self._base_url}/{resource_type}"
        self._logger.debug(
            "Searching FHIR resources",
            extra={"resource_type": resource_type, "params_count": len(params)},
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url, params=params, headers=self._get_headers()
                )

                if response.status_code == 200:
                    bundle = response.json()
                    if bundle.get("resourceType") == "Bundle":
                        entries = bundle.get("entry", [])
                        return [entry.get("resource", {}) for entry in entries]
                    return []

                self._handle_fhir_error(response)

        except httpx.TimeoutException as e:
            self._logger.error("FHIR search timeout", extra={"resource_type": resource_type})
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="search",
                message=f"Timeout searching {resource_type}",
            ) from e
        except httpx.RequestError as e:
            self._logger.error(
                "FHIR search connection error", extra={"resource_type": resource_type}
            )
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="search",
                message=f"Connection error: {str(e)}",
            ) from e

    @track_api_call(service_name=SERVICE_NAME)
    async def create(
        self, resource_type: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new FHIR resource."""
        url = f"{self._base_url}/{resource_type}"
        self._logger.debug("Creating FHIR resource", extra={"resource_type": resource_type})

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url, json=resource, headers=self._get_headers()
                )

                if response.status_code == 201:
                    return response.json()

                self._handle_fhir_error(response)

        except httpx.TimeoutException as e:
            self._logger.error("FHIR create timeout", extra={"resource_type": resource_type})
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="create",
                message=f"Timeout creating {resource_type}",
            ) from e
        except httpx.RequestError as e:
            self._logger.error(
                "FHIR create connection error", extra={"resource_type": resource_type}
            )
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="create",
                message=f"Connection error: {str(e)}",
            ) from e

    @track_api_call(service_name=SERVICE_NAME)
    async def update(
        self, resource_type: str, resource_id: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing FHIR resource."""
        url = f"{self._base_url}/{resource_type}/{resource_id}"
        self._logger.debug(
            "Updating FHIR resource",
            extra={"resource_type": resource_type, "resource_id": "[REDACTED]"},
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.put(
                    url, json=resource, headers=self._get_headers()
                )

                if response.status_code == 200:
                    return response.json()

                self._handle_fhir_error(response)

        except httpx.TimeoutException as e:
            self._logger.error("FHIR update timeout", extra={"resource_type": resource_type})
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="update",
                message=f"Timeout updating {resource_type}",
            ) from e
        except httpx.RequestError as e:
            self._logger.error(
                "FHIR update connection error", extra={"resource_type": resource_type}
            )
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="update",
                message=f"Connection error: {str(e)}",
            ) from e

    async def get_patient(self, patient_id: str) -> dict[str, Any]:
        """Get patient resource by ID."""
        return await self.read("Patient", patient_id)

    async def get_coverage(self, patient_id: str) -> list[dict[str, Any]]:
        """Get all coverage resources for a patient."""
        return await self.search("Coverage", {"patient": patient_id})

    async def get_encounter(self, encounter_id: str) -> dict[str, Any]:
        """Get encounter resource by ID."""
        return await self.read("Encounter", encounter_id)

    async def get_claim(self, claim_id: str) -> dict[str, Any]:
        """Get claim resource by ID."""
        return await self.read("Claim", claim_id)


class StubFHIRClient(FHIRClientProtocol):
    """Test stub for FHIR client.

    Returns predefined responses for integration testing.
    Does not make real HTTP requests.
    """

    def __init__(self) -> None:
        """Initialize stub client."""
        self._resources: dict[tuple[str, str], dict[str, Any]] = {}
        self._logger = get_logger(__name__)

    def add_resource(
        self, resource_type: str, resource_id: str, resource: dict[str, Any]
    ) -> None:
        """Add a resource to the stub store."""
        self._resources[(resource_type, resource_id)] = resource

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """Read from stub store."""
        await asyncio.sleep(0.01)  # Simulate network delay
        key = (resource_type, resource_id)
        if key not in self._resources:
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="read",
                message=f"Resource not found: {resource_type}/{resource_id}",
                status_code=404,
            )
        return self._resources[key]

    async def search(
        self, resource_type: str, params: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Search stub store."""
        await asyncio.sleep(0.01)
        results = []
        for (rtype, _), resource in self._resources.items():
            if rtype == resource_type:
                results.append(resource)
        return results

    async def create(
        self, resource_type: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        """Create in stub store."""
        await asyncio.sleep(0.01)
        resource_id = f"stub-{len(self._resources)}"
        resource["id"] = resource_id
        self._resources[(resource_type, resource_id)] = resource
        return resource

    async def update(
        self, resource_type: str, resource_id: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        """Update in stub store."""
        await asyncio.sleep(0.01)
        key = (resource_type, resource_id)
        if key not in self._resources:
            raise ExternalServiceException(
                service=SERVICE_NAME,
                operation="update",
                message=f"Resource not found: {resource_type}/{resource_id}",
                status_code=404,
            )
        self._resources[key] = resource
        return resource

    async def get_patient(self, patient_id: str) -> dict[str, Any]:
        """Get patient from stub."""
        return await self.read("Patient", patient_id)

    async def get_coverage(self, patient_id: str) -> list[dict[str, Any]]:
        """Get coverage from stub."""
        return await self.search("Coverage", {"patient": patient_id})

    async def get_encounter(self, encounter_id: str) -> dict[str, Any]:
        """Get encounter from stub."""
        return await self.read("Encounter", encounter_id)

    async def get_claim(self, claim_id: str) -> dict[str, Any]:
        """Get claim from stub."""
        return await self.read("Claim", claim_id)
