"""Worker: Calculate net payment after fees and withholdings."""
from __future__ import annotations

from decimal import Decimal

from platform.shared.domain.value_objects import Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution
from platform.revenue_cycle.collection.exceptions import PaymentValidationError

logger = get_logger(__name__)


class CalculateNetPaymentWorker:
    """Calculates net payment = gross - bank_fees - tax_withholding."""

    WORKER_TYPE = "calculate_net_payment"

    @track_task_execution(metric_name="calculate_net_payment")
    async def execute(self, task_variables: dict) -> dict:
        """Execute net payment calculation.

        Args:
            task_variables: Contains 'gross_amount', 'bank_fees' (optional), 'tax_withholding' (optional).

        Returns:
            Dict with calculated net_amount, bank_fees, tax_withholding.

        Raises:
            PaymentValidationError: If calculated net amount is negative.
        """
        try:
            gross_amount = Money.brl(task_variables.get("gross_amount", "0"))
            bank_fees = Money.brl(task_variables.get("bank_fees", "0"))
            tax_withholding = Money.brl(task_variables.get("tax_withholding", "0"))
        except Exception as exc:
            logger.error("amount_parsing_failed", error=str(exc))
            raise PaymentValidationError(
                _("Falha ao parsear valores monetários: {err}").format(err=str(exc))
            ) from exc

        # Calculate net = gross - fees - taxes
        net_amount = gross_amount - bank_fees - tax_withholding

        if net_amount.amount < Decimal("0"):
            logger.error(
                "negative_net_amount",
                gross=str(gross_amount.amount),
                fees=str(bank_fees.amount),
                taxes=str(tax_withholding.amount),
            )
            raise PaymentValidationError(
                _("Valor líquido não pode ser negativo: {net}").format(
                    net=str(net_amount.amount)
                )
            )

        logger.info(
            "net_payment_calculated",
            gross=str(gross_amount.amount),
            bank_fees=str(bank_fees.amount),
            tax_withholding=str(tax_withholding.amount),
            net=str(net_amount.amount),
        )

        return {
            **task_variables,
            "net_amount": str(net_amount.amount),
            "bank_fees": str(bank_fees.amount),
            "tax_withholding": str(tax_withholding.amount),
            "currency": net_amount.currency,
        }
