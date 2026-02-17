"""
Doctor Rounds Summary Worker

CIB7 External Task Topic: inpatient.rounds_summary
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Sends daily rounds summary at 6AM with patient list and pending items.
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

logger = get_logger(__name__, worker="clinical.rounds_summary")


class ClinicalOperationsException(DomainException):
    """Clinical operations domain exception."""

    bpmn_error_code: str = "CLINICAL_OPERATIONS_ERROR"


class DoctorRoundsSummaryInput(BaseModel):
    """Input model for doctor rounds summary worker."""

    doctor_id: str = Field(..., description=_("FHIR Practitioner ID"))
    phone_number: str = Field(..., description=_("Doctor phone E.164"))
    date: str = Field(..., description=_("Date ISO format (YYYY-MM-DD)"))
    patient_list: list[dict[str, Any]] = Field(
        ...,
        description=_(
            "List of patients with id, name, room, pending_items"
        ),
    )
    total_patients: int = Field(..., description=_("Total number of patients"))

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "doctor_id": self.doctor_id,
            "phone_number": self.phone_number,
            "date": self.date,
            "patient_list": self.patient_list,
            "total_patients": self.total_patients,
        }


class DoctorRoundsSummaryOutput(BaseModel):
    """Output model for doctor rounds summary worker."""

    notification_sent: bool = Field(
        ..., description=_("Whether notification was sent successfully")
    )
    message_id: str | None = Field(
        None, description=_("WhatsApp message ID for tracking")
    )
    sent_at: str = Field(..., description=_("ISO timestamp of sending"))
    patients_included: int = Field(
        ..., description=_("Number of patients included in summary")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "notification_sent": self.notification_sent,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
            "patients_included": self.patients_included,
        }


class DoctorRoundsSummaryWorker:
    """Worker for sending daily rounds summary via WhatsApp."""

    TOPIC = "inpatient.rounds_summary"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize with WhatsApp client dependency."""
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _count_pending_items(
        self, patient_list: list[dict[str, Any]]
    ) -> dict[str, int]:
        """
        Count pending items by category across all patients.

        Returns:
            Dictionary with counts: {results: X, discharges: Y, orders: Z}
        """
        counts = {"results": 0, "discharges": 0, "orders": 0}

        for patient in patient_list:
            pending = patient.get("pending_items", {})
            counts["results"] += pending.get("results", 0)
            counts["discharges"] += pending.get("discharges", 0)
            counts["orders"] += pending.get("orders", 0)

        return counts

    def _build_template(
        self,
        doctor_id: str,
        total_patients: int,
        pending_results: int,
        pending_discharges: int,
    ) -> WhatsAppTemplate:
        """Build WhatsApp template for rounds summary."""
        body_component = {
            "type": "body",
            "parameters": [
                {"type": "text", "text": doctor_id},
                {"type": "text", "text": str(total_patients)},
                {"type": "text", "text": str(pending_results)},
                {"type": "text", "text": str(pending_discharges)},
            ],
        }

        return WhatsAppTemplate(
            name="rounds_summary_v1",
            language="pt_BR",
            components=[body_component],
        )

    @require_tenant
    @track_task_execution(task_type="inpatient.rounds_summary")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute rounds summary worker.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If validation or sending fails
        """
        tenant_id = get_required_tenant().tenant_id

        logger.info(
            _("Iniciando worker de resumo de rounds tenant=%s"),
            tenant_id,
        )

        # Parse and validate input
        try:
            input_data = DoctorRoundsSummaryInput(**task_variables)
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

        if input_data.total_patients < 0:
            logger.error(
                _("total_patients inválido: %d"), input_data.total_patients
            )
            raise ClinicalOperationsException(
                _("total_patients deve ser >= 0")
            )

        # Count pending items
        pending_counts = self._count_pending_items(input_data.patient_list)

        logger.info(
            _("Resumo de rounds: doctor=%s pacientes=%d pendentes=%s"),
            input_data.doctor_id[:8],  # Only log first 8 chars for privacy
            input_data.total_patients,
            str(pending_counts),
        )

        # LGPD: NEVER log phone_number or patient details
        try:
            # Build template
            template = self._build_template(
                doctor_id=input_data.doctor_id,
                total_patients=input_data.total_patients,
                pending_results=pending_counts["results"],
                pending_discharges=pending_counts["discharges"],
            )

            # Send WhatsApp message
            message_id = await self._whatsapp_client.send_template_message(
                phone=input_data.phone_number, template=template
            )

            sent_at = datetime.now(timezone.utc).isoformat()

            logger.info(
                _("Resumo de rounds enviado: date=%s message_id=%s"),
                input_data.date,
                message_id,
            )

            # Build output
            output = DoctorRoundsSummaryOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                patients_included=input_data.total_patients,
            )

            logger.info(
                _("Worker de resumo de rounds concluído: %s"),
                input_data.date,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro ao enviar resumo de rounds date=%s: %s"),
                input_data.date,
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar resumo de rounds: {error}").format(
                    error=str(e)
                )
            ) from e


# Worker configuration
TOPIC = "inpatient.rounds_summary"
