"""
Patient Authorization Update Worker

Notifies patient of authorization status changes via WhatsApp.
Triggered by CIB7 topic: financial.auth_update

LGPD Compliance:
- Never logs phone_number or sensitive patient information
- Provides clear next steps for each authorization status

Architecture:
- Pydantic Input/Output models with Field descriptions
- @require_tenant and @track_task_execution decorators
- Validates input and wraps ValidationError in domain exception
- Uses WhatsAppClientProtocol for testing
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.whatsapp_client import (
    StubWhatsAppClient,
    WhatsAppClientProtocol,
    WhatsAppTemplate,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class RevenueCycleException(DomainException):
    """Revenue Cycle domain exception."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="REVENUE_CYCLE_ERROR",
            details=details,
            bpmn_error_code="REVENUE_CYCLE_ERROR",
        )


class PatientAuthorizationUpdateInput(BaseModel):
    """Input model for authorization status update notification."""

    patient_id: str = Field(..., description="Patient identifier")
    phone_number: str = Field(..., description="Patient phone number (E.164 format)")
    authorization_id: str = Field(..., description="Authorization request identifier")
    procedure_name: str = Field(..., description="Name of the procedure/service")
    status: Literal["approved", "denied", "pending"] = Field(
        ..., description="Authorization status"
    )
    reason: str | None = Field(None, description="Reason for status (especially for denials)")
    next_steps: str | None = Field(None, description="Next steps instructions for patient")


class PatientAuthorizationUpdateOutput(BaseModel):
    """Output model for authorization update notification."""

    notification_sent: bool = Field(..., description="Whether notification was sent")
    message_id: str | None = Field(None, description="WhatsApp message ID")
    sent_at: str = Field(..., description="ISO 8601 timestamp when sent")


class PatientAuthorizationUpdateWorker:
    """
    Worker to send authorization status updates via WhatsApp.

    Provides status-specific instructions and next steps.
    """

    TOPIC = "financial.auth_update"

    # Status label mapping
    STATUS_LABELS = {
        "approved": "Aprovado",
        "denied": "Negado",
        "pending": "Em Análise",
    }

    # Default next steps by status
    DEFAULT_NEXT_STEPS = {
        "approved": "Procedimento autorizado. Agende pelo portal ou ligue para a central.",
        "denied": "Para recorrer, ligue para 0800-XXX-XXXX ou acesse o portal.",
        "pending": "Aguarde a análise. Prazo estimado: 5 dias úteis.",
    }

    def __init__(self, whatsapp_client: WhatsAppClientProtocol | None = None):
        """
        Initialize worker with WhatsApp client.

        Args:
            whatsapp_client: WhatsApp client (defaults to stub)
        """
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute authorization update notification.

        Args:
            task_variables: Task variables from BPMN process

        Returns:
            dict with notification_sent, message_id, sent_at

        Raises:
            RevenueCycleException: If validation fails or notification fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = PatientAuthorizationUpdateInput(**task_variables)
        except ValidationError as e:
            logger.error(
                "Invalid authorization update input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                    "patient_id": task_variables.get("patient_id"),
                },
            )
            raise RevenueCycleException(
                message=_("Invalid authorization update input"),
                details={"validation_errors": e.errors()},
            )

        # Get status label
        status_label = self.STATUS_LABELS.get(input_data.status, input_data.status)

        # Get next steps (use provided or default)
        next_steps = input_data.next_steps or self.DEFAULT_NEXT_STEPS.get(
            input_data.status, "Entre em contato com a central de atendimento."
        )

        # Build template
        template = WhatsAppTemplate(
            name="auth_update_v1",
            language_code="pt_BR",
            body_params=[
                input_data.procedure_name,
                status_label,
                next_steps,
            ],
        )

        # Send notification
        try:
            message_id = self._whatsapp_client.send_template_message(
                phone_number=input_data.phone_number,
                template=template,
            )
            logger.info(
                "Authorization update notification sent",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "authorization_id": input_data.authorization_id,
                    "status": input_data.status,
                    "message_id": message_id,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to send authorization update notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "authorization_id": input_data.authorization_id,
                    "status": input_data.status,
                    "error": str(e),
                },
            )
            raise RevenueCycleException(
                message=_("Failed to send authorization update"),
                details={"error": str(e)},
            )

        # Build output
        sent_at = datetime.now(timezone.utc).isoformat()
        output = PatientAuthorizationUpdateOutput(
            notification_sent=True,
            message_id=message_id,
            sent_at=sent_at,
        )

        return output.model_dump()
