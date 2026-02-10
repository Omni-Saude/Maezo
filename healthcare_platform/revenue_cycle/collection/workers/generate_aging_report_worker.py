from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from healthcare_platform.revenue_cycle.collection.enums import AgingBucket
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class GenerateAgingReportWorker:
    """Gera relatório de aging de contas a receber (AR)."""

    WORKER_TYPE = "generate_aging_report"

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

    @track_task_execution(metric_name="generate_aging_report")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Gera relatório de AR aging agrupado por buckets de dias.

        Args:
            task_variables: {
                "as_of_date": str (ISO format, optional - defaults to today),
                "include_closed": bool (optional, default False)
            }

        Returns:
            {
                "report_date": str,
                "total_ar": float,
                "aging_buckets": {
                    "current": {"amount": float, "count": int, "percentage": float},
                    "30_days": {...},
                    "60_days": {...},
                    "90_days": {...},
                    "120_days": {...},
                    "180_days": {...},
                    "over_180_days": {...}
                },
                "total_claims": int
            }
        """
        as_of_date_str = task_variables.get("as_of_date")
        as_of_date = date.fromisoformat(as_of_date_str) if as_of_date_str else date.today()
        include_closed = task_variables.get("include_closed", False)

        logger.info(
            _("Gerando relatório de aging de AR"),
            extra={"as_of_date": as_of_date.isoformat(), "include_closed": include_closed},
        )

        # In real implementation, query CollectionCase repository and calculate aging
        # Mock data for demonstration
        aging_data = {
            AgingBucket.CURRENT: {"amount": Money.brl(250000.00), "count": 45},
            AgingBucket.DAYS_30: {"amount": Money.brl(180000.00), "count": 32},
            AgingBucket.DAYS_60: {"amount": Money.brl(120000.00), "count": 28},
            AgingBucket.DAYS_90: {"amount": Money.brl(85000.00), "count": 18},
            AgingBucket.DAYS_120: {"amount": Money.brl(45000.00), "count": 12},
            AgingBucket.DAYS_180: {"amount": Money.brl(25000.00), "count": 8},
            AgingBucket.OVER_180: {"amount": Money.brl(15000.00), "count": 5},
        }

        # Calculate totals
        total_ar = sum(bucket["amount"] for bucket in aging_data.values())
        total_claims = sum(bucket["count"] for bucket in aging_data.values())

        # Calculate percentages
        aging_buckets = {}
        for bucket, data in aging_data.items():
            percentage = (
                (data["amount"].amount / total_ar.amount * Decimal("100"))
                if total_ar.amount > 0
                else Decimal("0")
            )
            aging_buckets[bucket.value] = {
                "amount": float(data["amount"].amount),
                "count": data["count"],
                "percentage": float(percentage),
            }

        logger.info(
            _("Relatório de aging gerado"),
            extra={
                "total_ar": float(total_ar.amount),
                "total_claims": total_claims,
                "largest_bucket": max(aging_data.keys(), key=lambda k: aging_data[k]["amount"].amount).value,
            },
        )

        return {
            "report_date": as_of_date.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_ar": float(total_ar.amount),
            "aging_buckets": aging_buckets,
            "total_claims": total_claims,
            "include_closed": include_closed,
        }
