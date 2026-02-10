"""Worker for generating executive dashboard KPI data."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class AgingDistribution(BaseModel):
    """Distribuição por faixa de aging."""

    bucket: str
    amount: float
    count: int
    percentage: float


class ExecutiveDashboardData(BaseModel):
    """Dados para dashboard executivo."""

    collection_rate: float
    dso: float
    aging_distribution: list[AgingDistribution]
    top_payers: list[dict[str, Any]]
    revenue_forecast: float
    total_ar: float
    current_month_collected: float


class GenerateExecutiveDashboardWorker:
    """Gera dados de KPIs para dashboard executivo."""

    WORKER_TYPE = "generate_executive_dashboard"

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

    @track_task_execution(metric_name="generate_executive_dashboard")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Gera dados estruturados para dashboard executivo.

        Args:
            task_variables: {
                "collection_rate": float,
                "dso": float,
                "aging_buckets": list[dict],
                "payers": list[dict],
                "total_ar": float,
                "current_month_collected": float,
                "historical_collections": list[float]
            }

        Returns:
            ExecutiveDashboardData as dict
        """
        collection_rate = task_variables["collection_rate"]
        dso = task_variables["dso"]
        aging_buckets = task_variables["aging_buckets"]
        payers = task_variables["payers"]
        total_ar = Decimal(str(task_variables["total_ar"]))
        current_month_collected = Decimal(
            str(task_variables["current_month_collected"])
        )
        historical_collections = task_variables.get("historical_collections", [])

        logger.info(
            _("Gerando dados do dashboard executivo"),
            extra={
                "collection_rate": collection_rate,
                "dso": dso,
                "total_ar": float(total_ar),
            },
        )

        # Process aging distribution
        total_aging_amount = sum(
            Decimal(str(bucket["amount"])) for bucket in aging_buckets
        )
        aging_distribution: list[AgingDistribution] = []

        for bucket in aging_buckets:
            amount = Decimal(str(bucket["amount"]))
            percentage = (
                float((amount / total_aging_amount) * 100)
                if total_aging_amount > 0
                else 0.0
            )
            aging_distribution.append(
                AgingDistribution(
                    bucket=bucket["bucket"],
                    amount=float(amount),
                    count=bucket["count"],
                    percentage=round(percentage, 2),
                )
            )

        # Get top 5 payers by collected amount
        sorted_payers = sorted(
            payers,
            key=lambda p: Decimal(str(p.get("amount_collected", 0))),
            reverse=True,
        )
        top_payers = [
            {
                "payer_id": p["payer_id"],
                "payer_name": p["payer_name"],
                "amount_collected": float(
                    Decimal(str(p.get("amount_collected", 0)))
                ),
                "collection_rate": p.get("collection_rate", 0.0),
            }
            for p in sorted_payers[:5]
        ]

        # Simple revenue forecast (average of last 3 months * 1.05)
        if len(historical_collections) >= 3:
            avg_last_3 = sum(historical_collections[-3:]) / 3
            revenue_forecast = avg_last_3 * 1.05  # 5% growth assumption
        else:
            revenue_forecast = float(current_month_collected * Decimal("1.05"))

        dashboard_data = ExecutiveDashboardData(
            collection_rate=round(collection_rate, 2),
            dso=round(dso, 2),
            aging_distribution=aging_distribution,
            top_payers=top_payers,
            revenue_forecast=round(revenue_forecast, 2),
            total_ar=float(total_ar),
            current_month_collected=float(current_month_collected),
        )

        logger.info(
            _("Dashboard executivo gerado com sucesso"),
            extra={
                "collection_rate": dashboard_data.collection_rate,
                "dso": dashboard_data.dso,
                "revenue_forecast": dashboard_data.revenue_forecast,
            },
        )

        return dashboard_data.model_dump()
