"""Worker for calculating average revenue cycle time (encounter to payment)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class CalculateRevenueCycleTimeWorker:
    """    Calcula o tempo médio do ciclo de receita (encounter até pagamento).
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.calculate_revenue_cycle_time"

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

    @track_task_execution(metric_name="calculate_revenue_cycle_time")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Calcula tempo médio em dias de encounter até pagamento.

        Args:
            task_variables: {
                "encounters": [
                    {
                        "encounter_date": str (ISO),
                        "payment_date": str (ISO),
                        "payer_id": str
                    }
                ],
                "payer_id": str (optional - for per-payer calculation)
            }

        Returns:
            {
                "avg_cycle_time_days": float,
                "min_cycle_time_days": int,
                "max_cycle_time_days": int,
                "total_encounters": int,
                "payer_id": str (optional),
                "by_payer": dict[str, float] (if no specific payer_id)
            }
        """
        encounters = task_variables["encounters"]
        filter_payer_id = task_variables.get("payer_id")

        logger.info(
            _("Calculando tempo do ciclo de receita"),
            extra={
                "total_encounters": len(encounters),
                "payer_id": filter_payer_id,
            },
        )

        if not encounters:
            logger.warning(_("Nenhum encounter fornecido para cálculo"))
            return {
                "avg_cycle_time_days": 0.0,
                "min_cycle_time_days": 0,
                "max_cycle_time_days": 0,
                "total_encounters": 0,
            }

        cycle_times: list[int] = []
        payer_cycles: dict[str, list[int]] = {}

        for encounter in encounters:
            payer_id = encounter["payer_id"]

            # Filter by payer if specified
            if filter_payer_id and payer_id != filter_payer_id:
                continue

            encounter_date = datetime.fromisoformat(
                encounter["encounter_date"].replace("Z", "+00:00")
            )
            payment_date = datetime.fromisoformat(
                encounter["payment_date"].replace("Z", "+00:00")
            )

            days_diff = (payment_date - encounter_date).days
            cycle_times.append(days_diff)

            # Track per payer
            if payer_id not in payer_cycles:
                payer_cycles[payer_id] = []
            payer_cycles[payer_id].append(days_diff)

        if not cycle_times:
            logger.warning(_("Nenhum encounter válido após filtragem"))
            return {
                "avg_cycle_time_days": 0.0,
                "min_cycle_time_days": 0,
                "max_cycle_time_days": 0,
                "total_encounters": 0,
            }

        avg_cycle_time = sum(cycle_times) / len(cycle_times)
        min_cycle_time = min(cycle_times)
        max_cycle_time = max(cycle_times)

        result: dict[str, Any] = {
            "avg_cycle_time_days": round(avg_cycle_time, 2),
            "min_cycle_time_days": min_cycle_time,
            "max_cycle_time_days": max_cycle_time,
            "total_encounters": len(cycle_times),
        }

        if filter_payer_id:
            result["payer_id"] = filter_payer_id
        else:
            # Calculate per-payer averages
            by_payer = {
                payer: round(sum(times) / len(times), 2)
                for payer, times in payer_cycles.items()
            }
            result["by_payer"] = by_payer

        logger.info(
            _("Tempo do ciclo de receita calculado com sucesso"),
            extra={
                "avg_cycle_time_days": round(avg_cycle_time, 2),
                "total_encounters": len(cycle_times),
            },
        )

        return result
