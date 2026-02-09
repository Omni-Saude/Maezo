from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from platform.revenue_cycle.collection.entities import Reconciliation
from platform.revenue_cycle.collection.enums import ReconciliationPeriod, ReconciliationStatus
from platform.shared.domain.value_objects import Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class ReconcileWeeklyWorker:
    """Agrega reconciliações diárias em relatório semanal."""

    WORKER_TYPE = "reconcile_weekly"

    @track_task_execution(metric_name="reconcile_weekly")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Agrega reconciliações diárias em relatório semanal com tendências.

        Args:
            task_variables: {
                "week_start": str (ISO format, optional - defaults to last Monday),
                "previous_week_total": float (optional, for trend calculation)
            }

        Returns:
            {
                "reconciliation_id": str,
                "period_start": str,
                "period_end": str,
                "total_expected": float,
                "total_received": float,
                "total_variance": float,
                "status": str,
                "daily_reconciliations": int,
                "week_over_week_change": float,
                "trend": str
            }
        """
        week_start_str = task_variables.get("week_start")
        if week_start_str:
            week_start = date.fromisoformat(week_start_str)
        else:
            today = date.today()
            week_start = today - timedelta(days=today.weekday() + 7)

        week_end = week_start + timedelta(days=6)

        logger.info(
            _("Iniciando reconciliação semanal"),
            extra={"week_start": week_start.isoformat(), "week_end": week_end.isoformat()},
        )

        # In real implementation, aggregate daily reconciliations from DB
        total_expected = Money.brl(350000.00)
        total_received = Money.brl(332500.75)
        total_variance = total_expected - total_received
        daily_reconciliations = 7

        # Calculate week-over-week trend
        previous_week_total = Decimal(str(task_variables.get("previous_week_total", 320000.00)))
        current_total = total_received.amount
        week_over_week_change = (
            ((current_total - previous_week_total) / previous_week_total * Decimal("100"))
            if previous_week_total > 0
            else Decimal("0")
        )

        trend = "up" if week_over_week_change > 0 else "down" if week_over_week_change < 0 else "flat"

        # Determine overall status
        variance_percentage = (
            abs(total_variance.amount) / total_expected.amount * Decimal("100")
            if total_expected.amount > 0
            else Decimal("0")
        )
        status = ReconciliationStatus.BALANCED if variance_percentage <= 2 else ReconciliationStatus.UNBALANCED

        reconciliation = Reconciliation(
            id=uuid4(),
            period=ReconciliationPeriod.WEEKLY,
            period_start=week_start,
            period_end=week_end,
            status=status,
            total_expected=total_expected,
            total_received=total_received,
            total_variance=total_variance,
            payment_count=daily_reconciliations,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        logger.info(
            _("Reconciliação semanal concluída"),
            extra={
                "reconciliation_id": str(reconciliation.id),
                "status": status.value,
                "week_over_week_change": float(week_over_week_change),
                "trend": trend,
            },
        )

        return {
            "reconciliation_id": str(reconciliation.id),
            "period_start": week_start.isoformat(),
            "period_end": week_end.isoformat(),
            "total_expected": float(total_expected.amount),
            "total_received": float(total_received.amount),
            "total_variance": float(total_variance.amount),
            "status": status.value,
            "daily_reconciliations": daily_reconciliations,
            "week_over_week_change": float(week_over_week_change),
            "trend": trend,
        }
