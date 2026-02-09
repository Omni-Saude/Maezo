from __future__ import annotations

from decimal import Decimal
from typing import Any

from platform.revenue_cycle.collection.entities import PaymentAllocation
from platform.revenue_cycle.collection.enums import AllocationStatus
from platform.revenue_cycle.collection.exceptions import PaymentAllocationError
from platform.shared.domain.value_objects import FHIRReference, Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class AutoMatchingWorker:
    """Auto-matches payment to claims using multiple strategies with confidence scoring."""

    WORKER_TYPE = "auto_matching"

    @track_task_execution(metric_name="auto_matching")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Auto-match payment to claim using protocol, invoice, or patient strategies.

        Args:
            task_variables: {
                "payment_id": str,
                "protocol_number": str | None,
                "invoice_number": str | None,
                "patient_id": str | None,
                "payment_amount": float,
                "currency": str,
                "available_claims": list[dict] - claims to match against
            }

        Returns:
            {
                "matched": bool,
                "claim_id": str | None,
                "match_method": str,
                "confidence_score": float (0.0-1.0),
                "allocation_id": str | None
            }
        """
        payment_id = task_variables["payment_id"]
        payment_amount = task_variables["payment_amount"]
        currency = task_variables.get("currency", "BRL")
        available_claims = task_variables.get("available_claims", [])

        logger.info(
            _("Iniciando correspondência automática de pagamento"),
            extra={"payment_id": payment_id, "claims_count": len(available_claims)},
        )

        # Strategy 1: Protocol number (highest confidence)
        if protocol_number := task_variables.get("protocol_number"):
            match = self._match_by_protocol(protocol_number, available_claims)
            if match:
                return await self._create_allocation(
                    payment_id,
                    match["claim_id"],
                    payment_amount,
                    currency,
                    "protocol",
                    Decimal("0.95"),
                )

        # Strategy 2: Invoice number (high confidence)
        if invoice_number := task_variables.get("invoice_number"):
            match = self._match_by_invoice(invoice_number, available_claims)
            if match:
                return await self._create_allocation(
                    payment_id,
                    match["claim_id"],
                    payment_amount,
                    currency,
                    "invoice",
                    Decimal("0.85"),
                )

        # Strategy 3: Patient reference (medium confidence)
        if patient_id := task_variables.get("patient_id"):
            match = self._match_by_patient(patient_id, payment_amount, available_claims)
            if match:
                return await self._create_allocation(
                    payment_id,
                    match["claim_id"],
                    payment_amount,
                    currency,
                    "patient",
                    Decimal("0.60"),
                )

        logger.warning(
            _("Nenhuma correspondência automática encontrada"),
            extra={"payment_id": payment_id},
        )

        return {
            "matched": False,
            "claim_id": None,
            "match_method": "none",
            "confidence_score": 0.0,
            "allocation_id": None,
        }

    def _match_by_protocol(
        self, protocol_number: str, claims: list[dict]
    ) -> dict[str, Any] | None:
        """Match by TISS protocol number (exact match)."""
        for claim in claims:
            if claim.get("protocol_number") == protocol_number:
                return claim
        return None

    def _match_by_invoice(
        self, invoice_number: str, claims: list[dict]
    ) -> dict[str, Any] | None:
        """Match by invoice/fatura number."""
        for claim in claims:
            if claim.get("invoice_number") == invoice_number:
                return claim
            if claim.get("nosso_numero") == invoice_number:
                return claim
            if claim.get("seu_numero") == invoice_number:
                return claim
        return None

    def _match_by_patient(
        self, patient_id: str, payment_amount: float, claims: list[dict]
    ) -> dict[str, Any] | None:
        """Match by patient reference and amount proximity."""
        best_match = None
        min_diff = float("inf")

        for claim in claims:
            if claim.get("patient_id") == patient_id:
                claim_amount = float(claim.get("total_amount", 0))
                amount_diff = abs(claim_amount - payment_amount)
                if amount_diff < min_diff:
                    min_diff = amount_diff
                    best_match = claim

        # Only match if amount is within 5%
        if best_match and min_diff / payment_amount < 0.05:
            return best_match
        return None

    async def _create_allocation(
        self,
        payment_id: str,
        claim_id: str,
        amount: float,
        currency: str,
        method: str,
        confidence: Decimal,
    ) -> dict[str, Any]:
        """Create allocation record."""
        allocation = PaymentAllocation(
            id=f"ALLOC-{payment_id}-{claim_id}",
            payment_id=payment_id,
            claim_reference=FHIRReference(reference=f"Claim/{claim_id}"),
            allocated_amount=Money(amount=Decimal(str(amount)), currency=currency),
            status=AllocationStatus.AUTO_MATCHED,
            match_method=method,
            match_confidence=confidence,
        )

        logger.info(
            _("Correspondência automática bem-sucedida"),
            extra={
                "payment_id": payment_id,
                "claim_id": claim_id,
                "method": method,
                "confidence": float(confidence),
            },
        )

        return {
            "matched": True,
            "claim_id": claim_id,
            "match_method": method,
            "confidence_score": float(confidence),
            "allocation_id": allocation.id,
        }
