"""
Patient Authorization Update Notification Worker (Refactored)
Purpose: Notify patient of authorization status changes via WhatsApp

TOPIC: financial.auth_update
ARCHETYPE: OPERATIONAL_ROUTING
DMN: cash_operations/notifications/patient_auth_notification_routing

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides
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


class PatientAuthorizationUpdateWorker(BaseExternalTaskWorker):
    """
    Notifies patient of authorization status changes via WhatsApp.

    Responsibilities (thin worker pattern):
    1. Extract and validate input variables from TaskContext
    2. Evaluate DMN for routing (destino, prioridade, restricao/next_steps)
    3. Send WhatsApp notification with status and next steps
    """

    TOPIC = "financial.auth_update"
    DMN_DECISION_KEY = "patient_auth_notification_routing"
    DMN_CATEGORY = "cash_operations/notifications"

    def __init__(
        self,
        whatsapp_client: Optional[WhatsAppClientProtocol] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.whatsapp_client = whatsapp_client

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute patient authorization update notification for CIB Seven."""
        try:
            variables = context.variables
            patient_id = variables.get("patientId", "")
            phone_number = variables.get("phoneNumber", "")
            authorization_id = variables.get("authorizationId", "")
            procedure_name = variables.get("procedureName", "")
            status = variables.get("authorizationStatus", "")

            if not patient_id or not phone_number or not status:
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_INPUT",
                    error_message="Missing required variables: patient_id, phone_number, status",
                )

            # Evaluate DMN — routing and next steps (status labels extracted from code → DMN)
            dmn_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DECISION_KEY,
                variables={"authorization_status": status},
                category=self.DMN_CATEGORY,
            )

            destino = dmn_result.get("destino", "whatsapp")
            prioridade = dmn_result.get("prioridade", 5)
            next_steps = dmn_result.get("restricao", "Entre em contato com a central")

            # Send WhatsApp notification
            message_id = None
            if self.whatsapp_client:
                message_id = self.whatsapp_client.send_template(
                    to=phone_number,
                    template_name="auth_update_v1",
                    language_code="pt_BR",
                    body_params=[procedure_name, status, next_steps],
                )

            self.logger.info(
                "Authorization update notification sent",
                extra={
                    "tenant_id": context.tenant_id,
                    "patient_id": patient_id,
                    "authorization_id": authorization_id,
                    "status": status,
                },
            )

            return TaskResult.success({
                "notificationSent": True,
                "messageId": message_id,
                "sentAt": datetime.utcnow().isoformat(),
                "destino": destino,
                "prioridade": prioridade,
                "nextSteps": next_steps,
            })

        except Exception as e:
            self.logger.error(f"Auth update notification failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_AUTH_UPDATE_NOTIFICATION",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
