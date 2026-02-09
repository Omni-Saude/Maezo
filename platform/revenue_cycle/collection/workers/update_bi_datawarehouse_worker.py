"""Worker for exporting collection metrics to BI data warehouse."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class FactCollectionMetrics(BaseModel):
    """Fact table: collection metrics."""

    date_key: str
    payer_key: str
    facility_key: str
    amount_billed: float
    amount_collected: float
    amount_denied: float
    amount_outstanding: float
    collection_rate: float
    claim_count: int
    payment_count: int
    denial_count: int
    avg_days_to_payment: float


class DimDate(BaseModel):
    """Dimension: date."""

    date_key: str
    full_date: str
    year: int
    quarter: int
    month: int
    day: int
    week: int
    day_of_week: int


class UpdateBiDatawarehouseWorker:
    """Exporta métricas de cobrança para data warehouse de BI."""

    WORKER_TYPE = "update_bi_datawarehouse"

    @track_task_execution(metric_name="update_bi_datawarehouse")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Formata dados para modelo dimensional (fact + dimension tables).

        Args:
            task_variables: {
                "date": str (ISO),
                "metrics_by_payer": list[dict],
                "facility_id": str
            }

        Returns:
            {
                "fact_records": list[FactCollectionMetrics],
                "dim_date": DimDate,
                "total_records": int,
                "export_timestamp": str
            }
        """
        date_str = task_variables["date"]
        metrics_by_payer = task_variables["metrics_by_payer"]
        facility_id = task_variables["facility_id"]

        logger.info(
            _("Exportando métricas para data warehouse"),
            extra={
                "date": date_str,
                "payers_count": len(metrics_by_payer),
                "facility_id": facility_id,
            },
        )

        # Parse date
        date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

        # Create dimension record
        date_key = date_obj.strftime("%Y%m%d")
        dim_date = DimDate(
            date_key=date_key,
            full_date=date_str,
            year=date_obj.year,
            quarter=(date_obj.month - 1) // 3 + 1,
            month=date_obj.month,
            day=date_obj.day,
            week=date_obj.isocalendar()[1],
            day_of_week=date_obj.isoweekday(),
        )

        # Create fact records
        fact_records: list[FactCollectionMetrics] = []

        for metrics in metrics_by_payer:
            payer_id = metrics["payer_id"]
            amount_billed = Decimal(str(metrics["amount_billed"]))
            amount_collected = Decimal(str(metrics["amount_collected"]))
            amount_denied = Decimal(str(metrics.get("amount_denied", 0)))
            amount_outstanding = amount_billed - amount_collected - amount_denied

            collection_rate = (
                float((amount_collected / amount_billed) * 100)
                if amount_billed > 0
                else 0.0
            )

            fact = FactCollectionMetrics(
                date_key=date_key,
                payer_key=payer_id,
                facility_key=facility_id,
                amount_billed=float(amount_billed),
                amount_collected=float(amount_collected),
                amount_denied=float(amount_denied),
                amount_outstanding=float(amount_outstanding),
                collection_rate=round(collection_rate, 2),
                claim_count=metrics.get("claim_count", 0),
                payment_count=metrics.get("payment_count", 0),
                denial_count=metrics.get("denial_count", 0),
                avg_days_to_payment=metrics.get("avg_days_to_payment", 0.0),
            )
            fact_records.append(fact)

        export_timestamp = datetime.utcnow().isoformat()

        logger.info(
            _("Exportação para data warehouse concluída"),
            extra={
                "total_records": len(fact_records),
                "date_key": date_key,
            },
        )

        # In production, this would write to actual DW (e.g., Snowflake, BigQuery)
        # For now, return structured data
        return {
            "fact_records": [f.model_dump() for f in fact_records],
            "dim_date": dim_date.model_dump(),
            "total_records": len(fact_records),
            "export_timestamp": export_timestamp,
        }
