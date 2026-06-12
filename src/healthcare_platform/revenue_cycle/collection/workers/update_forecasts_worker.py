from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class UpdateForecastsWorker:
    """    Atualiza previsões de fluxo de caixa baseado em datas previstas e AR atual.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.update_forecasts"

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

    @track_task_execution(metric_name="update_forecasts")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Atualiza previsões de fluxo de caixa com base em AR e datas previstas.

        Args:
            task_variables: {
                "forecast_start": str (ISO format),
                "forecast_end": str (ISO format),
                "current_ar": float (optional),
                "predicted_collections": list (optional) - [
                    {"date": str, "amount": float, "confidence": float}
                ]
            }

        Returns:
            {
                "forecast_start": str,
                "forecast_end": str,
                "current_ar": float,
                "forecast_by_week": [
                    {
                        "week_start": str,
                        "week_end": str,
                        "expected_collections": float,
                        "confidence": float
                    }
                ],
                "total_forecast": float,
                "updated_at": str
            }
        """
        forecast_start = date.fromisoformat(task_variables["forecast_start"])
        forecast_end = date.fromisoformat(task_variables["forecast_end"])

        logger.info(
            _("Atualizando previsões de fluxo de caixa"),
            extra={
                "forecast_start": forecast_start.isoformat(),
                "forecast_end": forecast_end.isoformat(),
            },
        )

        # Get current AR
        current_ar = Money.brl(task_variables.get("current_ar", 720000.00))

        # Get predicted collections
        predicted_collections = task_variables.get("predicted_collections")
        if not predicted_collections:
            # Mock data - in real implementation, query from database based on predict_collection_date
            predicted_collections = [
                {"date": (date.today() + timedelta(days=7)).isoformat(), "amount": 45000.00, "confidence": 0.85},
                {"date": (date.today() + timedelta(days=14)).isoformat(), "amount": 52000.00, "confidence": 0.82},
                {"date": (date.today() + timedelta(days=21)).isoformat(), "amount": 38000.00, "confidence": 0.78},
                {"date": (date.today() + timedelta(days=28)).isoformat(), "amount": 65000.00, "confidence": 0.88},
            ]

        # Group by week
        forecast_by_week = []
        current_week_start = forecast_start
        while current_week_start <= forecast_end:
            current_week_end = min(current_week_start + timedelta(days=6), forecast_end)

            # Filter collections for this week
            week_collections = [
                c for c in predicted_collections
                if current_week_start <= date.fromisoformat(c["date"]) <= current_week_end
            ]

            expected_collections = sum(Decimal(str(c["amount"])) for c in week_collections)
            avg_confidence = (
                sum(Decimal(str(c["confidence"])) for c in week_collections) / len(week_collections)
                if week_collections
                else Decimal("0")
            )

            forecast_by_week.append({
                "week_start": current_week_start.isoformat(),
                "week_end": current_week_end.isoformat(),
                "expected_collections": float(expected_collections),
                "confidence": float(avg_confidence),
                "collection_count": len(week_collections),
            })

            current_week_start = current_week_end + timedelta(days=1)

        total_forecast = sum(Decimal(str(w["expected_collections"])) for w in forecast_by_week)

        logger.info(
            _("Previsões de fluxo de caixa atualizadas"),
            extra={
                "total_forecast": float(total_forecast),
                "current_ar": float(current_ar.amount),
                "weeks": len(forecast_by_week),
            },
        )

        return {
            "forecast_start": forecast_start.isoformat(),
            "forecast_end": forecast_end.isoformat(),
            "current_ar": float(current_ar.amount),
            "forecast_by_week": forecast_by_week,
            "total_forecast": float(total_forecast),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
