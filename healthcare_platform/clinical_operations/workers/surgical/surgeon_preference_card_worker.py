"""
Surgeon Preference Card Worker - Surgeon equipment and setup preferences.

CIB7 External Task Topic: surgical.preference_card
BPMN Error Code: SURGICAL_OPERATIONS_ERROR

Manages surgeon preference cards for surgical procedures.
Ensures correct equipment, positioning, and setup per surgeon preferences.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import TasySurgicalAdapter
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__, worker="surgical.preference_card")

TOPIC = "surgical.preference_card"


class SurgicalOperationsException(DomainException):
    """Exception for surgical operations failures."""

    bpmn_error_code = "SURGICAL_OPERATIONS_ERROR"


class PreferenceItem(BaseModel):
    """Individual preference item for surgical setup."""

    item_name: str = Field(..., description="Name of the item")
    item_code: Optional[str] = Field(None, description="Item catalog code")
    category: str = Field(
        ...,
        description="Item category",
        pattern="^(instrument|suture|implant|supply|medication)$"
    )
    quantity: int = Field(..., description="Quantity required", ge=1)
    size: Optional[str] = Field(None, description="Item size if applicable")
    special_instructions: Optional[str] = Field(
        None, description="Special handling instructions"
    )


class SurgeonPreferenceCardInput(BaseModel):
    """Input for surgeon preference card processing."""

    surgery_id: str = Field(..., description="Surgery identifier")
    surgeon_id: str = Field(..., description="Surgeon identifier")
    procedure_code: str = Field(..., description="Procedure code")
    procedure_description: str = Field(..., description="Procedure description")
    patient_position: str = Field(
        ...,
        description="Patient positioning",
        pattern="^(supine|prone|lateral_left|lateral_right|lithotomy|sitting)$"
    )
    preferred_instruments: List[PreferenceItem] = Field(
        default_factory=list, description="Preferred surgical instruments"
    )
    preferred_sutures: List[PreferenceItem] = Field(
        default_factory=list, description="Preferred sutures"
    )
    preferred_supplies: List[PreferenceItem] = Field(
        default_factory=list, description="Preferred supplies"
    )
    skin_prep: str = Field(..., description="Skin preparation protocol")
    draping_instructions: str = Field(..., description="Draping instructions")
    special_requests: Optional[str] = Field(
        None, description="Special requests or notes"
    )


class SurgeonPreferenceCardOutput(BaseModel):
    """Output from surgeon preference card processing."""

    card_id: str = Field(..., description="Preference card identifier")
    surgery_id: str = Field(..., description="Surgery identifier")
    surgeon_id: str = Field(..., description="Surgeon identifier")
    procedure_code: str = Field(..., description="Procedure code")
    setup_checklist: List[dict] = Field(
        ..., description="Setup checklist with items and status"
    )
    preparation_notes: List[str] = Field(..., description="Preparation notes")
    estimated_setup_time_minutes: int = Field(
        ..., description="Estimated setup time in minutes"
    )
    card_timestamp: str = Field(..., description="Card generation timestamp")


class SurgeonPreferenceCardWorker:
    """Worker for managing surgeon preference cards."""

    def __init__(self, tasy_adapter: Optional[TasySurgicalAdapter] = None) -> None:
        """
        Initialize worker.

        Args:
            tasy_adapter: Optional TASY surgical adapter
        """
        self.tasy_adapter = tasy_adapter or TasySurgicalAdapter()

    @require_tenant
    @track_task_execution(task_type="surgical.preference_card")
    async def execute(self, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute preference card processing.

        Args:
            variables: Process variables containing preference card input

        Returns:
            Dictionary with preference card output

        Raises:
            SurgicalOperationsException: If processing fails
        """
        tenant = get_required_tenant()
        logger.info(
            "Processing surgeon preference card",
            extra={
                "tenant_id": tenant.tenant_id,
                "surgery_id": variables.get("surgery_id"),
            },
        )

        try:
            # Parse and validate input
            input_data = SurgeonPreferenceCardInput(**variables)

            # Generate card ID
            card_id = str(uuid.uuid4())

            # Build setup checklist
            setup_checklist = self._build_setup_checklist(input_data)

            # Generate preparation notes
            preparation_notes = self._generate_preparation_notes(input_data)

            # Calculate estimated setup time
            estimated_setup_time = self._calculate_setup_time(input_data)

            # Create output
            output = SurgeonPreferenceCardOutput(
                card_id=card_id,
                surgery_id=input_data.surgery_id,
                surgeon_id=input_data.surgeon_id,
                procedure_code=input_data.procedure_code,
                setup_checklist=setup_checklist,
                preparation_notes=preparation_notes,
                estimated_setup_time_minutes=estimated_setup_time,
                card_timestamp=datetime.now(timezone.utc).isoformat(),
            )

            logger.info(
                "Surgeon preference card processed successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "card_id": card_id,
                    "surgery_id": input_data.surgery_id,
                    "checklist_items": len(setup_checklist),
                    "estimated_setup_time": estimated_setup_time,
                },
            )

            return output.model_dump()

        except ValueError as e:
            logger.error(
                "Invalid preference card input",
                extra={"tenant_id": tenant.tenant_id, "error": str(e)},
            )
            raise SurgicalOperationsException(
                message=_("Invalid preference card input: {error}").format(error=str(e)),
                details={"validation_error": str(e)},
            ) from e
        except Exception as e:
            logger.error(
                "Failed to process surgeon preference card",
                extra={"tenant_id": tenant.tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise SurgicalOperationsException(
                message=_("Failed to process preference card: {error}").format(
                    error=str(e)
                ),
                details={"error": str(e)},
            ) from e

    def _build_setup_checklist(
        self, input_data: SurgeonPreferenceCardInput
    ) -> List[dict]:
        """
        Build setup checklist from preference items.

        Args:
            input_data: Preference card input

        Returns:
            List of checklist items with status
        """
        checklist = []

        # Add instruments
        for item in input_data.preferred_instruments:
            checklist.append(self._create_checklist_item(item, "instrument"))

        # Add sutures
        for item in input_data.preferred_sutures:
            checklist.append(self._create_checklist_item(item, "suture"))

        # Add supplies
        for item in input_data.preferred_supplies:
            checklist.append(self._create_checklist_item(item, "supply"))

        return checklist

    def _create_checklist_item(
        self, item: PreferenceItem, category: str
    ) -> dict:
        """
        Create checklist item from preference item.

        Args:
            item: Preference item
            category: Item category

        Returns:
            Checklist item dictionary
        """
        checklist_item = {
            "category": category,
            "item": item.item_name,
            "quantity": item.quantity,
            "status": "pending",
        }

        if item.item_code:
            checklist_item["item_code"] = item.item_code

        if item.size:
            checklist_item["size"] = item.size

        if item.special_instructions:
            checklist_item["special_instructions"] = item.special_instructions

        return checklist_item

    def _generate_preparation_notes(
        self, input_data: SurgeonPreferenceCardInput
    ) -> List[str]:
        """
        Generate preparation notes for surgical setup.

        Args:
            input_data: Preference card input

        Returns:
            List of preparation notes
        """
        notes = []

        # Patient positioning
        position_formatted = input_data.patient_position.replace("_", " ").title()
        notes.append(f"Position patient: {position_formatted}")

        # Skin preparation
        notes.append(f"Skin prep: {input_data.skin_prep}")

        # Draping
        notes.append(f"Draping: {input_data.draping_instructions}")

        # Item counts
        instrument_count = len(input_data.preferred_instruments)
        suture_count = len(input_data.preferred_sutures)
        supply_count = len(input_data.preferred_supplies)

        notes.append(
            f"Prepare {instrument_count} instruments, "
            f"{suture_count} sutures, {supply_count} supplies"
        )

        # Special requests
        if input_data.special_requests:
            notes.append(f"Special request: {input_data.special_requests}")

        return notes

    def _calculate_setup_time(self, input_data: SurgeonPreferenceCardInput) -> int:
        """
        Calculate estimated setup time in minutes.

        Args:
            input_data: Preference card input

        Returns:
            Estimated setup time in minutes
        """
        # Base time: 15 minutes
        base_time = 15

        # Add 2 minutes per instrument
        instrument_time = len(input_data.preferred_instruments) * 2

        # Add 1 minute per supply
        supply_time = len(input_data.preferred_supplies) * 1

        total_time = base_time + instrument_time + supply_time

        return total_time
