"""
Doctor Discharge Readiness Worker

CIB7 External Task Topic: inpatient.discharge_ready
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Notifies doctor when patient meets discharge criteria.
Includes interactive buttons: [Review Now] [Schedule Later].
"""
from __future__ import annotations

import uuid
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

logger = get_logger(__name__, worker="clinical.discharge_ready")


class ClinicalOperationsException(DomainException):
    """Clinical operations domain exception."""

    bpmn_error_code: str = "CLINICAL_OPERATIONS_ERROR"


class DoctorDischargeReadinessInput(BaseModel):
    """Input model for doctor discharge readiness worker."""

    doctor_id: str = Field(
        ..., description=_("FHIR Practitioner ID of attending doctor")
    )
    phone_number: str = Field(..., description=_("Doctor phone E.164"))
    patient_id: str = Field(..., description=_("FHIR Patient ID"))
    patient_name: str = Field(..., description=_("Patient full name"))
    room: str = Field(..., description=_("Hospital room number"))
    admission_date: str = Field(
        ..., description=_("Admission date in ISO 8601 format")
    )
    discharge_criteria_met: list[str] = Field(
        ..., description=_("List of discharge criteria met")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "doctor_id": self.doctor_id,
            "phone_number": self.phone_number,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "room": self.room,
            "admission_date": self.admission_date,
            "discharge_criteria_met": self.discharge_criteria_met,
        }


class DoctorDischargeReadinessOutput(BaseModel):
    """Output model for doctor discharge readiness worker."""

    notification_sent: bool = Field(
        ..., description=_("Whether notification was sent successfully")
    )
    message_id: str | None = Field(
        None, description=_("WhatsApp message ID for tracking")
    )
    sent_at: str = Field(..., description=_("ISO 8601 timestamp when sent"))
    discharge_review_id: str = Field(
        ..., description=_("Generated UUID for tracking discharge review")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "notification_sent": self.notification_sent,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
            "discharge_review_id": self.discharge_review_id,
        }


class DoctorDischargeReadinessWorker:
    """Worker for notifying doctor about discharge readiness via WhatsApp."""

    TOPIC = "inpatient.discharge_ready"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize with WhatsApp client dependency."""
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _build_interactive_buttons(self, discharge_review_id: str) -> list[dict]:
        """Build interactive button components for discharge review."""
        return [
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "0",
                "parameters": [
                    {
                        "type": "payload",
                        "payload": f"review_now:{discharge_review_id}",
                    }
                ],
            },
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "1",
                "parameters": [
                    {
                        "type": "payload",
                        "payload": f"schedule_later:{discharge_review_id}",
                    }
                ],
            },
        ]

    def _build_template(
        self,
        patient_name: str,
        room: str,
        admission_date: str,
        criteria_count: int,
        discharge_review_id: str,
    ) -> WhatsAppTemplate:
        """Build WhatsApp template for discharge readiness notification."""
        body_component = {
            "type": "body",
            "parameters": [
                {"type": "text", "text": patient_name},
                {"type": "text", "text": room},
                {"type": "text", "text": admission_date},
                {"type": "text", "text": str(criteria_count)},
            ],
        }

        button_components = self._build_interactive_buttons(discharge_review_id)

        return WhatsAppTemplate(
            name="discharge_ready_v1",
            language="pt_BR",
            components=[body_component] + button_components,
        )

    @require_tenant
    @track_task_execution(task_type="inpatient.discharge_ready")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute discharge readiness notification worker.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If validation or sending fails
        """
        tenant_id = get_required_tenant().tenant_id

        logger.info(
            _("Iniciando worker de alta pronta tenant=%s"),
            tenant_id,
        )

        # Parse and validate input
        try:
            input_data = DoctorDischargeReadinessInput(**task_variables)
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

        if not input_data.discharge_criteria_met:
            logger.error(_("discharge_criteria_met não fornecido"))
            raise ClinicalOperationsException(
                _("discharge_criteria_met é obrigatório")
            )

        # Generate discharge review ID
        discharge_review_id = str(uuid.uuid4())
        sent_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            _("Notificando alta pronta doctor=%s review_id=%s"),
            input_data.doctor_id[:8],  # Only log first 8 chars for privacy
            discharge_review_id,
        )

        # LGPD: NEVER log phone_number or patient_name
        try:
            # Build template
            template = self._build_template(
                patient_name=input_data.patient_name,
                room=input_data.room,
                admission_date=input_data.admission_date,
                criteria_count=len(input_data.discharge_criteria_met),
                discharge_review_id=discharge_review_id,
            )

            # Send WhatsApp message
            message_id = await self._whatsapp_client.send_template_message(
                phone=input_data.phone_number, template=template
            )

            logger.info(
                _("Alta pronta enviada: review_id=%s message_id=%s"),
                discharge_review_id,
                message_id,
            )

            # Build output
            output = DoctorDischargeReadinessOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                discharge_review_id=discharge_review_id,
            )

            logger.info(
                _("Worker de alta pronta concluído: %s"),
                discharge_review_id,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro ao enviar alta pronta review_id=%s: %s"),
                discharge_review_id,
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar alta pronta: {error}").format(error=str(e))
            ) from e


# Worker configuration
TOPIC = "inpatient.discharge_ready"
