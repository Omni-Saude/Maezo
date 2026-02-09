"""Laboratory Information System (LIS) integration client.

Provides async interface for submitting lab orders, checking status, and retrieving results.
Uses circuit breaker, retry logic, and multi-tenant support via BaseIntegrationClient.
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from platform.shared.domain.exceptions import ExternalServiceException
from platform.shared.i18n import _
from platform.shared.integrations.base import BaseIntegrationClient, IntegrationSettings
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_api_call

logger = get_logger(__name__)

SERVICE_NAME = "lis"


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class LabOrderStatus(str, enum.Enum):
    """Status of a laboratory order."""

    PENDING = "pending"
    RECEIVED = "received"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class LabOrderDTO(BaseModel):
    """Laboratory order submission payload."""

    patient_id: str = Field(..., description="Patient identifier")
    encounter_id: str = Field(..., description="Encounter/visit identifier")
    ordering_provider_id: str = Field(..., description="Provider who ordered the tests")
    test_codes: list[str] = Field(..., min_length=1, description="List of test codes (e.g., LOINC)")
    priority: str = Field(default="routine", description="Priority: routine, urgent, stat")
    clinical_notes: str | None = Field(default=None, description="Clinical notes/indication")
    specimen_type: str | None = Field(default=None, description="Specimen type (e.g., blood, urine)")

    class Config:
        frozen = True


class LabResultDTO(BaseModel):
    """Laboratory result for a single test."""

    test_code: str = Field(..., description="Test code (e.g., LOINC)")
    test_name: str = Field(..., description="Human-readable test name")
    result_value: str = Field(..., description="Result value")
    result_unit: str | None = Field(default=None, description="Unit of measure")
    reference_range: str | None = Field(default=None, description="Normal reference range")
    abnormal_flag: str | None = Field(default=None, description="Abnormal flag: L, H, LL, HH, A")
    result_status: str = Field(default="final", description="Status: preliminary, final, corrected")
    performed_at: str | None = Field(default=None, description="ISO8601 timestamp when test was performed")
    notes: str | None = Field(default=None, description="Result notes or comments")

    class Config:
        frozen = True


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class LISClientProtocol(ABC):
    """Protocol for LIS client implementations."""

    @abstractmethod
    async def submit_order(self, order: LabOrderDTO) -> str:
        """Submit a laboratory order to the LIS.

        Args:
            order: Laboratory order details

        Returns:
            order_id: Unique identifier for the submitted order

        Raises:
            ExternalServiceException: If submission fails
        """
        ...

    @abstractmethod
    async def get_order_status(self, order_id: str) -> LabOrderStatus:
        """Get current status of a laboratory order.

        Args:
            order_id: Order identifier

        Returns:
            Current status of the order

        Raises:
            ExternalServiceException: If status check fails
        """
        ...

    @abstractmethod
    async def get_results(self, order_id: str) -> list[LabResultDTO]:
        """Retrieve laboratory results for an order.

        Args:
            order_id: Order identifier

        Returns:
            List of lab results (may be empty if not yet completed)

        Raises:
            ExternalServiceException: If retrieval fails
        """
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending laboratory order.

        Args:
            order_id: Order identifier

        Returns:
            True if cancelled successfully, False if already completed/cancelled

        Raises:
            ExternalServiceException: If cancellation fails
        """
        ...


# ---------------------------------------------------------------------------
# Production Client
# ---------------------------------------------------------------------------


class LISClient(BaseIntegrationClient, LISClientProtocol):
    """Production LIS client using HTTP/REST integration."""

    SERVICE_NAME = SERVICE_NAME

    def __init__(self, settings: IntegrationSettings) -> None:
        super().__init__(settings)

    @track_api_call(service=SERVICE_NAME, endpoint="/orders", method="POST")
    async def submit_order(self, order: LabOrderDTO) -> str:
        """Submit laboratory order via REST API."""
        tenant = self._get_tenant_context()

        payload = order.model_dump()
        payload["tenant_id"] = tenant.tenant_id

        resp = await self._request("POST", "/orders", json=payload)
        data = resp.json()

        order_id = data.get("order_id")
        if not order_id:
            raise ExternalServiceException(
                _("LIS não retornou order_id"),
                service_name=self.SERVICE_NAME,
                operation="submit_order",
            )

        self._logger.info(
            "Lab order submitted",
            order_id=order_id,
            test_count=len(order.test_codes),
            priority=order.priority,
        )
        return order_id

    @track_api_call(service=SERVICE_NAME, endpoint="/orders/{order_id}", method="GET")
    async def get_order_status(self, order_id: str) -> LabOrderStatus:
        """Retrieve order status from LIS."""
        tenant = self._get_tenant_context()

        resp = await self._request(
            "GET",
            f"/orders/{order_id}",
            params={"tenant_id": tenant.tenant_id},
        )
        data = resp.json()

        status_str = data.get("status", "").lower()
        try:
            status = LabOrderStatus(status_str)
        except ValueError:
            raise ExternalServiceException(
                _("Status inválido do LIS: {}").format(status_str),
                service_name=self.SERVICE_NAME,
                operation="get_order_status",
            )

        self._logger.debug("Lab order status retrieved", order_id=order_id, status=status)
        return status

    @track_api_call(service=SERVICE_NAME, endpoint="/orders/{order_id}/results", method="GET")
    async def get_results(self, order_id: str) -> list[LabResultDTO]:
        """Retrieve lab results for an order."""
        tenant = self._get_tenant_context()

        resp = await self._request(
            "GET",
            f"/orders/{order_id}/results",
            params={"tenant_id": tenant.tenant_id},
        )
        data = resp.json()

        results_data = data.get("results", [])
        results = [LabResultDTO(**r) for r in results_data]

        self._logger.info(
            "Lab results retrieved",
            order_id=order_id,
            result_count=len(results),
        )
        return results

    @track_api_call(service=SERVICE_NAME, endpoint="/orders/{order_id}/cancel", method="POST")
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending lab order."""
        tenant = self._get_tenant_context()

        payload = {"tenant_id": tenant.tenant_id}
        resp = await self._request("POST", f"/orders/{order_id}/cancel", json=payload)
        data = resp.json()

        cancelled = data.get("cancelled", False)
        self._logger.info(
            "Lab order cancellation attempted",
            order_id=order_id,
            cancelled=cancelled,
        )
        return cancelled


# ---------------------------------------------------------------------------
# Test Stub
# ---------------------------------------------------------------------------


class StubLISClient(LISClientProtocol):
    """In-memory stub for testing without real LIS."""

    def __init__(self) -> None:
        self._orders: dict[str, dict[str, Any]] = {}
        self._order_counter = 0
        self._logger = get_logger(f"integration.{SERVICE_NAME}.stub")

    async def submit_order(self, order: LabOrderDTO) -> str:
        """Store order in memory and return synthetic ID."""
        self._order_counter += 1
        order_id = f"LIS-{self._order_counter:06d}"

        self._orders[order_id] = {
            "order": order,
            "status": LabOrderStatus.PENDING,
            "results": [],
        }

        self._logger.info(
            "Stub: Lab order submitted",
            order_id=order_id,
            test_count=len(order.test_codes),
        )
        return order_id

    async def get_order_status(self, order_id: str) -> LabOrderStatus:
        """Return status from in-memory store."""
        if order_id not in self._orders:
            raise ExternalServiceException(
                _("Pedido não encontrado: {}").format(order_id),
                service_name=SERVICE_NAME,
                operation="get_order_status",
            )

        status = self._orders[order_id]["status"]
        self._logger.debug("Stub: Status retrieved", order_id=order_id, status=status)
        return status

    async def get_results(self, order_id: str) -> list[LabResultDTO]:
        """Return results from in-memory store."""
        if order_id not in self._orders:
            raise ExternalServiceException(
                _("Pedido não encontrado: {}").format(order_id),
                service_name=SERVICE_NAME,
                operation="get_results",
            )

        results = self._orders[order_id]["results"]
        self._logger.info("Stub: Results retrieved", order_id=order_id, result_count=len(results))
        return results

    async def cancel_order(self, order_id: str) -> bool:
        """Mark order as cancelled in memory."""
        if order_id not in self._orders:
            raise ExternalServiceException(
                _("Pedido não encontrado: {}").format(order_id),
                service_name=SERVICE_NAME,
                operation="cancel_order",
            )

        order_data = self._orders[order_id]
        current_status = order_data["status"]

        # Can only cancel pending or received orders
        if current_status in (LabOrderStatus.COMPLETED, LabOrderStatus.CANCELLED):
            self._logger.info(
                "Stub: Cannot cancel order",
                order_id=order_id,
                status=current_status,
            )
            return False

        order_data["status"] = LabOrderStatus.CANCELLED
        self._logger.info("Stub: Order cancelled", order_id=order_id)
        return True

    # Helper methods for testing

    def set_order_status(self, order_id: str, status: LabOrderStatus) -> None:
        """Test helper: manually set order status."""
        if order_id in self._orders:
            self._orders[order_id]["status"] = status

    def add_result(self, order_id: str, result: LabResultDTO) -> None:
        """Test helper: manually add a result."""
        if order_id in self._orders:
            self._orders[order_id]["results"].append(result)
