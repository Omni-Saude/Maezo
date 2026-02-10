"""Worker for calculating collection rate (amount_collected / amount_billed)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class CalculateCollectionRateWorker:
    """Calcula a taxa de cobrança (collection rate) para um período."""

    WORKER_TYPE = "calculate_collection_rate"

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

    @track_task_execution(metric_name="calculate_collection_rate")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Calcula taxa de cobrança = (valor_recebido / valor_faturado) * 100.

        Args:
            task_variables: {
                "period_start": str (ISO date),
                "period_end": str (ISO date),
                "amount_billed": float,
                "amount_collected": float,
                "payer_id": str (optional - for per-payer calculation)
            }

        Returns:
            {
                "collection_rate": float (percentage 0-100),
                "amount_billed": float,
                "amount_collected": float,
                "uncollected": float,
                "period_start": str,
                "period_end": str,
                "payer_id": str (optional)
            }
        """
        period_start = task_variables["period_start"]
        period_end = task_variables["period_end"]
        amount_billed = Decimal(str(task_variables["amount_billed"]))
        amount_collected = Decimal(str(task_variables["amount_collected"]))
        payer_id = task_variables.get("payer_id")

        logger.info(
            _("Calculando taxa de cobrança"),
            extra={
                "period_start": period_start,
                "period_end": period_end,
                "amount_billed": float(amount_billed),
                "amount_collected": float(amount_collected),
                "payer_id": payer_id,
            },
        )

        # Calculate collection rate
        if amount_billed == 0:
            collection_rate = Decimal("0.0")
            logger.warning(
                _("Valor faturado é zero, taxa de cobrança definida como 0%"),
                extra={"period_start": period_start, "period_end": period_end},
            )
        else:
            collection_rate = (amount_collected / amount_billed) * Decimal("100")

        uncollected = amount_billed - amount_collected

        result = {
            "collection_rate": float(collection_rate),
            "amount_billed": float(amount_billed),
            "amount_collected": float(amount_collected),
            "uncollected": float(uncollected),
            "period_start": period_start,
            "period_end": period_end,
        }

        if payer_id:
            result["payer_id"] = payer_id

        logger.info(
            _("Taxa de cobrança calculada com sucesso"),
            extra={
                "collection_rate": float(collection_rate),
                "uncollected": float(uncollected),
                "payer_id": payer_id,
            },
        )

        return result
