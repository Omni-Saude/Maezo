"""
Patient Care Team Introduction Worker

CIB7 External Task Topic: inpatient.care_team_intro
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Introduces care team members to patient on admission via WhatsApp.
Provides team composition, roles, and unit information.
"""

from __future__ import annotations

import logging
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
    """    Exception for clinical operations errors.
    
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


class PatientCareTeamIntroInput(BaseModel):
    """Input model for patient care team introduction."""

    patient_id: str = Field(..., description=_("FHIR Patient ID"))
    phone_number: str = Field(..., description=_("Patient phone in E.164 format"))
    care_team: list[dict[str, str]] = Field(
        ..., description=_("Care team members with name, role, photo_url")
    )
    unit_info: dict[str, str] = Field(
        ..., description=_("Unit information with name, floor, phone")
    )


class PatientCareTeamIntroOutput(BaseModel):
    """Output model for patient care team introduction."""

    notification_sent: bool = Field(..., description=_("Whether notification was sent"))
    message_id: str | None = Field(
        None, description=_("WhatsApp message ID if sent successfully")
    )
    sent_at: str = Field(
        ..., description=_("ISO 8601 timestamp when notification sent")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert output to Camunda process variables."""
        return self.model_dump()


class PatientCareTeamIntroWorker:
    """
    Worker to introduce care team members to patient on admission.

    Sends WhatsApp notification with care team composition and unit details.
    """

    TOPIC = "inpatient.care_team_intro"

    def __init__(
        self, whatsapp_client: WhatsAppClientProtocol | None = None
    ) -> None:
        """
        Initialize worker with WhatsApp client.

        Args:
            whatsapp_client: WhatsApp client for sending messages.
                           Defaults to StubWhatsAppClient for testing.
        """
        self._whatsapp_client = whatsapp_client or StubWhatsAppClient()

    @require_tenant
    @track_task_execution(task_type="inpatient.care_team_intro")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute care team introduction notification.

        Args:
            task_variables: Task variables containing care team details

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If notification fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = PatientCareTeamIntroInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for care team introduction input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para apresentação da equipe de cuidado"),
                details={"validation_error": str(e)},
            ) from e

        # Log care team introduction (LGPD: no phone_number)
        logger.info(
            "Processing care team introduction notification",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": input_data.patient_id,
                "team_size": len(input_data.care_team),
                "unit": input_data.unit_info.get("name", "Unknown"),
            },
        )

        # Format care team summary
        team_summary = self._format_care_team(input_data.care_team)
        unit_name = input_data.unit_info.get("name", "")
        unit_floor = input_data.unit_info.get("floor", "")

        # Build WhatsApp template
        template = WhatsAppTemplate(
            name="care_team_intro_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": team_summary},
                        {"type": "text", "text": unit_name},
                        {"type": "text", "text": unit_floor},
                    ],
                }
            ],
        )

        # Send notification
        try:
            message_id = self._whatsapp_client.send_template_message(
                phone_number=input_data.phone_number,
                template=template,
            )

            sent_at = datetime.now(UTC).isoformat()

            logger.info(
                "Care team introduction notification sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "message_id": message_id,
                    "team_size": len(input_data.care_team),
                },
            )

            # Build output
            output = PatientCareTeamIntroOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                "Failed to send care team introduction notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar apresentação da equipe de cuidado"),
                details={
                    "patient_id": input_data.patient_id,
                    "error": str(e),
                },
            ) from e

    def _format_care_team(self, care_team: list[dict[str, str]]) -> str:
        """
        Format care team members into readable summary.

        Args:
            care_team: List of team members with name and role

        Returns:
            Formatted care team summary (e.g., "Dr. Silva (Médico), Ana Costa (Enfermeira)")
        """
        if not care_team:
            return "Equipe não definida"

        formatted_members = []
        for member in care_team:
            name = member.get("name", "")
            role = member.get("role", "")
            if name and role:
                formatted_members.append(f"{name} ({role})")
            elif name:
                formatted_members.append(name)

        return ", ".join(formatted_members) if formatted_members else "Equipe não definida"


TOPIC = "inpatient.care_team_intro"
