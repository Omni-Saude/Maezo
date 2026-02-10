from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from healthcare_platform.revenue_cycle.collection.entities import PaymentAllocation
from healthcare_platform.revenue_cycle.collection.enums import AllocationStatus
from healthcare_platform.revenue_cycle.collection.exceptions import PaymentAllocationError
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class FinalizeAllocationWorker:
    """Locks final allocation - no further changes allowed after finalization."""

    WORKER_TYPE = "finalize_allocation"

    def __init__(self) -> None:
        self.dmn_service = FederatedDMNService()
        self._logger = get_logger(__name__)

    def _evaluate_cash_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate cash_operations DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id='default',
                category='cash_operations',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    @track_task_execution(metric_name="finalize_allocation")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Finalize and lock payment allocation.

        Args:
            task_variables: {
                "allocation_id": str,
                "locked_by": str (user or system identifier),
                "force_lock": bool (default: false)
            }

        Returns:
            {
                "allocation_id": str,
                "status": str,
                "locked_at": str (ISO timestamp),
                "locked_by": str,
                "finalized": bool
            }
        """
        allocation_id = task_variables["allocation_id"]
        locked_by = task_variables["locked_by"]
        force_lock = task_variables.get("force_lock", False)

        logger.info(
            _("Finalizando alocação de pagamento"),
            extra={"allocation_id": allocation_id, "locked_by": locked_by},
        )

        # In production, fetch allocation from database
        # For now, create a mock allocation object
        allocation_data = task_variables.get("allocation_data", {})

        # Check if already locked
        if allocation_data.get("locked_at") and not force_lock:
            raise PaymentAllocationError(
                _("Alocação já está bloqueada e não pode ser modificada"),
                details={
                    "allocation_id": allocation_id,
                    "locked_at": allocation_data.get("locked_at"),
                    "locked_by": allocation_data.get("locked_by"),
                },
            )

        # Lock allocation
        locked_at = datetime.now(timezone.utc)

        logger.info(
            _("Alocação finalizada e bloqueada"),
            extra={
                "allocation_id": allocation_id,
                "locked_at": locked_at.isoformat(),
                "locked_by": locked_by,
            },
        )

        return {
            "allocation_id": allocation_id,
            "status": AllocationStatus.LOCKED.value,
            "locked_at": locked_at.isoformat(),
            "locked_by": locked_by,
            "finalized": True,
        }
