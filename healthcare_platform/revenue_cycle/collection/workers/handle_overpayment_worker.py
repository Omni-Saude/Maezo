from __future__ import annotations

from decimal import Decimal
from typing import Any

from healthcare_platform.revenue_cycle.collection.entities import PaymentAllocation
from healthcare_platform.revenue_cycle.collection.enums import AllocationStatus, DiscrepancyType
from healthcare_platform.revenue_cycle.collection.exceptions import OverpaymentError
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import FHIRReference, Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class HandleOverpaymentWorker:
    """    Handles overpayments - records overpayment and creates credit note for payer.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "handle_overpayment"

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

    @track_task_execution(metric_name="handle_overpayment")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Handle overpayment scenario - raise error for manual review.

        Args:
            task_variables: {
                "payment_id": str,
                "claim_id": str,
                "payment_amount": float,
                "expected_amount": float,
                "currency": str,
                "payer_id": str
            }

        Returns:
            {
                "overpayment_amount": float,
                "credit_note_id": str,
                "allocation_id": str,
                "requires_review": bool
            }

        Raises:
            OverpaymentError: Always raises for manual review
        """
        payment_id = task_variables["payment_id"]
        claim_id = task_variables["claim_id"]
        payment_amount = Decimal(str(task_variables["payment_amount"]))
        expected_amount = Decimal(str(task_variables["expected_amount"]))
        currency = task_variables.get("currency", "BRL")
        payer_id = task_variables["payer_id"]

        overpayment = payment_amount - expected_amount

        logger.warning(
            _("Sobrepagamento detectado"),
            extra={
                "payment_id": payment_id,
                "claim_id": claim_id,
                "overpayment": float(overpayment),
                "payment_amount": float(payment_amount),
                "expected_amount": float(expected_amount),
            },
        )

        # Create allocation with overpayment flag
        allocation = PaymentAllocation(
            id=f"ALLOC-{payment_id}-{claim_id}",
            payment_id=payment_id,
            claim_reference=FHIRReference(reference=f"Claim/{claim_id}"),
            allocated_amount=Money(amount=payment_amount, currency=currency),
            expected_amount=Money(amount=expected_amount, currency=currency),
            variance=Money(amount=overpayment, currency=currency),
            status=AllocationStatus.ESCALATED,
            match_method="overpayment",
            match_confidence=Decimal("0.95"),
            discrepancy_type=DiscrepancyType.OVERPAYMENT,
        )

        # Generate credit note ID
        credit_note_id = f"CN-{payment_id}-{claim_id}"

        logger.info(
            _("Nota de crédito criada para sobrepagamento"),
            extra={
                "credit_note_id": credit_note_id,
                "payer_id": payer_id,
                "amount": float(overpayment),
            },
        )

        result = {
            "overpayment_amount": float(overpayment),
            "credit_note_id": credit_note_id,
            "allocation_id": allocation.id,
            "requires_review": True,
        }

        # Always raise for manual review
        raise OverpaymentError(
            _("Sobrepagamento requer revisão manual: {amount} {currency}").format(
                amount=float(overpayment), currency=currency
            ),
            details=result,
        )
