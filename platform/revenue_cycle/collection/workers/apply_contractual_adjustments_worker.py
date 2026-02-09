from __future__ import annotations

from decimal import Decimal
from typing import Any

from platform.revenue_cycle.collection.entities import PaymentAllocation
from platform.revenue_cycle.collection.enums import AllocationStatus, DiscrepancyType
from platform.shared.domain.value_objects import FHIRReference, Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class ApplyContractualAdjustmentsWorker:
    """Applies contractual adjustments between expected and contracted rates."""

    WORKER_TYPE = "apply_contractual_adjustments"

    @track_task_execution(metric_name="apply_contractual_adjustments")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Apply contractual adjustments (desconto contratual) to payment allocation.

        Args:
            task_variables: {
                "payment_id": str,
                "claim_id": str,
                "billed_amount": float (tabela hospital),
                "contracted_amount": float (tabela convênio),
                "payment_amount": float,
                "currency": str,
                "payer_id": str
            }

        Returns:
            {
                "allocation_id": str,
                "contractual_discount": float,
                "discount_percent": float,
                "final_amount": float,
                "adjustment_applied": bool
            }
        """
        payment_id = task_variables["payment_id"]
        claim_id = task_variables["claim_id"]
        billed_amount = Decimal(str(task_variables["billed_amount"]))
        contracted_amount = Decimal(str(task_variables["contracted_amount"]))
        payment_amount = Decimal(str(task_variables["payment_amount"]))
        currency = task_variables.get("currency", "BRL")
        payer_id = task_variables["payer_id"]

        logger.info(
            _("Aplicando ajustes contratuais"),
            extra={
                "payment_id": payment_id,
                "claim_id": claim_id,
                "billed": float(billed_amount),
                "contracted": float(contracted_amount),
            },
        )

        # Calculate contractual discount
        contractual_discount = billed_amount - contracted_amount
        discount_percent = (contractual_discount / billed_amount * 100) if billed_amount > 0 else Decimal("0")

        # Verify payment matches contracted amount
        variance = payment_amount - contracted_amount
        adjustment_applied = abs(variance) < Decimal("0.01")

        # Create allocation with contractual adjustment
        allocation = PaymentAllocation(
            id=f"ALLOC-{payment_id}-{claim_id}",
            payment_id=payment_id,
            claim_reference=FHIRReference(reference=f"Claim/{claim_id}"),
            allocated_amount=Money(amount=payment_amount, currency=currency),
            expected_amount=Money(amount=contracted_amount, currency=currency),
            variance=Money(amount=variance, currency=currency),
            status=AllocationStatus.FULLY_ALLOCATED if adjustment_applied else AllocationStatus.ESCALATED,
            match_method="contractual",
            match_confidence=Decimal("0.95"),
            discrepancy_type=DiscrepancyType.CONTRACTUAL_ADJUSTMENT if adjustment_applied else None,
        )

        logger.info(
            _("Ajustes contratuais aplicados"),
            extra={
                "allocation_id": allocation.id,
                "discount": float(contractual_discount),
                "discount_percent": float(discount_percent),
                "variance": float(variance),
            },
        )

        return {
            "allocation_id": allocation.id,
            "contractual_discount": float(contractual_discount),
            "discount_percent": float(discount_percent),
            "final_amount": float(payment_amount),
            "adjustment_applied": adjustment_applied,
            "variance": float(variance),
        }
