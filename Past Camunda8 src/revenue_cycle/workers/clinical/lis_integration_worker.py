"""
LisIntegrationWorker - Zeebe worker for LIS (Laboratory Information System) integration.

This worker integrates with the LIS to retrieve lab results.

Topic: lis-integration
BPMN Task: Task_LIS_Integration

Business Rule: RN-LISIntegrationDelegate.md (RN-CLINICAL-005)
Regulatory Compliance: HL7 FHIR R4, LOINC standards, ANS documentation requirements
Migrated from: com.hospital.revenuecycle.delegates.clinical.LISIntegrationDelegate
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.clinical.clinical_models import (
    LisIntegrationInput,
    LisIntegrationOutput,
    LabResult,
    LabStatus,
)

logger = structlog.get_logger(__name__)


@worker(topic="lis-integration", max_jobs=8, lock_duration=30000)
class LisIntegrationWorker(BaseWorker):
    """
    Zeebe worker for LIS integration.

    BPMN Task: Task_LIS_Integration
    Topic: lis-integration

    This worker:
    - Retrieves lab orders from LIS
    - Collects lab results
    - Handles missing orders
    - Tracks integration status

    Input Variables:
        - encounterId: Encounter identifier (required)
        - labOrderIds: List of lab order identifiers (required)
        - tenantId: Tenant identifier (required)

    Output Variables:
        - encounterId: Encounter identifier
        - labResults: List of lab results
        - integrationStatus: Status of integration
        - integrationTimestamp: Integration timestamp
        - missingOrders: List of missing order IDs
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "lis_integration"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the LIS integration task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with lab results
        """
        self._logger.info(
            "Processing LIS integration",
            encounter_id=variables.get("encounterId"),
        )

        try:
            # Validate input
            input_data = LisIntegrationInput(**variables)

            # Retrieve lab results
            lab_results = []
            missing_orders = []

            for order_id in input_data.lab_order_ids:
                result = await self._retrieve_lab_result(order_id)
                if result:
                    lab_results.append(result)
                else:
                    missing_orders.append(order_id)

            # Determine integration status
            status = "SUCCESS" if not missing_orders else "PARTIAL"

            output = LisIntegrationOutput(
                encounterId=input_data.encounter_id,
                labResults=lab_results,
                integrationStatus=status,
                integrationTimestamp=datetime.utcnow(),
                missingOrders=missing_orders,
            )

            self._logger.info(
                "LIS integration completed",
                encounter_id=input_data.encounter_id,
                results_retrieved=len(lab_results),
                missing_orders=len(missing_orders),
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Error in LIS integration",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"LIS integration failed: {e}",
                retry=True,
            )

    async def _retrieve_lab_result(self, order_id: str) -> LabResult | None:
        """Retrieve a lab result by order ID."""
        # Mock implementation - in real scenario, query LIS system
        if order_id.startswith("ORDER-"):
            return LabResult(
                testCode="TEST-001",
                testName="Blood Test",
                resultValue="Normal",
                referenceRange="Normal",
                unit="Result",
                collectedDate=datetime.utcnow(),
                resultDate=datetime.utcnow(),
                status=LabStatus.COMPLETED,
            )
        return None
