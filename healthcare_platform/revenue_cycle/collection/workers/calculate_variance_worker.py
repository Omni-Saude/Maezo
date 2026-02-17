from __future__ import annotations

from decimal import Decimal
from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class CalculateVarianceWorker:
    """    Calculates variance between expected and actual payment using Money arithmetic.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "calculate_variance"

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

    @track_task_execution(metric_name="calculate_variance")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Calculate payment variance with precision.

        Args:
            task_variables: {
                "expected_amount": float,
                "actual_amount": float,
                "currency": str
            }

        Returns:
            {
                "variance": float,
                "variance_percent": float,
                "is_positive": bool (overpayment),
                "is_negative": bool (underpayment),
                "is_exact": bool,
                "tolerance_met": bool (within 1%)
            }
        """
        expected = Decimal(str(task_variables["expected_amount"]))
        actual = Decimal(str(task_variables["actual_amount"]))
        currency = task_variables.get("currency", "BRL")

        logger.info(
            _("Calculando variação de pagamento"),
            extra={"expected": float(expected), "actual": float(actual)},
        )

        # Use Money objects for precise calculation
        expected_money = Money(amount=expected, currency=currency)
        actual_money = Money(amount=actual, currency=currency)

        # Calculate variance (positive = overpayment, negative = underpayment)
        variance_money = actual_money - expected_money
        variance = variance_money.amount

        # Calculate percentage
        variance_percent = (variance / expected * 100) if expected > 0 else Decimal("0")

        # Tolerance check (1%)
        tolerance_threshold = expected * Decimal("0.01")
        tolerance_met = abs(variance) <= tolerance_threshold

        is_exact = abs(variance) < Decimal("0.01")
        is_positive = variance > Decimal("0.01")
        is_negative = variance < Decimal("-0.01")

        logger.info(
            _("Variação calculada"),
            extra={
                "variance": float(variance),
                "variance_percent": float(variance_percent),
                "is_exact": is_exact,
                "tolerance_met": tolerance_met,
            },
        )

        return {
            "variance": float(variance),
            "variance_percent": float(variance_percent),
            "is_positive": is_positive,
            "is_negative": is_negative,
            "is_exact": is_exact,
            "tolerance_met": tolerance_met,
        }
