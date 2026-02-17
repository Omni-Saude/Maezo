"""
Doctor Procedure Authorization Status Notification Worker (Refactored)
Purpose: Notify doctors about pending procedure authorizations via WhatsApp

TOPIC: financial.auth_pending

Refactored using template-first approach:
- Skip/priority routing extracted to DMN: auth_notification_routing.dmn
- Worker focuses on: DMN evaluation + WhatsApp notification send

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from healthcare_platform.shared.domain.exceptions import RevenueCycleException
from healthcare_platform.shared.integrations.whatsapp_client import WhatsAppClientProtocol
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class DoctorProcedureAuthStatusWorker(BaseExternalTaskWorker):
    """
    Refactored auth status notification worker.

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for routing decision (skip vs send, priority)
    3. Build summary of top pending authorizations
    4. Send WhatsApp notification
    """

    TOPIC = "financial.auth_pending"
    DMN_DECISION_KEY = "auth_notification_routing"
    DMN_CATEGORY = "cash_operations/notifications"

    def __init__(
        self,
        whatsapp_client: Optional[WhatsAppClientProtocol] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.whatsapp_client = whatsapp_client

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute doctor authorization status notification."""
        try:
            variables = context.variables
            doctor_id = variables.get("doctor_id", "")
            phone_number = variables.get("phone_number", "")
            pending_authorizations = variables.get("pending_authorizations", [])
            total_pending = len(pending_authorizations)

            if not doctor_id or not phone_number:
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_INPUT",
                    error_message="Missing doctor_id or phone_number",
                )

            # Compute oldest days for DMN input
            oldest_days = max(
                (a.get("days_pending", 0) for a in pending_authorizations),
                default=0,
            )

            # Evaluate DMN for routing (skip/send, priority)
            dmn_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DECISION_KEY,
                variables={
                    "totalPending": total_pending,
                    "oldestDays": oldest_days,
                },
                category=self.DMN_CATEGORY,
            )

            destino = dmn_result.get("destino", "skip")
            prioridade = dmn_result.get("prioridade", 5)
            restricao = dmn_result.get("restricao", "")

            # DMN says skip
            if destino == "skip":
                return TaskResult.success({
                    "notification_sent": False,
                    "destino": destino,
                    "prioridade": prioridade,
                    "restricao": restricao,
                    "total_pending": 0,
                })

            # Build summary of top 3 pending items
            sorted_auths = sorted(
                pending_authorizations,
                key=lambda x: x.get("days_pending", 0),
                reverse=True,
            )[:3]
            summary_lines = [
                f"- {a.get('patient_name', '?')}: {a.get('procedure', '?')} "
                f"({a.get('days_pending', 0)}d, {a.get('payer', '?')})"
                for a in sorted_auths
            ]
            summary_text = "\n".join(summary_lines)

            # Send WhatsApp notification
            message_id = None
            if self.whatsapp_client:
                message_id = self.whatsapp_client.send_template(
                    to=phone_number,
                    template_name="auth_pending_summary_v1",
                    language_code="pt_BR",
                    body_params=[str(total_pending), str(oldest_days), summary_text],
                )

            return TaskResult.success({
                "notification_sent": True,
                "message_id": message_id,
                "sent_at": datetime.utcnow().isoformat(),
                "total_pending": total_pending,
                "destino": destino,
                "prioridade": prioridade,
                "restricao": restricao,
            })

        except Exception as e:
            self.logger.error(f"Auth status notification failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_AUTH_STATUS_NOTIFICATION",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
