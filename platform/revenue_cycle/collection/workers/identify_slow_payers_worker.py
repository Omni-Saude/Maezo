from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class IdentifySlowPayersWorker:
    """Identifica operadoras com padrões consistentemente lentos de pagamento."""

    WORKER_TYPE = "identify_slow_payers"

    @track_task_execution(metric_name="identify_slow_payers")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Identifica payers com padrões lentos de pagamento e ranqueia por média de dias.

        Args:
            task_variables: {
                "lookback_days": int (optional, default 90),
                "min_payments": int (optional, default 5 - minimum payments for statistical relevance),
                "threshold_days": int (optional, default 60 - days to be considered "slow")
            }

        Returns:
            {
                "slow_payers": [
                    {
                        "payer_id": str,
                        "payer_name": str,
                        "avg_days_to_payment": float,
                        "payment_count": int,
                        "total_amount": float,
                        "variance": float
                    }
                ],
                "analyzed_payers": int,
                "total_payments": int,
                "generated_at": str
            }
        """
        lookback_days = task_variables.get("lookback_days", 90)
        min_payments = task_variables.get("min_payments", 5)
        threshold_days = task_variables.get("threshold_days", 60)

        logger.info(
            _("Identificando operadoras com pagamento lento"),
            extra={
                "lookback_days": lookback_days,
                "min_payments": min_payments,
                "threshold_days": threshold_days,
            },
        )

        # In real implementation, query Payment and PaymentAllocation repositories
        # Calculate avg days from claim date to payment date grouped by payer
        # Mock data for demonstration
        payer_stats = [
            {
                "payer_id": "OP-001",
                "payer_name": "Operadora Alfa S.A.",
                "avg_days_to_payment": 85.5,
                "payment_count": 42,
                "total_amount": 850000.00,
                "variance": 12.3,
            },
            {
                "payer_id": "OP-002",
                "payer_name": "Operadora Beta Ltda",
                "avg_days_to_payment": 72.8,
                "payment_count": 28,
                "total_amount": 620000.00,
                "variance": 18.7,
            },
            {
                "payer_id": "OP-003",
                "payer_name": "Operadora Gama Corp",
                "avg_days_to_payment": 65.2,
                "payment_count": 35,
                "total_amount": 710000.00,
                "variance": 9.5,
            },
        ]

        # Filter slow payers
        slow_payers = [
            payer
            for payer in payer_stats
            if payer["avg_days_to_payment"] >= threshold_days and payer["payment_count"] >= min_payments
        ]

        # Sort by average days (slowest first)
        slow_payers.sort(key=lambda x: x["avg_days_to_payment"], reverse=True)

        total_payments = sum(p["payment_count"] for p in payer_stats)

        logger.info(
            _("Operadoras lentas identificadas"),
            extra={
                "slow_payers_count": len(slow_payers),
                "analyzed_payers": len(payer_stats),
                "slowest_payer": slow_payers[0]["payer_name"] if slow_payers else None,
                "slowest_avg_days": slow_payers[0]["avg_days_to_payment"] if slow_payers else None,
            },
        )

        return {
            "slow_payers": slow_payers,
            "analyzed_payers": len(payer_stats),
            "total_payments": total_payments,
            "lookback_days": lookback_days,
            "threshold_days": threshold_days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
