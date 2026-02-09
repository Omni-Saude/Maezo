from __future__ import annotations

from decimal import Decimal
from typing import Any

from platform.revenue_cycle.collection.entities import PaymentAllocation
from platform.revenue_cycle.collection.enums import AllocationStatus
from platform.shared.domain.value_objects import FHIRReference, Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class MatchByInvoiceWorker:
    """Matches payment to claim by invoice/fatura number."""

    WORKER_TYPE = "match_by_invoice"

    @track_task_execution(metric_name="match_by_invoice")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Match payment to claim using invoice/fatura number.

        Args:
            task_variables: {
                "payment_id": str,
                "invoice_number": str,
                "nosso_numero": str | None,
                "seu_numero": str | None,
                "payment_amount": float,
                "currency": str,
                "available_claims": list[dict]
            }

        Returns:
            {
                "matched": bool,
                "claim_id": str | None,
                "allocation_id": str | None,
                "invoice_number": str
            }
        """
        payment_id = task_variables["payment_id"]
        invoice_number = task_variables["invoice_number"]
        nosso_numero = task_variables.get("nosso_numero")
        seu_numero = task_variables.get("seu_numero")
        payment_amount = task_variables["payment_amount"]
        currency = task_variables.get("currency", "BRL")
        available_claims = task_variables.get("available_claims", [])

        logger.info(
            _("Buscando correspondência por número de fatura"),
            extra={"payment_id": payment_id, "invoice_number": invoice_number},
        )

        # Try multiple invoice number fields
        matched_claim = None
        for claim in available_claims:
            if claim.get("invoice_number") == invoice_number:
                matched_claim = claim
                break
            if nosso_numero and claim.get("nosso_numero") == nosso_numero:
                matched_claim = claim
                break
            if seu_numero and claim.get("seu_numero") == seu_numero:
                matched_claim = claim
                break

        if not matched_claim:
            logger.warning(
                _("Número de fatura não encontrado"),
                extra={"invoice_number": invoice_number},
            )
            return {
                "matched": False,
                "claim_id": None,
                "allocation_id": None,
                "invoice_number": invoice_number,
            }

        # Create allocation
        claim_id = matched_claim["claim_id"]
        allocation = PaymentAllocation(
            id=f"ALLOC-{payment_id}-{claim_id}",
            payment_id=payment_id,
            claim_reference=FHIRReference(reference=f"Claim/{claim_id}"),
            allocated_amount=Money(amount=Decimal(str(payment_amount)), currency=currency),
            status=AllocationStatus.AUTO_MATCHED,
            match_method="invoice",
            match_confidence=Decimal("0.85"),
        )

        logger.info(
            _("Correspondência por fatura bem-sucedida"),
            extra={"payment_id": payment_id, "claim_id": claim_id, "invoice_number": invoice_number},
        )

        return {
            "matched": True,
            "claim_id": claim_id,
            "allocation_id": allocation.id,
            "invoice_number": invoice_number,
        }
