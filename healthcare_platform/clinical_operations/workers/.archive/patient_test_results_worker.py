"""Patient Test Results Worker - Phase 5.3 Post-Discharge Continuity.

CIB7 Topic: continuity.results_available
Purpose: Notify patient when test/lab results are available.

This worker sends WhatsApp notifications to patients when their test or lab
results become available, with options to view results or schedule a discussion.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

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


class ClinicalOperationsException(DomainException):
    """    Exception raised for clinical operations errors.
    
        Archetype: COMPLIANCE_VALIDATION
        """

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="CLINICAL_OPERATIONS_ERROR",
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )


class PatientTestResultsInput(BaseModel):
    """Input for patient test results notification."""

    patient_id: str = Field(
        ..., description=_("ID FHIR do paciente")
    )
    phone_number: str = Field(
        ..., description=_("Telefone do paciente em formato E.164")
    )
    test_name: str = Field(
        ..., description=_("Nome do exame")
    )
    result_date: str = Field(
        ..., description=_("Data do resultado (ISO 8601)")
    )
    requires_followup: bool = Field(
        ..., description=_("Se requer consulta de acompanhamento")
    )
    portal_url: str = Field(
        ..., description=_("URL do portal do paciente")
    )


class PatientTestResultsOutput(BaseModel):
    """Output for patient test results notification."""

    notification_sent: bool = Field(
        ..., description=_("Se a notificação foi enviada com sucesso")
    )
    message_id: str | None = Field(
        ..., description=_("ID da mensagem do WhatsApp")
    )
    sent_at: str = Field(
        ..., description=_("Timestamp de envio (ISO 8601)")
    )
    notification_id: str = Field(
        ..., description=_("ID único da notificação")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert output to Temporal workflow variables."""
        return self.model_dump()


class PatientTestResultsWorker:
    """Worker for patient test results notifications."""

    TOPIC = "continuity.results_available"

    def __init__(self, whatsapp_client: WhatsAppClientProtocol | None = None) -> None:
        """Initialize the worker.

        Args:
            whatsapp_client: WhatsApp client instance (defaults to StubWhatsAppClient)
        """
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="continuity.results_available")
    def notify_test_results(
        self, input_data: PatientTestResultsInput
    ) -> PatientTestResultsOutput:
        """Send test results notification to patient.

        Args:
            input_data: Input data for test results notification

        Returns:
            Output data with notification status

        Raises:
            ClinicalOperationsException: If notification fails
        """
        tenant = get_required_tenant()

        # LGPD: Never log phone_number or portal_url (contains patient identifiers)
        logger.info(
            "Sending test results notification",
            extra={
                "patient_id": input_data.patient_id,
                "test_name": input_data.test_name,
                "requires_followup": input_data.requires_followup,
                "tenant_id": tenant.tenant_id,
            },
        )

        notification_id = str(uuid.uuid4())

        # Build followup message based on requirements
        followup_message = (
            "Recomendamos agendar uma consulta para discutir os resultados."
            if input_data.requires_followup
            else "Sem necessidade de acompanhamento adicional."
        )

        # Create WhatsApp template
        # Note: portal_url is used for deep linking when patient clicks "View Results"
        # but is not logged for LGPD compliance
        template = WhatsAppTemplate(
            name="results_available_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": input_data.test_name},
                        {"type": "text", "text": input_data.result_date},
                        {"type": "text", "text": followup_message},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 0,
                    "parameters": [
                        {"type": "payload", "payload": f"view_results:{notification_id}"}
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 1,
                    "parameters": [
                        {"type": "payload", "payload": f"schedule_discussion:{notification_id}"}
                    ],
                },
            ],
        )

        try:
            message_id = self.whatsapp_client.send_template(
                to=input_data.phone_number, template=template
            )

            sent_at = datetime.now(UTC).isoformat()

            logger.info(
                "Test results notification sent successfully",
                extra={
                    "patient_id": input_data.patient_id,
                    "notification_id": notification_id,
                    "tenant_id": tenant.tenant_id,
                },
            )

            return PatientTestResultsOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                notification_id=notification_id,
            )

        except Exception as e:
            logger.error(
                "Failed to send test results notification",
                extra={
                    "patient_id": input_data.patient_id,
                    "test_name": input_data.test_name,
                    "error": str(e),
                    "tenant_id": tenant.tenant_id,
                },
            )
            raise ClinicalOperationsException(
                message=_("Failed to send test results notification"),
                details={
                    "patient_id": input_data.patient_id,
                    "test_name": input_data.test_name,
                    "error": str(e),
                },
            ) from e


TOPIC = "continuity.results_available"
