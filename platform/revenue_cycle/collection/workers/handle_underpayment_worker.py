from __future__ import annotations

from decimal import Decimal
from typing import Any

from platform.revenue_cycle.collection.entities import PaymentAllocation
from platform.revenue_cycle.collection.enums import AllocationStatus, DiscrepancyType
from platform.revenue_cycle.collection.exceptions import UnderpaymentError
from platform.shared.domain.value_objects import FHIRReference, Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class HandleUnderpaymentWorker:
    """Handles underpayments - calculates shortfall and flags for collection."""

    WORKER_TYPE = "handle_underpayment"

    @track_task_execution(metric_name="handle_underpayment")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Handle underpayment scenario - check if it's a glosa or collection issue.

        Args:
            task_variables: {
                "payment_id": str,
                "claim_id": str,
                "payment_amount": float,
                "expected_amount": float,
                "currency": str,
                "glosa_amount": float (optional - known denials)
            }

        Returns:
            {
                "underpayment_amount": float,
                "is_glosa": bool,
                "requires_collection": bool,
                "allocation_id": str
            }

        Raises:
            UnderpaymentError: If underpayment exceeds threshold
        """
        payment_id = task_variables["payment_id"]
        claim_id = task_variables["claim_id"]
        payment_amount = Decimal(str(task_variables["payment_amount"]))
        expected_amount = Decimal(str(task_variables["expected_amount"]))
        currency = task_variables.get("currency", "BRL")
        glosa_amount = Decimal(str(task_variables.get("glosa_amount", 0)))

        underpayment = expected_amount - payment_amount

        logger.warning(
            _("Pagamento insuficiente detectado"),
            extra={
                "payment_id": payment_id,
                "claim_id": claim_id,
                "shortfall": float(underpayment),
                "payment_amount": float(payment_amount),
                "expected_amount": float(expected_amount),
            },
        )

        # Check if underpayment matches known glosa amount
        is_glosa = abs(underpayment - glosa_amount) < Decimal("0.01")
        requires_collection = not is_glosa and underpayment > Decimal("10.00")

        # Create allocation
        allocation = PaymentAllocation(
            id=f"ALLOC-{payment_id}-{claim_id}",
            payment_id=payment_id,
            claim_reference=FHIRReference(reference=f"Claim/{claim_id}"),
            allocated_amount=Money(amount=payment_amount, currency=currency),
            expected_amount=Money(amount=expected_amount, currency=currency),
            variance=Money(amount=-underpayment, currency=currency),
            status=AllocationStatus.PARTIALLY_ALLOCATED,
            match_method="underpayment",
            match_confidence=Decimal("0.80"),
            discrepancy_type=DiscrepancyType.UNDERPAYMENT,
        )

        logger.info(
            _("Pagamento insuficiente processado"),
            extra={
                "allocation_id": allocation.id,
                "is_glosa": is_glosa,
                "requires_collection": requires_collection,
            },
        )

        result = {
            "underpayment_amount": float(underpayment),
            "is_glosa": is_glosa,
            "requires_collection": requires_collection,
            "allocation_id": allocation.id,
        }

        # Raise error if collection is required
        if requires_collection:
            raise UnderpaymentError(
                _("Pagamento insuficiente requer cobrança: {amount} {currency}").format(
                    amount=float(underpayment), currency=currency
                ),
                details=result,
            )

        return result
