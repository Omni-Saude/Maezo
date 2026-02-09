from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from platform.revenue_cycle.collection.enums import AllocationStatus
from platform.revenue_cycle.collection.exceptions import UnmatchedPaymentError
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class EscalateUnmatchedWorker:
    """Escalates payments that couldn't be matched after all strategies."""

    WORKER_TYPE = "escalate_unmatched"

    @track_task_execution(metric_name="escalate_unmatched")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Escalate unmatched payment for manual review.

        Args:
            task_variables: {
                "payment_id": str,
                "payment_amount": float,
                "currency": str,
                "payer_id": str,
                "attempted_strategies": list[str],
                "payment_date": str,
                "transaction_id": str,
                "notes": str
            }

        Returns:
            {
                "escalation_id": str,
                "status": str,
                "escalated_at": str,
                "requires_manual_review": bool
            }

        Raises:
            UnmatchedPaymentError: Always raises to create human task
        """
        payment_id = task_variables["payment_id"]
        payment_amount = task_variables["payment_amount"]
        currency = task_variables.get("currency", "BRL")
        payer_id = task_variables.get("payer_id")
        attempted_strategies = task_variables.get("attempted_strategies", [])
        transaction_id = task_variables.get("transaction_id", "")

        logger.error(
            _("Pagamento não correspondido - escalando para revisão manual"),
            extra={
                "payment_id": payment_id,
                "amount": payment_amount,
                "payer_id": payer_id,
                "strategies_attempted": len(attempted_strategies),
            },
        )

        escalation_id = f"ESC-{payment_id}-{int(datetime.now(timezone.utc).timestamp())}"
        escalated_at = datetime.now(timezone.utc).isoformat()

        # Create escalation context
        context = {
            "payment_id": payment_id,
            "payment_amount": payment_amount,
            "currency": currency,
            "payer_id": payer_id,
            "transaction_id": transaction_id,
            "attempted_strategies": attempted_strategies,
            "payment_date": task_variables.get("payment_date"),
            "notes": task_variables.get("notes", ""),
            "escalated_at": escalated_at,
        }

        result = {
            "escalation_id": escalation_id,
            "status": AllocationStatus.ESCALATED.value,
            "escalated_at": escalated_at,
            "requires_manual_review": True,
            "context": context,
        }

        logger.info(
            _("Escalação criada com sucesso"),
            extra={"escalation_id": escalation_id, "payment_id": payment_id},
        )

        # Always raise error to create human task in BPMN
        raise UnmatchedPaymentError(
            _("Pagamento não correspondido requer revisão manual: {amount} {currency}").format(
                amount=payment_amount, currency=currency
            ),
            details=result,
        )
