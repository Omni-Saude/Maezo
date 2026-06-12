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

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.base import BaseIntegrationClient, IntegrationSettings
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_api_call

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

    @abstractmethod
    async def conditional_update(
        self,
        resource_type: str,
        resource: dict[str, Any],
        identifier_system: str,
        identifier_value: str,
    ) -> dict[str, Any]:
        """Create or update a FHIR resource by identifier (upsert).

        Uses FHIR conditional update: PUT Resource?identifier=system|value.
        Creates the resource if it doesn't exist, updates if it does.

        Args:
            resource_type: FHIR resource type (e.g., 'Patient')
            resource: FHIR resource content
            identifier_system: Identifier system URI
            identifier_value: Identifier value

        Returns:
            Created or updated resource

        Raises:
            ExternalServiceException: On FHIR errors or connectivity issues
        """
        ...

    @abstractmethod
    async def execute_bundle(
        self, entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute a FHIR Transaction Bundle atomically.

        Posts a Bundle with type=transaction to the FHIR server base URL.
        All entries succeed or all fail.

        Args:
            entries: List of Bundle entries, each with 'resource' and 'request' keys

        Returns:
            Response Bundle with entry results

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
        settings = IntegrationSettings(
            base_url=base_url,
            timeout_seconds=timeout,
            max_retries=max_retries,
        )
        super().__init__(settings)
        self.SERVICE_NAME = SERVICE_NAME
        self._base_url = base_url
        self._timeout = timeout
        self._api_key = api_key
        self._logger = get_logger(__name__)

    def _get_headers(self) -> dict[str, str]:
        """Build HTTP headers for FHIR requests."""
        headers: dict[str, str] = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        # Tomcat 10.1+ rejects hostnames with underscore per RFC 7230.
        # Override Host header when base_url contains underscore.
        if "_" in self._base_url:
            headers["Host"] = "localhost:8080"
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
                    _("Erro FHIR: {}").format(error_msg),
                    service_name=SERVICE_NAME,
                    operation="fhir_request",
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
            _("HTTP {}: {}").format(response.status_code, response.text[:200]),
            service_name=SERVICE_NAME,
            operation="fhir_request",
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
                _("Tempo limite excedido ao ler {}").format(resource_type),
                service_name=SERVICE_NAME,
                operation="read",
            ) from e
        except httpx.RequestError as e:
            self._logger.error(
                "FHIR read connection error", extra={"resource_type": resource_type}
            )
            raise ExternalServiceException(
                _("Erro de conexão: {}").format(str(e)),
                service_name=SERVICE_NAME,
                operation="read",
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
                _("Tempo limite excedido ao buscar {}").format(resource_type),
                service_name=SERVICE_NAME,
                operation="search",
            ) from e
        except httpx.RequestError as e:
            self._logger.error(
                "FHIR search connection error", extra={"resource_type": resource_type}
            )
            raise ExternalServiceException(
                _("Erro de conexão: {}").format(str(e)),
                service_name=SERVICE_NAME,
                operation="search",
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
                _("Tempo limite excedido ao criar {}").format(resource_type),
                service_name=SERVICE_NAME,
                operation="create",
            ) from e
        except httpx.RequestError as e:
            self._logger.error(
                "FHIR create connection error", extra={"resource_type": resource_type}
            )
            raise ExternalServiceException(
                _("Erro de conexão: {}").format(str(e)),
                service_name=SERVICE_NAME,
                operation="create",
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
                _("Tempo limite excedido ao atualizar {}").format(resource_type),
                service_name=SERVICE_NAME,
                operation="update",
            ) from e
        except httpx.RequestError as e:
            self._logger.error(
                "FHIR update connection error", extra={"resource_type": resource_type}
            )
            raise ExternalServiceException(
                _("Erro de conexão: {}").format(str(e)),
                service_name=SERVICE_NAME,
                operation="update",
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

    @track_api_call(service_name=SERVICE_NAME)
    async def conditional_update(
        self,
        resource_type: str,
        resource: dict[str, Any],
        identifier_system: str,
        identifier_value: str,
    ) -> dict[str, Any]:
        """Create or update a FHIR resource by identifier (upsert)."""
        url = f"{self._base_url}/{resource_type}"
        params = {"identifier": f"{identifier_system}|{identifier_value}"}
        self._logger.debug(
            "Conditional update FHIR resource",
            extra={"resource_type": resource_type},
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.put(
                    url, json=resource, params=params, headers=self._get_headers()
                )

                self._logger.debug(
                    "FHIR conditional_update response",
                    extra={
                        "status_code": response.status_code,
                        "url": str(response.url),
                        "body_preview": response.text[:200] if response.status_code >= 400 else "",
                    },
                )

                if response.status_code in (200, 201):
                    return response.json()

                self._handle_fhir_error(response)

        except httpx.TimeoutException as e:
            self._logger.error(
                "FHIR conditional_update timeout",
                extra={"resource_type": resource_type},
            )
            raise ExternalServiceException(
                _("Tempo limite excedido ao upsert {}").format(resource_type),
                service_name=SERVICE_NAME,
                operation="conditional_update",
            ) from e
        except httpx.RequestError as e:
            self._logger.error(
                "FHIR conditional_update connection error",
                extra={"resource_type": resource_type},
            )
            raise ExternalServiceException(
                _("Erro de conexão: {}").format(str(e)),
                service_name=SERVICE_NAME,
                operation="conditional_update",
            ) from e

    @track_api_call(service_name=SERVICE_NAME)
    async def execute_bundle(
        self, entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute a FHIR Transaction Bundle atomically."""
        bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": entries,
        }
        url = self._base_url
        self._logger.debug(
            "Executing FHIR transaction bundle",
            extra={"entries_count": len(entries)},
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url, json=bundle, headers=self._get_headers()
                )

                if response.status_code == 200:
                    return response.json()

                self._handle_fhir_error(response)

        except httpx.TimeoutException as e:
            self._logger.error("FHIR bundle timeout")
            raise ExternalServiceException(
                _("Tempo limite excedido ao executar bundle"),
                service_name=SERVICE_NAME,
                operation="execute_bundle",
            ) from e
        except httpx.RequestError as e:
            self._logger.error("FHIR bundle connection error")
            raise ExternalServiceException(
                _("Erro de conexão: {}").format(str(e)),
                service_name=SERVICE_NAME,
                operation="execute_bundle",
            ) from e


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
                _("Recurso não encontrado: {}/{}").format(resource_type, resource_id),
                service_name=SERVICE_NAME,
                operation="read",
                status_code=404,
            )
        return self._resources[key]

    async def search(
        self, resource_type: str, params: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Search stub store."""
        await asyncio.sleep(0.01)
        results = []
        for (rtype, _rid), resource in self._resources.items():
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
                _("Recurso não encontrado: {}/{}").format(resource_type, resource_id),
                service_name=SERVICE_NAME,
                operation="update",
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

    async def conditional_update(
        self,
        resource_type: str,
        resource: dict[str, Any],
        identifier_system: str,
        identifier_value: str,
    ) -> dict[str, Any]:
        """Conditional update in stub store (upsert by identifier)."""
        await asyncio.sleep(0.01)
        resource_id = resource.get("id", f"stub-{identifier_value}")
        resource["id"] = resource_id
        self._resources[(resource_type, resource_id)] = resource
        return resource

    async def execute_bundle(
        self, entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute bundle in stub store."""
        await asyncio.sleep(0.01)
        result_entries = []
        for entry in entries:
            res = entry.get("resource", {})
            rtype = res.get("resourceType", "Unknown")
            resource_id = res.get("id", f"stub-{len(self._resources)}")
            res["id"] = resource_id
            self._resources[(rtype, resource_id)] = res
            result_entries.append({"resource": res, "response": {"status": "200 OK"}})
        return {"resourceType": "Bundle", "type": "transaction-response", "entry": result_entries}
