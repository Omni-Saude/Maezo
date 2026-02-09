from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from platform.revenue_cycle.collection.entities import Reconciliation
from platform.revenue_cycle.collection.enums import ReconciliationPeriod, ReconciliationStatus
from platform.revenue_cycle.collection.exceptions import ReconciliationError
from platform.shared.domain.value_objects import Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class ReconcileDailyWorker:
    """Executa reconciliação diária de pagamentos recebidos."""

    WORKER_TYPE = "reconcile_daily"

    @track_task_execution(metric_name="reconcile_daily")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Executa reconciliação diária comparando pagamentos esperados vs recebidos.

        Args:
            task_variables: {
                "reconciliation_date": str (ISO format, optional - defaults to yesterday),
                "expected_amount": float (optional),
                "variance_threshold": float (optional, default 0.01 = 1%)
            }

        Returns:
            {
                "reconciliation_id": str,
                "period_start": str,
                "period_end": str,
                "total_expected": float,
                "total_received": float,
                "total_variance": float,
                "variance_percentage": float,
                "status": str,
                "payment_count": int,
                "matched_count": int,
                "unmatched_count": int
            }
        """
        recon_date_str = task_variables.get("reconciliation_date")
        if recon_date_str:
            recon_date = date.fromisoformat(recon_date_str)
        else:
            recon_date = date.today() - timedelta(days=1)

        variance_threshold = Decimal(str(task_variables.get("variance_threshold", 0.01)))

        logger.info(
            _("Iniciando reconciliação diária"),
            extra={"reconciliation_date": recon_date.isoformat()},
        )

        # In real implementation, query Payment repository for the date range
        # Mock data for demonstration
        total_expected = Money.brl(task_variables.get("expected_amount", 50000.00))
        total_received = Money.brl(47500.50)  # Mock: would sum payments from DB
        payment_count = 45
        matched_count = 42
        unmatched_count = 3

        total_variance = total_expected - total_received
        variance_percentage = (
            abs(total_variance.amount) / total_expected.amount * Decimal("100")
            if total_expected.amount > 0
            else Decimal("0")
        )

        # Determine status based on variance
        if abs(variance_percentage) <= (variance_threshold * Decimal("100")):
            status = ReconciliationStatus.BALANCED
        else:
            status = ReconciliationStatus.UNBALANCED

        reconciliation = Reconciliation(
            id=uuid4(),
            period=ReconciliationPeriod.DAILY,
            period_start=recon_date,
            period_end=recon_date,
            status=status,
            total_expected=total_expected,
            total_received=total_received,
            total_variance=total_variance,
            payment_count=payment_count,
            matched_count=matched_count,
            unmatched_count=unmatched_count,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        logger.info(
            _("Reconciliação diária concluída"),
            extra={
                "reconciliation_id": str(reconciliation.id),
                "status": reconciliation.status.value,
                "variance": float(total_variance.amount),
                "variance_percentage": float(variance_percentage),
            },
        )

        if status == ReconciliationStatus.UNBALANCED:
            logger.warning(
                _("Variação acima do limite aceitável"),
                extra={
                    "variance_percentage": float(variance_percentage),
                    "threshold": float(variance_threshold * Decimal("100")),
                },
            )

        return {
            "reconciliation_id": str(reconciliation.id),
            "period_start": recon_date.isoformat(),
            "period_end": recon_date.isoformat(),
            "total_expected": float(total_expected.amount),
            "total_received": float(total_received.amount),
            "total_variance": float(total_variance.amount),
            "variance_percentage": float(variance_percentage),
            "status": reconciliation.status.value,
            "payment_count": payment_count,
            "matched_count": matched_count,
            "unmatched_count": unmatched_count,
        }
