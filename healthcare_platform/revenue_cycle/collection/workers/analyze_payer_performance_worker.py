"""Worker for analyzing and benchmarking payer performance."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class PayerPerformanceMetrics(BaseModel):
    """    Métricas de performance de um pagador.
    
        Archetype: FINANCIAL_CALCULATION
        """

    payer_id: str
    payer_name: str
    avg_payment_time_days: float
    denial_rate: float
    collection_rate: float
    dso: float  # Days Sales Outstanding
    total_billed: float
    total_collected: float
    performance_score: float


class AnalyzePayerPerformanceWorker:
    """Analisa e compara performance dos pagadores."""

    WORKER_TYPE = "analyze_payer_performance"

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

    @track_task_execution(metric_name="analyze_payer_performance")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Benchmarks de performance por pagador.

        Args:
            task_variables: {
                "payers": [
                    {
                        "payer_id": str,
                        "payer_name": str,
                        "avg_payment_time_days": float,
                        "total_claims": int,
                        "denied_claims": int,
                        "amount_billed": float,
                        "amount_collected": float,
                        "days_sales_outstanding": float
                    }
                ]
            }

        Returns:
            {
                "payers": list[PayerPerformanceMetrics],
                "best_performer": PayerPerformanceMetrics,
                "worst_performer": PayerPerformanceMetrics,
                "total_payers_analyzed": int
            }
        """
        payers_data = task_variables["payers"]

        logger.info(
            _("Analisando performance dos pagadores"),
            extra={"total_payers": len(payers_data)},
        )

        if not payers_data:
            logger.warning(_("Nenhum pagador fornecido para análise"))
            return {
                "payers": [],
                "best_performer": None,
                "worst_performer": None,
                "total_payers_analyzed": 0,
            }

        performance_list: list[PayerPerformanceMetrics] = []

        for payer in payers_data:
            # Calculate metrics
            total_claims = payer["total_claims"]
            denied_claims = payer["denied_claims"]
            amount_billed = Decimal(str(payer["amount_billed"]))
            amount_collected = Decimal(str(payer["amount_collected"]))

            denial_rate = (
                (denied_claims / total_claims * 100) if total_claims > 0 else 0.0
            )
            collection_rate = (
                float((amount_collected / amount_billed) * 100)
                if amount_billed > 0
                else 0.0
            )

            # Calculate performance score (0-100)
            # Lower payment time = better
            # Lower denial rate = better
            # Higher collection rate = better
            # Lower DSO = better
            payment_time_score = max(0, 100 - payer["avg_payment_time_days"])
            denial_score = max(0, 100 - denial_rate)
            collection_score = collection_rate
            dso_score = max(0, 100 - payer["days_sales_outstanding"])

            performance_score = (
                payment_time_score * 0.3
                + denial_score * 0.3
                + collection_score * 0.2
                + dso_score * 0.2
            )

            metrics = PayerPerformanceMetrics(
                payer_id=payer["payer_id"],
                payer_name=payer["payer_name"],
                avg_payment_time_days=round(payer["avg_payment_time_days"], 2),
                denial_rate=round(denial_rate, 2),
                collection_rate=round(collection_rate, 2),
                dso=round(payer["days_sales_outstanding"], 2),
                total_billed=float(amount_billed),
                total_collected=float(amount_collected),
                performance_score=round(performance_score, 2),
            )
            performance_list.append(metrics)

        # Sort by performance score (descending)
        performance_list.sort(key=lambda x: x.performance_score, reverse=True)

        best_performer = performance_list[0]
        worst_performer = performance_list[-1]

        logger.info(
            _("Análise de performance concluída"),
            extra={
                "total_payers": len(performance_list),
                "best_performer": best_performer.payer_name,
                "worst_performer": worst_performer.payer_name,
            },
        )

        return {
            "payers": [p.model_dump() for p in performance_list],
            "best_performer": best_performer.model_dump(),
            "worst_performer": worst_performer.model_dump(),
            "total_payers_analyzed": len(performance_list),
        }
