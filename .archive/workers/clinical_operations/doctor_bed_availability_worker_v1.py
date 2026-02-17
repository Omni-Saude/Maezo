"""
Doctor Bed Availability Worker
CIB7 External Task Topic: inpatient.bed_available
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Notifies doctor when bed becomes available for pending admission.
No interactive buttons, just template message notification.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.whatsapp_client import (
    WhatsAppClientProtocol,
    WhatsAppTemplate,
    StubWhatsAppClient,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__, worker="clinical.bed_available")


class ClinicalOperationsException(DomainException):
    """Clinical operations domain exception."""

    bpmn_error_code: str = "CLINICAL_OPERATIONS_ERROR"


class DoctorBedAvailabilityInput(BaseModel):
    """Input model for doctor bed availability worker."""

    doctor_id: str = Field(
        ..., description=_("FHIR Practitioner ID of attending doctor")
    )
    phone_number: str = Field(..., description=_("Doctor phone E.164"))
    patient_id: str = Field(..., description=_("FHIR Patient ID"))
    patient_name: str = Field(..., description=_("Patient full name"))
    bed_id: str = Field(..., description=_("Bed identifier"))
    unit: str = Field(..., description=_("Hospital unit name"))
    bed_type: str = Field(..., description=_("Bed type (e.g., UTI, enfermaria)"))
    available_since: str = Field(
        ..., description=_("Availability timestamp in ISO 8601 format")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "doctor_id": self.doctor_id,
            "phone_number": self.phone_number,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "bed_id": self.bed_id,
            "unit": self.unit,
            "bed_type": self.bed_type,
            "available_since": self.available_since,
        }


class DoctorBedAvailabilityOutput(BaseModel):
    """Output model for doctor bed availability worker."""

    notification_sent: bool = Field(
        ..., description=_("Whether notification was sent successfully")
    )
    message_id: str | None = Field(
        None, description=_("WhatsApp message ID for tracking")
    )
    sent_at: str = Field(..., description=_("ISO 8601 timestamp when sent"))

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "notification_sent": self.notification_sent,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
        }


class DoctorBedAvailabilityWorker:
    """Worker for notifying doctor about bed availability via WhatsApp."""

    TOPIC = "inpatient.bed_available"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize with WhatsApp client dependency."""
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _build_template(
        self, unit: str, bed_type: str, patient_name: str, bed_id: str
    ) -> WhatsAppTemplate:
        """Build WhatsApp template for bed availability notification."""
        body_component = {
            "type": "body",
            "parameters": [
                {"type": "text", "text": unit},
                {"type": "text", "text": bed_type},
                {"type": "text", "text": patient_name},
                {"type": "text", "text": bed_id},
            ],
        }

        return WhatsAppTemplate(
            name="bed_available_v1",
            language="pt_BR",
            components=[body_component],
        )

    @require_tenant
    @track_task_execution(task_type="inpatient.bed_available")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute bed availability notification worker.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If validation or sending fails
        """
        tenant_id = get_required_tenant().tenant_id

        logger.info(
            _("Iniciando worker de leito disponível tenant=%s"),
            tenant_id,
        )

        # Parse and validate input
        try:
            input_data = DoctorBedAvailabilityInput(**task_variables)
        except Exception as e:
            logger.error(
                _("Erro ao validar entrada: %s"),
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos: {error}").format(error=str(e))
            ) from e

        # Validate required fields
        if not input_data.doctor_id:
            logger.error(_("doctor_id não fornecido"))
            raise ClinicalOperationsException(_("doctor_id é obrigatório"))

        if not input_data.bed_id:
            logger.error(_("bed_id não fornecido"))
            raise ClinicalOperationsException(_("bed_id é obrigatório"))

        sent_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            _("Notificando leito disponível doctor=%s bed=%s"),
            input_data.doctor_id[:8],  # Only log first 8 chars for privacy
            input_data.bed_id,
        )

        # LGPD: NEVER log phone_number or patient_name
        try:
            # Build template
            template = self._build_template(
                unit=input_data.unit,
                bed_type=input_data.bed_type,
                patient_name=input_data.patient_name,
                bed_id=input_data.bed_id,
            )

            # Send WhatsApp message
            message_id = await self._whatsapp_client.send_template_message(
                phone=input_data.phone_number, template=template
            )

            logger.info(
                _("Leito disponível enviado: bed=%s message_id=%s"),
                input_data.bed_id,
                message_id,
            )

            # Build output
            output = DoctorBedAvailabilityOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            logger.info(
                _("Worker de leito disponível concluído: bed=%s"),
                input_data.bed_id,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro ao enviar leito disponível bed=%s: %s"),
                input_data.bed_id,
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar leito disponível: {error}").format(
                    error=str(e)
                )
            ) from e


# Worker configuration
TOPIC = "inpatient.bed_available"
