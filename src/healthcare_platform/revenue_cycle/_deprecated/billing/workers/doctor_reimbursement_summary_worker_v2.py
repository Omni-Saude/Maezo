"""
Doctor Reimbursement Summary Notification Worker (Refactored)
Purpose: Notify doctors with monthly billing and reimbursement summary via WhatsApp

TOPIC: financial.reimbursement_summary

Archetype: NONE (no DMN) - Thin worker: formatting + WhatsApp send only.

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from healthcare_platform.shared.integrations.whatsapp_client import WhatsAppClientProtocol
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


def format_brl(amount: float) -> str:
    """Format amount as Brazilian Real (R$ 1.234,56)."""
    formatted = f"R$ {amount:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


class DoctorReimbursementSummaryWorker(BaseExternalTaskWorker):
    """
    Refactored reimbursement summary worker.

    Responsibilities (thin worker, no DMN):
    1. Parse and validate input variables
    2. Format currency values
    3. Calculate receipt rate
    4. Send WhatsApp notification
    """

    TOPIC = "financial.reimbursement_summary"

    def __init__(
        self,
        whatsapp_client: Optional[WhatsAppClientProtocol] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.whatsapp_client = whatsapp_client

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute reimbursement summary notification."""
        try:
            variables = context.variables
            doctor_id = variables.get("doctor_id", "")
            phone_number = variables.get("phone_number", "")
            period = variables.get("period", "")

            if not doctor_id or not phone_number or not period:
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_INPUT",
                    error_message="Missing doctor_id, phone_number, or period",
                )

            total_billed = float(variables.get("total_billed", 0))
            total_received = float(variables.get("total_received", 0))
            total_pending = float(variables.get("total_pending", 0))
            # DEPRECATED: top_denials era usado para exibir top negativas no resumo
            # top_denials = variables.get("top_denials", [])

            # Calculate receipt rate
            receipt_rate = (
                (total_received / total_billed) * 100 if total_billed > 0 else 0
            )

            # Build body params
            body_params = [
                period,
                format_brl(total_billed),
                format_brl(total_received),
                f"{receipt_rate:.1f}%",
                format_brl(total_pending),
            ]

            # Send WhatsApp notification
            message_id = None
            if self.whatsapp_client:
                message_id = self.whatsapp_client.send_template(
                    to=phone_number,
                    template_name="reimbursement_summary_v1",
                    language_code="pt_BR",
                    body_params=body_params,
                )

            self.logger.info(
                "Reimbursement summary sent",
                extra={"tenant_id": context.tenant_id, "doctor_id": doctor_id},
            )

            return TaskResult.success({
                "notification_sent": True,
                "message_id": message_id,
                "sent_at": datetime.utcnow().isoformat(),
                "receipt_rate": round(receipt_rate, 1),
            })

        except Exception as e:
            self.logger.error(f"Reimbursement summary failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_REIMBURSEMENT_SUMMARY",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
