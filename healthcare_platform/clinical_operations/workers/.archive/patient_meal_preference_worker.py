"""
Patient Meal Preference Worker

CIB7 External Task Topic: inpatient.meal_choice
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Collects meal preference from inpatient via WhatsApp interactive LIST message.
Supports dietary restrictions and meal type validation.
"""

from __future__ import annotations

import logging
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

VALID_MEAL_TYPES = {"breakfast", "lunch", "dinner"}


class ClinicalOperationsException(DomainException):
    """    Exception for clinical operations errors.
    
        Archetype: CLINICAL_ALERT
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


class PatientMealPreferenceInput(BaseModel):
    """Input model for patient meal preference collection."""

    patient_id: str = Field(..., description=_("FHIR Patient ID"))
    phone_number: str = Field(..., description=_("Patient phone in E.164 format"))
    meal_type: str = Field(
        ..., description=_("Meal type: breakfast, lunch, or dinner")
    )
    options: list[dict[str, str]] = Field(
        ..., description=_("List of meal options with id, title, description")
    )
    dietary_restrictions: list[str] = Field(
        default_factory=list, description=_("Patient dietary restrictions")
    )


class PatientMealPreferenceOutput(BaseModel):
    """Output model for patient meal preference collection."""

    notification_sent: bool = Field(..., description=_("Whether notification was sent"))
    message_id: str | None = Field(
        None, description=_("WhatsApp message ID if sent successfully")
    )
    sent_at: str = Field(
        ..., description=_("ISO 8601 timestamp when notification sent")
    )
    selection_received: bool = Field(
        default=False, description=_("Whether patient selection was received")
    )
    selected_option: str | None = Field(
        None, description=_("Selected meal option ID")
    )
    meal_request_id: str = Field(..., description=_("Unique meal request identifier"))

    def to_variables(self) -> dict[str, Any]:
        """Convert output to Camunda process variables."""
        return self.model_dump()


class PatientMealPreferenceWorker:
    """
    Worker to collect patient meal preference via WhatsApp interactive list.

    Sends interactive list message to patient for meal selection.
    Supports dietary restrictions and validates meal type.
    """

    TOPIC = "inpatient.meal_choice"

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
    @track_task_execution(task_type="inpatient.meal_choice")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute meal preference collection.

        Args:
            task_variables: Task variables containing meal selection details

        Returns:
            Dictionary with notification results

        Raises:
            ClinicalOperationsException: If notification fails or validation fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = PatientMealPreferenceInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for meal preference input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para preferência de refeição"),
                details={"validation_error": str(e)},
            ) from e

        # Validate meal type
        if input_data.meal_type not in VALID_MEAL_TYPES:
            raise ClinicalOperationsException(
                _("Tipo de refeição inválido"),
                details={
                    "meal_type": input_data.meal_type,
                    "valid_types": list(VALID_MEAL_TYPES),
                },
            )

        # Generate unique meal request ID
        meal_request_id = str(uuid.uuid4())

        # Log meal preference request (LGPD: no phone_number)
        logger.info(
            "Processing meal preference collection",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": input_data.patient_id,
                "meal_type": input_data.meal_type,
                "meal_request_id": meal_request_id,
                "option_count": len(input_data.options),
            },
        )

        # Build dietary info text
        dietary_info = (
            ", ".join(input_data.dietary_restrictions)
            if input_data.dietary_restrictions
            else "Nenhuma"
        )

        # Build list sections for interactive message
        list_sections = self._build_list_sections(
            input_data.meal_type, input_data.options
        )

        # Build WhatsApp template with list components
        template = WhatsAppTemplate(
            name="meal_choice_v1",
            language="pt_BR",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": input_data.meal_type},
                        {"type": "text", "text": dietary_info},
                    ],
                },
                {
                    "type": "interactive",
                    "sub_type": "list",
                    "parameters": [
                        {
                            "type": "action",
                            "action": {
                                "button": "Ver opções",
                                "sections": list_sections,
                            },
                        }
                    ],
                },
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
                "Meal preference notification sent successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "message_id": message_id,
                    "meal_request_id": meal_request_id,
                    "meal_type": input_data.meal_type,
                },
            )

            # Build output
            output = PatientMealPreferenceOutput(
                notification_sent=True,
                message_id=message_id,
                sent_at=sent_at,
                selection_received=False,
                selected_option=None,
                meal_request_id=meal_request_id,
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                "Failed to send meal preference notification",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "meal_request_id": meal_request_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha ao enviar notificação de preferência de refeição"),
                details={
                    "patient_id": input_data.patient_id,
                    "meal_request_id": meal_request_id,
                    "error": str(e),
                },
            ) from e

    def _build_list_sections(
        self, meal_type: str, options: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        """
        Build WhatsApp list sections from meal options.

        Args:
            meal_type: Type of meal (breakfast/lunch/dinner)
            options: List of meal options with id, title, description

        Returns:
            List sections formatted for WhatsApp interactive list
        """
        rows = []
        for opt in options:
            rows.append(
                {
                    "id": opt["id"],
                    "title": opt["title"],
                    "description": opt.get("description", ""),
                }
            )

        return [
            {
                "title": meal_type.capitalize(),
                "rows": rows,
            }
        ]


TOPIC = "inpatient.meal_choice"
