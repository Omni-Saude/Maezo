"""Patient Medication Adherence Worker - Phase 5.3 Post-Discharge Continuity.

CIB7 Topic: continuity.medication_adherence
Purpose: Daily check on post-discharge medication adherence.

This worker sends WhatsApp notifications to patients to check their medication
adherence after discharge. If the patient reports side effects or missed doses,
the response should be escalated to the care team via BPMN.
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
    """Exception raised for clinical operations errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="CLINICAL_OPERATIONS_ERROR",
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )


class PatientMedicationAdherenceInput(BaseModel):
    """Input for patient medication adherence notification."""

    patient_id: str = Field(
        ..., description=_("ID FHIR do paciente")
    )
    phone_number: str = Field(
        ..., description=_("Telefone do paciente em formato E.164")
    )
    medications: list[dict[str, str]] = Field(
        ..., description=_("Lista de medicamentos (name, dosage, frequency)")
    )
    days_since_discharge: int = Field(
        ..., description=_("Dias desde a alta")
    )


class PatientMedicationAdherenceOutput(BaseModel):
    """Output for patient medication adherence notification."""

    notification_sent: bool = Field(
        ..., description=_("Se a notificação foi enviada com sucesso")
    )
    message_id: str | None = Field(
        ..., description=_("ID da mensagem do WhatsApp")
    )
    sent_at: str = Field(
        ..., description=_("Timestamp de envio (ISO 8601)")
    )
    adherence_id: str = Field(
        ..., description=_("ID único da verificação de aderência")
    )
    response_received: bool = Field(
        default=False, description=_("Se a resposta foi recebida")
    )
    adherence_status: str | None = Field(
        default=None,
        description=_("Status da aderência (all_taken/missed_some/need_refill/side_effects)"),
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert output to Temporal workflow variables."""
        return self.model_dump()


class PatientMedicationAdherenceWorker:
    """Worker for patient medication adherence notifications.

    Archetype: CLINICAL_ALERT
    """

    TOPIC = "continuity.medication_adherence"

    def __init__(self, whatsapp_client: WhatsAppClientProtocol | None = None) -> None:
        """Initialize the worker.

        Args:
            whatsapp_client: WhatsApp client instance (defaults to StubWhatsAppClient)
        """
        self.whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="continuity.medication_adherence")
    def check_medication_adherence(
        self, input_data: PatientMedicationAdherenceInput
    ) -> PatientMedicationAdherenceOutput:
        """Send medication adherence check to patient.

        Args:
            input_data: Input data for medication adherence check

        Returns:
            Output data with notification status

        Raises:
            ClinicalOperationsException: If notification fails
        """
        tenant = get_required_tenant()

        # LGPD: Never log phone_number or medication details
        logger.info(
            "Sending medication adherence check",
            extra={
                "patient_id": input_data.patient_id,
                "days_since_discharge": input_data.days_since_discharge,
                "tenant_id": tenant.tenant_id,
            },
        )

        adherence_id = str(uuid.uuid4())

        # Build medication list for template
        medication_names = [med.get("name", "Unknown") for med in input_data.medications]
        medication_list = ", ".join(medication_names)

        # Create WhatsApp template
        # CRITICAL: If patient responds with side_effects or missed_some,
        # this should be escalated to the care team via BPMN workflow
        template = WhatsAppTemplate(
            name="medication_adherence_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": medication_list},
                        {"type": "text", "text": str(input_data.days_since_discharge)},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 0,
                    "parameters": [
                        {"type": "payload", "payload": f"all_taken:{adherence_id}"}
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 1,
                    "parameters": [
                        {"type": "payload", "payload": f"missed_some:{adherence_id}"}
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 2,
                    "parameters": [
                        {"type": "payload", "payload": f"need_refill:{adherence_id}"}
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 3,
                    "parameters": [
                        {"type": "payload", "payload": f"side_effects:{adherence_id}"}
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
                "Medication adherence check sent successfully",
                extra={
                    "patient_id": input_data.patient_id,
                    "adherence_id": adherence_id,
                    "tenant_id": tenant.tenant_id,
                },
            )

            return PatientMedicationAdherenceOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                adherence_id=adherence_id,
                response_received=False,
                adherence_status=None,
            )

        except Exception as e:
            logger.error(
                "Failed to send medication adherence check",
                extra={
                    "patient_id": input_data.patient_id,
                    "error": str(e),
                    "tenant_id": tenant.tenant_id,
                },
            )
            raise ClinicalOperationsException(
                message=_("Failed to send medication adherence check"),
                details={"patient_id": input_data.patient_id, "error": str(e)},
            ) from e


TOPIC = "continuity.medication_adherence"
