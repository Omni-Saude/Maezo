from __future__ import annotations

from typing import Any

from healthcare_platform.revenue_cycle.collection.lib.penalty_calculator import calculate_penalty
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class ApplyPenaltiesWorker:
    """Aplica multas e juros conforme legislação brasileira."""

    WORKER_TYPE = "apply_penalties"

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

    @track_task_execution(metric_name="apply_penalties")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Calcula e aplica multas/juros sobre valores vencidos.

        Args:
            task_variables: {
                "collection_case_id": str,
                "principal_amount": float,
                "currency": str,
                "days_overdue": int,
                "original_due_date": str (ISO format),
                "penalty_rate": float (optional, default per Brazilian law),
                "interest_rate_per_month": float (optional, default per SELIC)
            }

        Returns:
            {
                "collection_case_id": str,
                "principal_amount": float,
                "penalty_amount": float,
                "interest_amount": float,
                "total_amount": float,
                "penalty_breakdown": dict
            }
        """
        from datetime import datetime

        collection_case_id = task_variables["collection_case_id"]
        principal_amount = task_variables["principal_amount"]
        currency = task_variables.get("currency", "BRL")
        days_overdue = task_variables["days_overdue"]
        original_due_date_str = task_variables["original_due_date"]

        logger.info(
            _("Aplicando multas e juros"),
            extra={
                "collection_case_id": collection_case_id,
                "principal_amount": principal_amount,
                "days_overdue": days_overdue,
            },
        )

        # Parse due date
        original_due_date = datetime.fromisoformat(
            original_due_date_str.replace("Z", "+00:00")
        )

        # Get penalty configuration
        penalty_rate = task_variables.get("penalty_rate")
        interest_rate_per_month = task_variables.get("interest_rate_per_month")

        # Calculate penalties using Brazilian law
        penalty_result = calculate_penalty(
            principal_amount=Money(value=principal_amount, currency=currency),
            due_date=original_due_date,
            calculation_date=None,  # Uses current date
            penalty_rate=penalty_rate,
            interest_rate_per_month=interest_rate_per_month,
        )

        total_amount = (
            principal_amount + penalty_result["penalty"] + penalty_result["interest"]
        )

        logger.info(
            _("Multas e juros aplicados com sucesso"),
            extra={
                "collection_case_id": collection_case_id,
                "penalty_amount": penalty_result["penalty"],
                "interest_amount": penalty_result["interest"],
                "total_amount": total_amount,
            },
        )

        return {
            "collection_case_id": collection_case_id,
            "principal_amount": principal_amount,
            "penalty_amount": penalty_result["penalty"],
            "interest_amount": penalty_result["interest"],
            "total_amount": total_amount,
            "currency": currency,
            "penalty_breakdown": {
                "days_overdue": days_overdue,
                "penalty_rate": penalty_result["penalty_rate"],
                "interest_rate_per_month": penalty_result["interest_rate_per_month"],
                "interest_days": penalty_result["interest_days"],
            },
        }
