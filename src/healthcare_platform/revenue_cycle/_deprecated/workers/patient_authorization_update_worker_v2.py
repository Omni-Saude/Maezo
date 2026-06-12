"""
Patient Authorization Update Notification Worker (Refactored)
Purpose: Notify patient of authorization status changes via WhatsApp

TOPIC: financial.auth_update

Refactored using template-first approach:
- STATUS_LABELS/DEFAULT_NEXT_STEPS dicts extracted to DMN: patient_auth_notification_routing.dmn
- Worker focuses on: DMN evaluation + WhatsApp notification send

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError

from healthcare_platform.shared.domain.exceptions import RevenueCycleException
from healthcare_platform.shared.integrations.whatsapp_client import (
    WhatsAppClientProtocol,
    WhatsAppTemplate,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


# ── Pydantic Models (for backward compat with tests) ──

class PatientAuthorizationUpdateInput(BaseModel):
    """Input model for authorization status update notification."""
    patient_id: str = Field(..., description="Patient identifier")
    phone_number: str = Field(..., description="Patient phone number (E.164 format)")
    authorization_id: str = Field(..., description="Authorization request identifier")
    procedure_name: str = Field(..., description="Name of the procedure/service")
    status: str = Field(..., description="Authorization status: approved, denied, pending")
    reason: Optional[str] = Field(None, description="Reason for status")
    next_steps: Optional[str] = Field(None, description="Next steps instructions")


class PatientAuthorizationUpdateWorker(BaseExternalTaskWorker):
    """
    Refactored patient authorization update worker.

    Responsibilities (thin worker pattern):
    1. Parse input variables
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

    def execute_task(self, context: TaskContext) -> TaskResult:
        """Execute patient authorization update notification for Camunda."""
        try:
            variables = context.variables
            patient_id = variables.get("patient_id", "")
            phone_number = variables.get("phone_number", "")
            authorization_id = variables.get("authorization_id", "")
            procedure_name = variables.get("procedure_name", "")
            status = variables.get("status", "")

            if not patient_id or not phone_number or not status:
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_INPUT",
                    error_message="Missing patient_id, phone_number, or status",
                )

            # Evaluate DMN for routing and next steps
            dmn_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DECISION_KEY,
                variables={"authorizationStatus": status},
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
                "notification_sent": True,
                "message_id": message_id,
                "sent_at": datetime.utcnow().isoformat(),
                "destino": destino,
                "prioridade": prioridade,
                "next_steps": next_steps,
            })

        except Exception as e:
            self.logger.error(f"Auth update notification failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_AUTH_UPDATE_NOTIFICATION",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )

    # ── Async execute for backward compatibility with tests ──

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Async execute method for backward compatibility with old tests.

        This method validates input with Pydantic and raises RevenueCycleException
        on errors, matching the old worker API.
        """
        _tenant = get_required_tenant()

        # Handle TaskContext or Dict input
        if isinstance(task_variables, TaskContext):
            task_variables = task_variables.variables

        # Validate input
        try:
            input_data = PatientAuthorizationUpdateInput(**task_variables)
        except ValidationError as e:
            raise RevenueCycleException(
                message="Invalid authorization update input",
                details={"validation_errors": e.errors()},
            ) from e

        # Status labels for WhatsApp
        STATUS_LABELS = {
            "approved": "Aprovado",
            "denied": "Negado",
            "pending": "Em Análise",
        }

        DEFAULT_NEXT_STEPS = {
            "approved": "Procedimento autorizado. Agende pelo portal ou ligue para a central.",
            "denied": "Para recorrer, ligue para 0800-XXX-XXXX ou acesse o portal.",
            "pending": "Aguarde a análise. Prazo estimado: 5 dias úteis.",
        }

        status_label = STATUS_LABELS.get(input_data.status, input_data.status)
        next_steps = input_data.next_steps or DEFAULT_NEXT_STEPS.get(
            input_data.status, "Entre em contato com a central de atendimento."
        )

        # Send notification
        try:
            message_id = None
            if self.whatsapp_client:
                template = WhatsAppTemplate(
                    name="auth_update_v1",
                    language_code="pt_BR",
                    body_params=[input_data.procedure_name, status_label, next_steps],
                )
                message_id = self.whatsapp_client.send_template_message(
                    phone_number=input_data.phone_number,
                    template=template,
                )

            return {
                "notification_sent": True,
                "message_id": message_id,
                "sent_at": datetime.utcnow().isoformat() + "Z",
            }
        except Exception as e:
            raise RevenueCycleException(
                message="Failed to send authorization update",
                details={"error": str(e), "patient_id": input_data.patient_id},
            ) from e
