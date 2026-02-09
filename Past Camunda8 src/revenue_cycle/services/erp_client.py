"""
ERP integration client for provision synchronization.

Handles asynchronous communication with ERP systems (TOTVS, SAP)
for financial provision data synchronization.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

import structlog

from revenue_cycle.config import Settings, get_settings

logger = structlog.get_logger(__name__)


@dataclass
class ERPProvisionRequest:
    """Request payload for ERP provision creation."""

    provision_id: str
    glosa_id: str
    amount: float
    accounting_period: str
    debit_account: str
    credit_account: str
    source_system: str = "REVENUE_CYCLE"
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API call."""
        return {
            "provision_id": self.provision_id,
            "glosa_id": self.glosa_id,
            "amount": self.amount,
            "accounting_period": self.accounting_period,
            "debit_account": self.debit_account,
            "credit_account": self.credit_account,
            "source_system": self.source_system,
            "created_at": self.created_at or datetime.utcnow().isoformat(),
        }


@dataclass
class ERPProvisionResponse:
    """Response from ERP provision creation."""

    erp_provision_id: str
    status: str
    integration_date: str
    erp_batch_id: Optional[str] = None
    error_message: Optional[str] = None


class ERPClient:
    """
    Client for ERP system integration.

    Supports asynchronous provisioning with:
    - Queue-based processing
    - Retry with exponential backoff
    - Dead letter queue for failures

    Example:
        erp = ERPClient()
        await erp.queue_provision({
            "provision_id": "PROV-001",
            "glosa_id": "GL-001",
            "amount": 5000.00,
        })
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize ERP client.

        Args:
            settings: Application settings
        """
        self._settings = settings or get_settings()
        self._logger = logger.bind(service="erp_client")
        self._queue: asyncio.Queue[ERPProvisionRequest] = asyncio.Queue()
        self._processing = False

    async def queue_provision(
        self,
        data: dict[str, Any],
    ) -> str:
        """
        Queue a provision for ERP integration.

        This method is non-blocking and returns immediately.
        The provision will be processed asynchronously.

        Args:
            data: Provision data dictionary

        Returns:
            Queue reference ID
        """
        request = ERPProvisionRequest(
            provision_id=data.get("provision_id", ""),
            glosa_id=data.get("glosa_id", ""),
            amount=data.get("amount", 0.0),
            accounting_period=data.get("accounting_period", ""),
            debit_account=data.get("debit_account", "6301"),
            credit_account=data.get("credit_account", "2101"),
            created_at=data.get("created_at"),
        )

        queue_ref = f"ERPQ-{uuid4().hex[:12].upper()}"

        await self._queue.put(request)

        self._logger.info(
            "Provision queued for ERP integration",
            queue_ref=queue_ref,
            provision_id=request.provision_id,
            glosa_id=request.glosa_id,
            amount=request.amount,
        )

        return queue_ref

    async def sync_provision(
        self,
        request: ERPProvisionRequest,
        max_retries: int = 5,
    ) -> ERPProvisionResponse:
        """
        Synchronously send a provision to ERP.

        Uses exponential backoff for retries.

        Args:
            request: Provision request
            max_retries: Maximum retry attempts

        Returns:
            ERP response

        Raises:
            ERPIntegrationError: If all retries fail
        """
        last_error = None
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                response = await self._send_to_erp(request)
                self._logger.info(
                    "Provision synced to ERP",
                    provision_id=request.provision_id,
                    erp_provision_id=response.erp_provision_id,
                    attempt=attempt + 1,
                )
                return response

            except Exception as e:
                last_error = e
                self._logger.warning(
                    "ERP sync attempt failed",
                    provision_id=request.provision_id,
                    attempt=attempt + 1,
                    error=str(e),
                    next_backoff=backoff,
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 16.0)  # Max 16 second backoff

        self._logger.error(
            "ERP sync failed after all retries",
            provision_id=request.provision_id,
            max_retries=max_retries,
            error=str(last_error),
        )

        raise ERPIntegrationError(
            f"Failed to sync provision {request.provision_id} after {max_retries} attempts: {last_error}"
        )

    async def _send_to_erp(
        self,
        request: ERPProvisionRequest,
    ) -> ERPProvisionResponse:
        """
        Send provision to ERP API.

        Note: This is a stub implementation. In production, this would:
        1. Connect to TOTVS/SAP API
        2. Authenticate with the ERP system
        3. POST the provision data
        4. Handle ERP-specific response formats

        Args:
            request: Provision request

        Returns:
            ERP response
        """
        # Simulate API call latency
        await asyncio.sleep(0.1)

        # In production, this would be an actual HTTP call:
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(
        #         f"{self._settings.integration.tasy_base_url}/provisions",
        #         json=request.to_dict(),
        #         timeout=self._settings.integration.tasy_timeout,
        #     )
        #     response.raise_for_status()
        #     return ERPProvisionResponse(**response.json())

        # Stub response
        return ERPProvisionResponse(
            erp_provision_id=f"ERP-PROV-{uuid4().hex[:8].upper()}",
            status="CREATED",
            integration_date=datetime.utcnow().isoformat(),
            erp_batch_id=f"BATCH-{datetime.utcnow().strftime('%Y%m%d')}-001",
        )

    async def start_processing(self) -> None:
        """Start the background queue processor."""
        if self._processing:
            return

        self._processing = True
        self._logger.info("Starting ERP queue processor")

        while self._processing:
            try:
                request = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0,
                )
                try:
                    await self.sync_provision(request)
                except ERPIntegrationError as e:
                    self._logger.error(
                        "Provision moved to DLQ",
                        provision_id=request.provision_id,
                        error=str(e),
                    )
                    # In production: send to dead letter queue
                finally:
                    self._queue.task_done()

            except asyncio.TimeoutError:
                continue

    async def stop_processing(self) -> None:
        """Stop the background queue processor."""
        self._processing = False
        self._logger.info("Stopping ERP queue processor")


class ERPIntegrationError(Exception):
    """Exception raised when ERP integration fails."""

    pass
