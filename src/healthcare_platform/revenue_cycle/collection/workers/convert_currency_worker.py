"""Worker: Convert non-BRL payments to BRL."""
from __future__ import annotations

from decimal import Decimal

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class ConvertCurrencyWorker:
    """    Converts non-BRL payments to BRL using exchange rates.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.convert_currency"

    def __init__(self, exchange_rates: dict[str, Decimal] | None = None) -> None:
        """Initialize worker with exchange rates.

        Args:
            exchange_rates: Dict of currency->BRL rates (e.g. {"USD": Decimal("5.20")}).
        """
        self.exchange_rates = exchange_rates or {
            "USD": Decimal("5.20"),
            "EUR": Decimal("5.60"),
            "GBP": Decimal("6.50"),
        }
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

    @track_task_execution(metric_name="convert_currency")
    async def execute(self, task_variables: dict) -> dict:
        """Execute currency conversion.

        Args:
            task_variables: Contains 'gross_amount', 'currency', 'net_amount' (optional).

        Returns:
            Dict with BRL amounts (gross_amount_brl, net_amount_brl, exchange_rate).
        """
        currency = task_variables.get("currency", "BRL")
        gross_amount = Decimal(str(task_variables.get("gross_amount", "0")))
        net_amount = task_variables.get("net_amount")

        if currency == "BRL":
            logger.debug("payment_already_brl", amount=str(gross_amount))
            return {
                **task_variables,
                "gross_amount_brl": str(gross_amount),
                "net_amount_brl": str(net_amount) if net_amount else str(gross_amount),
                "exchange_rate": "1.0",
                "original_currency": "BRL",
            }

        # Non-BRL payment - convert
        logger.warning(
            "non_brl_payment_detected",
            currency=currency,
            amount=str(gross_amount),
        )

        exchange_rate = self.exchange_rates.get(currency)
        if not exchange_rate:
            logger.error("exchange_rate_not_found", currency=currency)
            # Default to 1:1 if rate not found (log warning)
            exchange_rate = Decimal("1.0")

        gross_brl = Money(amount=gross_amount * exchange_rate, currency="BRL")
        net_brl = gross_brl
        if net_amount:
            net_dec = Decimal(str(net_amount))
            net_brl = Money(amount=net_dec * exchange_rate, currency="BRL")

        logger.info(
            "currency_converted",
            original_currency=currency,
            original_amount=str(gross_amount),
            exchange_rate=str(exchange_rate),
            brl_amount=str(gross_brl.amount),
        )

        return {
            **task_variables,
            "gross_amount_brl": str(gross_brl.amount),
            "net_amount_brl": str(net_brl.amount),
            "exchange_rate": str(exchange_rate),
            "original_currency": currency,
            "original_gross_amount": str(gross_amount),
            "currency": "BRL",  # Update to BRL
        }
