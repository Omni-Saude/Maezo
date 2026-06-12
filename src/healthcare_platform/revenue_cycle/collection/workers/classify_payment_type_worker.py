"""Worker: Classify payment type based on expected claim amounts."""
from __future__ import annotations

from decimal import Decimal

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.revenue_cycle.collection.enums import PaymentType

logger = get_logger(__name__)


class ClassifyPaymentTypeWorker:
    """    Classifies payment as full/partial/advance based on expected amounts.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.classify_payment_type"

    def __init__(
        self,
        full_threshold: Decimal = Decimal("0.95"),
        partial_threshold: Decimal = Decimal("0.10"),
    ) -> None:
        """Initialize worker with classification thresholds.

        Args:
            full_threshold: Ratio for full payment (default 95% of expected).
            partial_threshold: Minimum ratio for partial payment (default 10%).
        """
        self.full_threshold = full_threshold
        self.partial_threshold = partial_threshold
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

    @track_task_execution(metric_name="classify_payment_type")
    async def execute(self, task_variables: dict) -> dict:
        """Execute payment type classification.

        Args:
            task_variables: Contains 'net_amount', 'expected_amount' (optional).

        Returns:
            Dict with payment_type (full/partial/advance).
        """
        net_amount = Decimal(str(task_variables.get("net_amount", "0")))
        expected_amount = task_variables.get("expected_amount")

        # If no expected amount, classify as advance payment
        if not expected_amount or expected_amount == "0":
            logger.info("payment_classified_advance_no_expected", net=str(net_amount))
            return {
                **task_variables,
                "payment_type": PaymentType.ADVANCE.value,
                "classification_reason": "no_expected_amount",
            }

        expected = Decimal(str(expected_amount))
        if expected <= Decimal("0"):
            logger.warning("invalid_expected_amount", expected=str(expected))
            return {
                **task_variables,
                "payment_type": PaymentType.ADVANCE.value,
                "classification_reason": "invalid_expected_amount",
            }

        # Calculate payment ratio
        ratio = net_amount / expected

        # Classify
        if ratio >= self.full_threshold:
            payment_type = PaymentType.FULL
            reason = f"ratio_{ratio:.2f}_above_full_threshold"
        elif ratio >= self.partial_threshold:
            payment_type = PaymentType.PARTIAL
            reason = f"ratio_{ratio:.2f}_partial_range"
        elif ratio < self.partial_threshold and net_amount > Decimal("0"):
            payment_type = PaymentType.PARTIAL
            reason = f"ratio_{ratio:.2f}_minimal_partial"
        else:
            payment_type = PaymentType.ADVANCE
            reason = "zero_or_negative_amount"

        logger.info(
            "payment_classified",
            payment_type=payment_type.value,
            net_amount=str(net_amount),
            expected_amount=str(expected),
            ratio=f"{ratio:.2f}",
        )

        return {
            **task_variables,
            "payment_type": payment_type.value,
            "classification_reason": reason,
            "payment_ratio": f"{ratio:.4f}",
        }
