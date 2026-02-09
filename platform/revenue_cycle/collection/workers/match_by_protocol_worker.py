from __future__ import annotations

from decimal import Decimal
from typing import Any

from platform.revenue_cycle.collection.entities import PaymentAllocation
from platform.revenue_cycle.collection.enums import AllocationStatus
from platform.revenue_cycle.collection.exceptions import UnmatchedPaymentError
from platform.shared.domain.value_objects import FHIRReference, Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class MatchByProtocolWorker:
    """Matches payment to claim by TISS protocol number - exact match only."""

    WORKER_TYPE = "match_by_protocol"

    @track_task_execution(metric_name="match_by_protocol")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Match payment to claim using TISS protocol number.

        Args:
            task_variables: {
                "payment_id": str,
                "protocol_number": str,
                "payment_amount": float,
                "currency": str,
                "available_claims": list[dict]
            }

        Returns:
            {
                "matched": bool,
                "claim_id": str | None,
                "allocation_id": str | None,
                "protocol_number": str
            }
        """
        payment_id = task_variables["payment_id"]
        protocol_number = task_variables["protocol_number"]
        payment_amount = task_variables["payment_amount"]
        currency = task_variables.get("currency", "BRL")
        available_claims = task_variables.get("available_claims", [])

        logger.info(
            _("Buscando correspondência por protocolo TISS"),
            extra={"payment_id": payment_id, "protocol_number": protocol_number},
        )

        # Exact match by protocol
        matched_claim = None
        for claim in available_claims:
            if claim.get("protocol_number") == protocol_number:
                matched_claim = claim
                break

        if not matched_claim:
            logger.warning(
                _("Protocolo TISS não encontrado"),
                extra={"protocol_number": protocol_number},
            )
            return {
                "matched": False,
                "claim_id": None,
                "allocation_id": None,
                "protocol_number": protocol_number,
            }

        # Create allocation
        claim_id = matched_claim["claim_id"]
        allocation = PaymentAllocation(
            id=f"ALLOC-{payment_id}-{claim_id}",
            payment_id=payment_id,
            claim_reference=FHIRReference(reference=f"Claim/{claim_id}"),
            allocated_amount=Money(amount=Decimal(str(payment_amount)), currency=currency),
            status=AllocationStatus.AUTO_MATCHED,
            match_method="protocol",
            match_confidence=Decimal("0.95"),
        )

        logger.info(
            _("Correspondência por protocolo bem-sucedida"),
            extra={"payment_id": payment_id, "claim_id": claim_id, "protocol_number": protocol_number},
        )

        return {
            "matched": True,
            "claim_id": claim_id,
            "allocation_id": allocation.id,
            "protocol_number": protocol_number,
        }
