from __future__ import annotations

from decimal import Decimal
from typing import Any

from healthcare_platform.revenue_cycle.collection.enums import DiscrepancyType
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class FlagDiscrepanciesWorker:
    """    Flags payment discrepancies by type for human review.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.flag_discrepancies"

    def __init__(self, tasy_api_client=None) -> None:
        self.dmn_service = FederatedDMNService()
        self._logger = get_logger(__name__)
        self._tasy_api_client = tasy_api_client

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

    @track_task_execution(metric_name="flag_discrepancies")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Flag payment discrepancies for manual review.

        Args:
            task_variables: {
                "payment_id": str,
                "claim_id": str,
                "variance": float,
                "expected_amount": float,
                "actual_amount": float,
                "duplicate_check": bool,
                "currency": str
            }

        Returns:
            {
                "has_discrepancy": bool,
                "discrepancy_type": str,
                "severity": str (low, medium, high, critical),
                "requires_review": bool,
                "flagged_at": str (ISO timestamp)
            }
        """
        from datetime import datetime, timezone

        payment_id = task_variables["payment_id"]
        claim_id = task_variables.get("claim_id")
        variance = Decimal(str(task_variables.get("variance", 0)))
        expected = Decimal(str(task_variables.get("expected_amount", 0)))
        # TODO: actual sera usado na comparacao detalhada de valores pagos vs esperados
        # actual = Decimal(str(task_variables.get("actual_amount", 0)))
        is_duplicate = task_variables.get("duplicate_check", False)

        logger.info(
            _("Verificando discrepâncias de pagamento"),
            extra={"payment_id": payment_id, "variance": float(variance)},
        )

        # Try to get discrepancies from TASY API if available
        if self._tasy_api_client:
            try:
                from datetime import datetime, timezone
                today = datetime.now(timezone.utc).date()
                tasy_discrepancies = await self._tasy_api_client.get_reconciliation_discrepancies(
                    date_from=today.isoformat(),
                    date_to=today.isoformat(),
                )

                # Check if this payment has a discrepancy in TASY
                for disc in tasy_discrepancies:
                    if disc.get("payment_id") == payment_id:
                        self._logger.info("Found TASY discrepancy", type=disc.get("type"))
                        return {
                            "has_discrepancy": True,
                            "discrepancy_type": disc.get("type"),
                            "severity": disc.get("severity", "medium"),
                            "requires_review": disc.get("requires_review", True),
                            "flagged_at": datetime.now(timezone.utc).isoformat(),
                            "source": "tasy",
                        }
            except Exception as e:
                self._logger.warning("Failed to get TASY discrepancies, using fallback logic", error=str(e))

        # Fallback to local discrepancy detection
        discrepancy_type = None
        severity = "low"
        has_discrepancy = False

        # Check for duplicate
        if is_duplicate:
            discrepancy_type = DiscrepancyType.DUPLICATE_PAYMENT.value
            severity = "critical"
            has_discrepancy = True

        # Check for wrong claim
        elif not claim_id:
            discrepancy_type = DiscrepancyType.WRONG_CLAIM.value
            severity = "high"
            has_discrepancy = True

        # Check variance
        elif variance > Decimal("10.00"):
            discrepancy_type = DiscrepancyType.OVERPAYMENT.value
            severity = "high" if variance > expected * Decimal("0.1") else "medium"
            has_discrepancy = True

        elif variance < Decimal("-10.00"):
            discrepancy_type = DiscrepancyType.UNDERPAYMENT.value
            severity = "medium" if abs(variance) > expected * Decimal("0.1") else "low"
            has_discrepancy = True

        # Small variance - contractual adjustment
        elif abs(variance) > Decimal("0.01"):
            discrepancy_type = DiscrepancyType.CONTRACTUAL_ADJUSTMENT.value
            severity = "low"
            has_discrepancy = True

        # Unmatched payment
        elif not claim_id:
            discrepancy_type = DiscrepancyType.UNMATCHED.value
            severity = "medium"
            has_discrepancy = True

        flagged_at = datetime.now(timezone.utc).isoformat()

        if has_discrepancy:
            logger.warning(
                _("Discrepância detectada"),
                extra={
                    "payment_id": payment_id,
                    "type": discrepancy_type,
                    "severity": severity,
                },
            )
        else:
            logger.info(
                _("Nenhuma discrepância detectada"),
                extra={"payment_id": payment_id},
            )

        return {
            "has_discrepancy": has_discrepancy,
            "discrepancy_type": discrepancy_type,
            "severity": severity,
            "requires_review": severity in ["high", "critical"],
            "flagged_at": flagged_at,
        }
