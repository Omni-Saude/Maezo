"""LIS (Laboratory Information System) HTTP client."""

from typing import List, Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from revenue_cycle.config import Settings, get_settings
from revenue_cycle.integrations.lis.models import LISOrderDTO, LISResultDTO

logger = structlog.get_logger(__name__)


class LISClientError(Exception):
    """Base exception for LIS client errors."""

    pass


class LISClient:
    """
    LIS integration client for laboratory results.

    Provides async methods to retrieve lab orders and results for
    clinical documentation and glosa appeal evidence gathering.

    Example:
        client = LISClient(settings)
        order = await client.get_lab_order("12345")
        results = await client.get_lab_results("12345")
        evidence = await client.search_results_by_encounter("ENC-001")
    """

    def __init__(self, settings: Optional[Settings] = None, tenant_id: Optional[str] = None):
        """
        Initialize LIS client.

        Args:
            settings: Application settings
            tenant_id: Tenant identifier for multi-tenant deployments
        """
        self._settings = settings or get_settings()
        self._tenant_id = tenant_id
        self._base_url = self._settings.integration.lis_base_url
        self._timeout = httpx.Timeout(30.0, connect=5.0)
        # Connection pooling limits for better performance
        self._limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_headers(self) -> dict:
        """Get HTTP headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._tenant_id:
            headers["X-Tenant-ID"] = self._tenant_id
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create shared HTTP client with connection pooling."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=self._limits,
                http2=True,  # Enable HTTP/2 for better performance
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_lab_order(self, order_id: str) -> LISOrderDTO:
        """
        Get lab order details.

        Args:
            order_id: Lab order ID

        Returns:
            Lab order details

        Raises:
            LISClientError: If order retrieval fails
            httpx.HTTPError: On HTTP errors
        """
        url = f"{self._base_url}/orders/{order_id}"

        try:
            client = await self._get_client()
            logger.info("Fetching lab order", order_id=order_id, tenant_id=self._tenant_id)
            response = await client.get(url, headers=self._get_headers())
            response.raise_for_status()

            data = response.json()
            order = LISOrderDTO.model_validate(data)

            logger.info(
                "Lab order retrieved",
                order_id=order_id,
                status=order.status,
                patient_id=order.patient_id,
            )
            return order

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error fetching lab order",
                order_id=order_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise LISClientError(f"Failed to fetch lab order {order_id}: {e}") from e
        except httpx.HTTPError as e:
            logger.error("Network error fetching lab order", order_id=order_id, error=str(e))
            raise LISClientError(f"Network error fetching lab order {order_id}: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_lab_results(self, order_id: str) -> List[LISResultDTO]:
        """
        Get lab results for order.

        Args:
            order_id: Lab order ID

        Returns:
            List of lab results

        Raises:
            LISClientError: If results retrieval fails
        """
        url = f"{self._base_url}/orders/{order_id}/results"

        try:
            client = await self._get_client()
            logger.info("Fetching lab results", order_id=order_id, tenant_id=self._tenant_id)
            response = await client.get(url, headers=self._get_headers())
            response.raise_for_status()

            data = response.json()
            results = [LISResultDTO.model_validate(item) for item in data.get("results", [])]

            logger.info(
                "Lab results retrieved",
                order_id=order_id,
                result_count=len(results),
            )
            return results

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error fetching lab results",
                order_id=order_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise LISClientError(f"Failed to fetch lab results for order {order_id}: {e}") from e
        except httpx.HTTPError as e:
            logger.error("Network error fetching lab results", order_id=order_id, error=str(e))
            raise LISClientError(f"Network error fetching lab results for order {order_id}: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def search_results_by_encounter(self, encounter_id: str) -> List[LISResultDTO]:
        """
        Search lab results by encounter ID for appeal evidence.

        This method retrieves all lab results associated with a specific
        encounter/hospitalization, useful for glosa appeals and clinical audits.

        Args:
            encounter_id: Encounter/hospitalization ID

        Returns:
            List of lab results for the encounter

        Raises:
            LISClientError: If search fails
        """
        url = f"{self._base_url}/results/search"
        params = {"encounterId": encounter_id}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.info(
                    "Searching lab results by encounter",
                    encounter_id=encounter_id,
                    tenant_id=self._tenant_id,
                )
                response = await client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()

                data = response.json()
                results = [LISResultDTO.model_validate(item) for item in data.get("results", [])]

                logger.info(
                    "Encounter lab results retrieved",
                    encounter_id=encounter_id,
                    result_count=len(results),
                )
                return results

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error searching lab results",
                encounter_id=encounter_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise LISClientError(
                f"Failed to search lab results for encounter {encounter_id}: {e}"
            ) from e
        except httpx.HTTPError as e:
            logger.error(
                "Network error searching lab results", encounter_id=encounter_id, error=str(e)
            )
            raise LISClientError(
                f"Network error searching lab results for encounter {encounter_id}: {e}"
            ) from e
