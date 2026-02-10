from __future__ import annotations

from decimal import Decimal
from typing import Any

from healthcare_platform.revenue_cycle.collection.entities import PaymentAllocation
from healthcare_platform.revenue_cycle.collection.enums import AllocationStatus
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import FHIRReference, Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class PartialAllocationWorker:
    """Handles partial payments - allocates payment across multiple claims by priority."""

    WORKER_TYPE = "partial_allocation"

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

    @track_task_execution(metric_name="partial_allocation")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Allocate partial payment across multiple claims (oldest first).

        Args:
            task_variables: {
                "payment_id": str,
                "payment_amount": float,
                "currency": str,
                "available_claims": list[dict] - sorted by due date (oldest first)
            }

        Returns:
            {
                "allocations": list[dict],
                "total_allocated": float,
                "remaining_amount": float,
                "claims_paid": int,
                "claims_partial": int
            }
        """
        payment_id = task_variables["payment_id"]
        payment_amount = Decimal(str(task_variables["payment_amount"]))
        currency = task_variables.get("currency", "BRL")
        available_claims = task_variables.get("available_claims", [])

        logger.info(
            _("Iniciando alocação parcial de pagamento"),
            extra={"payment_id": payment_id, "amount": float(payment_amount), "claims": len(available_claims)},
        )

        allocations = []
        remaining = payment_amount
        claims_fully_paid = 0
        claims_partially_paid = 0

        # Sort by due date (oldest first)
        sorted_claims = sorted(available_claims, key=lambda c: c.get("due_date", "9999-12-31"))

        for claim in sorted_claims:
            if remaining <= 0:
                break

            claim_id = claim["claim_id"]
            claim_amount = Decimal(str(claim.get("outstanding_amount", claim.get("total_amount", 0))))

            if claim_amount <= 0:
                continue

            # Allocate as much as possible to this claim
            allocated = min(remaining, claim_amount)

            allocation = PaymentAllocation(
                id=f"ALLOC-{payment_id}-{claim_id}",
                payment_id=payment_id,
                claim_reference=FHIRReference(reference=f"Claim/{claim_id}"),
                allocated_amount=Money(amount=allocated, currency=currency),
                expected_amount=Money(amount=claim_amount, currency=currency),
                variance=Money(amount=allocated - claim_amount, currency=currency),
                status=AllocationStatus.FULLY_ALLOCATED if allocated == claim_amount else AllocationStatus.PARTIALLY_ALLOCATED,
                match_method="partial",
                match_confidence=Decimal("0.90"),
            )

            allocations.append({
                "allocation_id": allocation.id,
                "claim_id": claim_id,
                "allocated_amount": float(allocated),
                "claim_amount": float(claim_amount),
                "fully_paid": allocated == claim_amount,
            })

            if allocated == claim_amount:
                claims_fully_paid += 1
            else:
                claims_partially_paid += 1

            remaining -= allocated

        logger.info(
            _("Alocação parcial concluída"),
            extra={
                "payment_id": payment_id,
                "allocations_count": len(allocations),
                "remaining": float(remaining),
                "fully_paid": claims_fully_paid,
                "partially_paid": claims_partially_paid,
            },
        )

        return {
            "allocations": allocations,
            "total_allocated": float(payment_amount - remaining),
            "remaining_amount": float(remaining),
            "claims_paid": claims_fully_paid,
            "claims_partial": claims_partially_paid,
        }
