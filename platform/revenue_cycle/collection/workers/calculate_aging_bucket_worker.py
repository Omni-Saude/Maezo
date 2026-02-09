from __future__ import annotations

from typing import Any

from platform.revenue_cycle.collection.enums import AgingBucket
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class CalculateAgingBucketWorker:
    """Calcula o bucket de aging baseado nos dias de vencimento."""

    WORKER_TYPE = "calculate_aging_bucket"

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
