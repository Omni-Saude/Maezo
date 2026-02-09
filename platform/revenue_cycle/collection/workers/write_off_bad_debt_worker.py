from __future__ import annotations

from typing import Any

from platform.revenue_cycle.collection.enums import CollectionStatus
from platform.revenue_cycle.collection.exceptions import WriteOffError
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class WriteOffBadDebtWorker:
    """Baixa dívidas incobráveis (requer aprovação para valores altos)."""

    WORKER_TYPE = "write_off_bad_debt"

    # Approval threshold (R$ 10,000)
    APPROVAL_THRESHOLD = 10000.0

    @track_task_execution(metric_name="write_off_bad_debt")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Baixa dívida como incobrável.

        Args:
            task_variables: {
                "collection_case_id": str,
                "amount_due": float,
                "currency": str,
                "reason": str,
                "approved_by": str (required if amount > threshold),
                "approval_reference": str (optional),
                "write_off_date": str (ISO format, optional)
            }

        Returns:
            {
                "collection_case_id": str,
                "amount_written_off": float,
                "write_off_reason": str,
                "written_off_at": str,
                "requires_approval": bool,
                "approved": bool
            }
        """
        from datetime import datetime, timezone

        collection_case_id = task_variables["collection_case_id"]
        amount_due = task_variables["amount_due"]
        currency = task_variables.get("currency", "BRL")
        reason = task_variables["reason"]
        approved_by = task_variables.get("approved_by")
        approval_reference = task_variables.get("approval_reference")

        logger.info(
            _("Processando baixa de dívida incobrável"),
            extra={
                "collection_case_id": collection_case_id,
                "amount_due": amount_due,
                "reason": reason,
            },
        )

        # Check if approval is required
        requires_approval = amount_due >= self.APPROVAL_THRESHOLD

        if requires_approval and not approved_by:
            error_msg = _(
                "Baixa de valor R$ {amount:.2f} requer aprovação gerencial "
                "(limite: R$ {threshold:.2f})"
            ).format(amount=amount_due, threshold=self.APPROVAL_THRESHOLD)
            logger.error(
                error_msg,
                extra={"collection_case_id": collection_case_id, "amount": amount_due},
            )
            raise WriteOffError(error_msg)

        # Parse write-off date
        write_off_date_str = task_variables.get("write_off_date")
        if write_off_date_str:
            write_off_date = datetime.fromisoformat(
                write_off_date_str.replace("Z", "+00:00")
            )
        else:
            write_off_date = datetime.now(timezone.utc)

        # Perform write-off
        write_off_data = {
            "collection_case_id": collection_case_id,
            "amount_written_off": amount_due,
            "currency": currency,
            "write_off_reason": reason,
            "written_off_at": write_off_date.isoformat(),
            "requires_approval": requires_approval,
            "approved": bool(approved_by),
            "approved_by": approved_by,
            "approval_reference": approval_reference,
            "new_status": CollectionStatus.WRITTEN_OFF.value,
        }

        logger.info(
            _("Dívida baixada como incobrável"),
            extra={
                "collection_case_id": collection_case_id,
                "amount_written_off": amount_due,
                "approved": bool(approved_by),
                "approved_by": approved_by,
            },
        )

        return write_off_data
