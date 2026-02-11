"""
Doctor Performance Summary Worker

CIB7 External Task Topic: relationship.doctor_performance
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Sends weekly/monthly performance summary with badges and peer comparison.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError

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

logger = get_logger(__name__, worker="relationship.doctor_performance")


class ClinicalOperationsException(DomainException):
    """Clinical operations domain exception."""

    bpmn_error_code: str = "CLINICAL_OPERATIONS_ERROR"


class DoctorPerformanceSummaryInput(BaseModel):
    """Input model for doctor performance summary worker."""

    doctor_id: str = Field(..., description=_("FHIR Practitioner ID"))
    phone_number: str = Field(..., description=_("Doctor phone E.164"))
    period_start: str = Field(..., description=_("Period start ISO date"))
    period_end: str = Field(..., description=_("Period end ISO date"))
    patients_seen: int = Field(..., ge=0, description=_("Patients seen in period"))
    avg_satisfaction: float = Field(
        ..., ge=0, le=5, description=_("Average patient satisfaction 0-5")
    )
    outcomes_achieved: int = Field(
        ..., ge=0, description=_("Clinical outcomes achieved")
    )
    peer_comparison_percentile: int = Field(
        ..., ge=0, le=100, description=_("Peer comparison percentile")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "doctor_id": self.doctor_id,
            "phone_number": self.phone_number,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "patients_seen": self.patients_seen,
            "avg_satisfaction": self.avg_satisfaction,
            "outcomes_achieved": self.outcomes_achieved,
            "peer_comparison_percentile": self.peer_comparison_percentile,
        }


class DoctorPerformanceSummaryOutput(BaseModel):
    """Output model for doctor performance summary worker."""

    notification_sent: bool = Field(
        ..., description=_("Whether notification was sent successfully")
    )
    message_id: str | None = Field(
        None, description=_("WhatsApp message ID for tracking")
    )
    sent_at: str = Field(..., description=_("ISO timestamp of sending"))

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "notification_sent": self.notification_sent,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
        }


class DoctorPerformanceSummaryWorker:
    """Worker for sending performance summary via WhatsApp."""

    TOPIC = "relationship.doctor_performance"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """Initialize with WhatsApp client dependency."""
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    def _get_badges(
        self,
        patients_seen: int,
        avg_satisfaction: float,
        outcomes_achieved: int,
    ) -> list[str]:
        """
        Determine earned badges based on performance metrics.

        Returns:
            List of badge strings earned in the period.
        """
        badges: list[str] = []
        if patients_seen >= 100:
            badges.append("\U0001f3c6 Centenário")
        if avg_satisfaction >= 4.8:
            badges.append("\u2b50 Semana 5 Estrelas")
        if outcomes_achieved >= 50:
            badges.append("\U0001f3af Resultados Perfeitos")
        return badges

    def _build_template(
        self,
        input_data: DoctorPerformanceSummaryInput,
        badges: list[str],
    ) -> WhatsAppTemplate:
        """Build WhatsApp template for performance summary."""
        period_range = f"{input_data.period_start} - {input_data.period_end}"
        satisfaction_text = f"{input_data.avg_satisfaction:.1f}\u2b50"
        percentile_text = f"Top {input_data.peer_comparison_percentile}%"

        parameters = [
            {"type": "text", "text": period_range},
            {"type": "text", "text": str(input_data.patients_seen)},
            {"type": "text", "text": satisfaction_text},
            {"type": "text", "text": percentile_text},
        ]

        if badges:
            badges_text = " | ".join(badges)
            parameters.append({"type": "text", "text": badges_text})

        body_component = {"type": "body", "parameters": parameters}

        return WhatsAppTemplate(
            name="performance_summary_v1",
            language="pt_BR",
            components=[body_component],
        )

    @require_tenant
    @track_task_execution(task_type="relationship.doctor_performance")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute performance summary worker.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If validation or sending fails
        """
        tenant_id = get_required_tenant().tenant_id

        logger.info(
            _("Iniciando worker de performance summary tenant=%s"),
            tenant_id,
        )

        # Parse and validate input
        try:
            input_data = DoctorPerformanceSummaryInput(**task_variables)
        except ValidationError as e:
            logger.error(
                _("Erro ao validar entrada: %s"),
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos: {error}").format(error=str(e))
            ) from e

        # Calculate badges
        badges = self._get_badges(
            patients_seen=input_data.patients_seen,
            avg_satisfaction=input_data.avg_satisfaction,
            outcomes_achieved=input_data.outcomes_achieved,
        )

        logger.info(
            _("Performance summary: doctor=%s patients=%d satisfaction=%.1f badges=%d"),
            input_data.doctor_id[:8],
            input_data.patients_seen,
            input_data.avg_satisfaction,
            len(badges),
        )

        # LGPD: NEVER log phone_number
        try:
            template = self._build_template(input_data, badges)

            message_id = await self._whatsapp_client.send_template_message(
                phone=input_data.phone_number, template=template
            )

            sent_at = datetime.now(timezone.utc).isoformat()

            logger.info(
                _("Performance summary enviado: doctor=%s message_id=%s"),
                input_data.doctor_id[:8],
                message_id,
            )

            output = DoctorPerformanceSummaryOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro ao enviar performance summary doctor=%s: %s"),
                input_data.doctor_id[:8],
                str(e),
                exc_info=True,
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar performance summary: {error}").format(
                    error=str(e)
                )
            ) from e


# Worker configuration
TOPIC = "relationship.doctor_performance"
