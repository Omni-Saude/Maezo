"""
Doctor Critical Value Worker

CIB7 External Task Topic: clinical.critical_value
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

URGENT notification for critical lab values requiring immediate attention.
PRIORITY: HIGHEST - bypasses ALL frequency limits.
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

logger = get_logger(__name__, worker="clinical.critical_value")


class ClinicalOperationsException(DomainException):
    """    Clinical operations domain exception.
    
        Archetype: CLINICAL_ALERT
        """

    bpmn_error_code: str = "CLINICAL_OPERATIONS_ERROR"


class DoctorCriticalValueInput(BaseModel):
    """Input model for doctor critical value worker."""

    doctor_id: str = Field(..., description=_("FHIR Practitioner ID"))
    phone_number: str = Field(..., description=_("Doctor phone E.164"))
    patient_id: str = Field(..., description=_("FHIR Patient ID"))
    patient_name: str = Field(..., description=_("Patient name"))
    lab_test: str = Field(..., description=_("Lab test name"))
    value: str = Field(..., description=_("Test result value"))
    unit: str = Field(..., description=_("Measurement unit"))
    critical_range: str = Field(
        ..., description=_("Critical range description")
    )
    timestamp: str = Field(..., description=_("Lab result timestamp ISO"))

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "doctor_id": self.doctor_id,
            "phone_number": self.phone_number,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "lab_test": self.lab_test,
            "value": self.value,
            "unit": self.unit,
            "critical_range": self.critical_range,
            "timestamp": self.timestamp,
        }


class DoctorCriticalValueOutput(BaseModel):
    """Output model for doctor critical value worker."""

    notification_sent: bool = Field(
        ..., description=_("Whether notification was sent successfully")
    )
    message_id: str | None = Field(
        None, description=_("WhatsApp message ID for tracking")
    )
    sent_at: str = Field(..., description=_("ISO timestamp of sending"))
    acknowledged: bool = Field(
        default=False, description=_("Initial acknowledgment status")
    )
    alert_id: str = Field(..., description=_("Unique alert identifier"))

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "notification_sent": self.notification_sent,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
            "acknowledged": self.acknowledged,
            "alert_id": self.alert_id,
        }


class DoctorCriticalValueWorker:
    """Worker for sending critical lab value alerts via WhatsApp."""

    TOPIC = "clinical.critical_value"
    PRIORITY = "critical"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize with WhatsApp client dependency."""
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _build_interactive_buttons(self, alert_id: str) -> list[dict]:
        """Build interactive button components for critical value response."""
        return [
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "0",
                "parameters": [
                    {
                        "type": "payload",
                        "payload": f"acknowledge:{alert_id}",
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
                        "payload": f"call_patient:{alert_id}",
                    }
                ],
            },
        ]

    def _build_template(
        self,
        patient_name: str,
        lab_test: str,
        value: str,
        unit: str,
        critical_range: str,
        alert_id: str,
    ) -> WhatsAppTemplate:
        """Build WhatsApp template for critical value alert."""
        body_component = {
            "type": "body",
            "parameters": [
                {"type": "text", "text": patient_name},
                {"type": "text", "text": lab_test},
                {"type": "text", "text": f"{value} {unit}"},
                {"type": "text", "text": critical_range},
            ],
        }

        button_components = self._build_interactive_buttons(alert_id)

        return WhatsAppTemplate(
            name="critical_value_v1",
            language="pt_BR",
            components=[body_component] + button_components,
        )

    @require_tenant
    @track_task_execution(task_type="clinical.critical_value")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute critical value alert worker.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If validation or sending fails
        """
        tenant_id = get_required_tenant().tenant_id

        logger.info(
            _("Iniciando worker de valor crítico tenant=%s"),
            tenant_id,
        )

        # Parse and validate input
        try:
            input_data = DoctorCriticalValueInput(**task_variables)
        except Exception as e:
            logger.error(
                _("Erro ao validar entrada: %s"),
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos: {error}").format(error=str(e))
            ) from e

        # Validate inputs
        if not input_data.doctor_id:
            logger.error(_("doctor_id não fornecido"))
            raise ClinicalOperationsException(_("doctor_id é obrigatório"))

        if not input_data.patient_id:
            logger.error(_("patient_id não fornecido"))
            raise ClinicalOperationsException(_("patient_id é obrigatório"))

        # Generate alert ID
        alert_id = str(uuid.uuid4())

        logger.warning(
            _(
                "VALOR CRÍTICO: doctor=%s patient=%s test=%s alert_id=%s"
            ),
            input_data.doctor_id[:8],  # Only log first 8 chars for privacy
            input_data.patient_id[:8],
            input_data.lab_test,
            alert_id,
        )

        # LGPD: NEVER log phone_number, patient_name, or lab values
        try:
            # Build template
            template = self._build_template(
                patient_name=input_data.patient_name,
                lab_test=input_data.lab_test,
                value=input_data.value,
                unit=input_data.unit,
                critical_range=input_data.critical_range,
                alert_id=alert_id,
            )

            # Send WhatsApp message
            message_id = await self._whatsapp_client.send_template_message(
                phone=input_data.phone_number, template=template
            )

            sent_at = datetime.now(timezone.utc).isoformat()

            logger.warning(
                _(
                    "Valor crítico enviado: alert_id=%s message_id=%s"
                ),
                alert_id,
                message_id,
            )

            # Build output
            output = DoctorCriticalValueOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                acknowledged=False,
                alert_id=alert_id,
            )

            logger.info(
                _("Worker de valor crítico concluído: %s"),
                alert_id,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro ao enviar valor crítico alert_id=%s: %s"),
                alert_id,
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar valor crítico: {error}").format(
                    error=str(e)
                )
            ) from e


# Worker configuration
TOPIC = "clinical.critical_value"
