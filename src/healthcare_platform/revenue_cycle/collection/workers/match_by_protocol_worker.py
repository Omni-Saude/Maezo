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


class MatchByProtocolWorker:
    """    Matches payment to claim by TISS protocol number - exact match only.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.match_by_protocol"

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
