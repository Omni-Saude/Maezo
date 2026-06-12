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


class MatchByPatientWorker:
    """    Matches payment to claim by patient reference when other methods fail.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.match_by_patient"

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

    @track_task_execution(metric_name="match_by_patient")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Match payment to claim using patient reference and amount proximity.

        Args:
            task_variables: {
                "payment_id": str,
                "patient_id": str,
                "payment_amount": float,
                "currency": str,
                "available_claims": list[dict],
                "tolerance_percent": float (default: 5.0)
            }

        Returns:
            {
                "matched": bool,
                "claim_id": str | None,
                "allocation_id": str | None,
                "confidence_score": float,
                "amount_difference": float
            }
        """
        payment_id = task_variables["payment_id"]
        patient_id = task_variables["patient_id"]
        payment_amount = task_variables["payment_amount"]
        currency = task_variables.get("currency", "BRL")
        available_claims = task_variables.get("available_claims", [])
        tolerance_percent = task_variables.get("tolerance_percent", 5.0)

        logger.info(
            _("Buscando correspondência por paciente"),
            extra={"payment_id": payment_id, "patient_id": patient_id},
        )

        # Find claims for this patient
        patient_claims = [c for c in available_claims if c.get("patient_id") == patient_id]

        if not patient_claims:
            logger.warning(
                _("Nenhum claim encontrado para o paciente"),
                extra={"patient_id": patient_id},
            )
            return {
                "matched": False,
                "claim_id": None,
                "allocation_id": None,
                "confidence_score": 0.0,
                "amount_difference": 0.0,
            }

        # Find best match by amount proximity
        best_match = None
        min_difference = float("inf")

        for claim in patient_claims:
            claim_amount = float(claim.get("total_amount", 0))
            difference = abs(claim_amount - payment_amount)

            if difference < min_difference:
                min_difference = difference
                best_match = claim

        # Calculate confidence based on amount proximity
        tolerance = payment_amount * (tolerance_percent / 100.0)
        if min_difference > tolerance:
            logger.warning(
                _("Diferença de valor excede tolerância"),
                extra={"difference": min_difference, "tolerance": tolerance},
            )
            return {
                "matched": False,
                "claim_id": None,
                "allocation_id": None,
                "confidence_score": 0.0,
                "amount_difference": min_difference,
            }

        # Calculate confidence (inverse of difference ratio)
        confidence = max(0.3, 1.0 - (min_difference / payment_amount))

        # Create allocation
        claim_id = best_match["claim_id"]
        allocation = PaymentAllocation(
            id=f"ALLOC-{payment_id}-{claim_id}",
            payment_id=payment_id,
            claim_reference=FHIRReference(reference=f"Claim/{claim_id}"),
            allocated_amount=Money(amount=Decimal(str(payment_amount)), currency=currency),
            status=AllocationStatus.AUTO_MATCHED,
            match_method="patient",
            match_confidence=Decimal(str(confidence)),
        )

        logger.info(
            _("Correspondência por paciente bem-sucedida"),
            extra={
                "payment_id": payment_id,
                "claim_id": claim_id,
                "confidence": confidence,
                "difference": min_difference,
            },
        )

        return {
            "matched": True,
            "claim_id": claim_id,
            "allocation_id": allocation.id,
            "confidence_score": confidence,
            "amount_difference": min_difference,
        }
