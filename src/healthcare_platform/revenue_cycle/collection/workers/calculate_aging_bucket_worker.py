from __future__ import annotations

from typing import Any

from healthcare_platform.revenue_cycle.collection.enums import AgingBucket
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class CalculateAgingBucketWorker:
    """    Calcula o bucket de aging baseado nos dias de vencimento.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.calculate_aging_bucket"

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

    @track_task_execution(metric_name="calculate_aging_bucket")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Atribui bucket de aging baseado em dias de vencimento.

        Args:
            task_variables: {
                "collection_case_id": str,
                "days_overdue": int
            }

        Returns:
            {
                "collection_case_id": str,
                "aging_bucket": str,
                "days_overdue": int,
                "bucket_description": str
            }
        """
        collection_case_id = task_variables["collection_case_id"]
        days_overdue = task_variables["days_overdue"]

        logger.info(
            _("Calculando bucket de aging"),
            extra={
                "collection_case_id": collection_case_id,
                "days_overdue": days_overdue,
            },
        )

        # Determine aging bucket based on days overdue
        if days_overdue <= 30:
            aging_bucket = AgingBucket.DAYS_0_30
            bucket_description = _("0-30 dias")
        elif days_overdue <= 60:
            aging_bucket = AgingBucket.DAYS_31_60
            bucket_description = _("31-60 dias")
        elif days_overdue <= 90:
            aging_bucket = AgingBucket.DAYS_61_90
            bucket_description = _("61-90 dias")
        elif days_overdue <= 120:
            aging_bucket = AgingBucket.DAYS_91_120
            bucket_description = _("91-120 dias")
        elif days_overdue <= 180:
            aging_bucket = AgingBucket.DAYS_121_180
            bucket_description = _("121-180 dias")
        else:
            aging_bucket = AgingBucket.DAYS_180_PLUS
            bucket_description = _("180+ dias")

        logger.info(
            _("Bucket de aging calculado"),
            extra={
                "collection_case_id": collection_case_id,
                "aging_bucket": aging_bucket.value,
                "days_overdue": days_overdue,
            },
        )

        return {
            "collection_case_id": collection_case_id,
            "aging_bucket": aging_bucket.value,
            "days_overdue": days_overdue,
            "bucket_description": bucket_description,
        }
