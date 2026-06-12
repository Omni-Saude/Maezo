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


class MatchByInvoiceWorker:
    """    Matches payment to claim by invoice/fatura number.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.match_by_invoice"

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
