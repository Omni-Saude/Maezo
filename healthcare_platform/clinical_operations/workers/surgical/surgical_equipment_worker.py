"""
Surgical Equipment Worker - Equipment availability and sterilization check.

CIB7 External Task Topic: surgical.equipment_check
BPMN Error Code: SURGICAL_OPERATIONS_ERROR

Verifies surgical equipment availability and sterilization status.
Integrates with WHO Safe Surgery Checklist Time Out phase.
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

logger = get_logger(__name__, worker="surgical.equipment_check")


TOPIC = "surgical.equipment_check"


class SurgicalOperationsException(DomainException):
    """Exception for surgical operations errors."""

    bpmn_error_code = "SURGICAL_OPERATIONS_ERROR"


class EquipmentItem(BaseModel):
    """Equipment item for surgical procedure."""

    equipment_id: str = Field(..., description="Unique identifier for the equipment")
    name: str = Field(..., description="Name of the equipment")
    category: str = Field(
        ...,
        description="Equipment category: instrument, implant, disposable, device"
    )
    sterilization_status: str = Field(
        ...,
        description="Sterilization status: sterile, pending, expired, not_required"
    )
    sterilization_date: Optional[datetime] = Field(
        None, description="Date when equipment was sterilized"
    )
    expiration_date: Optional[datetime] = Field(
        None, description="Expiration date for sterilization"
    )
    available: bool = Field(..., description="Whether equipment is available")


class SurgicalEquipmentInput(BaseModel):
    """Input for surgical equipment check."""

    surgery_id: str = Field(..., description="Unique identifier for the surgery")
    operating_room_id: str = Field(..., description="Operating room identifier")
    procedure_code: str = Field(..., description="Surgical procedure code")
    required_equipment: List[EquipmentItem] = Field(
        ..., description="List of required equipment items"
    )
    who_checklist_phase: str = Field(
        default="time_out",
        description="WHO Safe Surgery Checklist phase"
    )
    checked_by_practitioner_id: str = Field(
        ..., description="ID of practitioner performing the check"
    )


class SurgicalEquipmentOutput(BaseModel):
    """Output from surgical equipment check."""

    check_id: str = Field(..., description="Unique identifier for this check")
    surgery_id: str = Field(..., description="Surgery identifier")
    all_equipment_available: bool = Field(
        ..., description="Whether all equipment is available"
    )
    all_sterilization_valid: bool = Field(
        ..., description="Whether all sterilization is valid"
    )
    equipment_ready: bool = Field(
        ...,
        description="Overall readiness: both availability and sterilization valid"
    )
    missing_equipment: List[str] = Field(
        default_factory=list, description="List of missing equipment names"
    )
    expired_sterilization: List[str] = Field(
        default_factory=list, description="List of equipment with expired sterilization"
    )
    check_timestamp: datetime = Field(
        ..., description="Timestamp when check was performed"
    )
    who_timeout_equipment_confirmed: bool = Field(
        ..., description="WHO Time Out equipment confirmation status"
    )


class SurgicalEquipmentWorker:
    """Worker for checking surgical equipment availability and sterilization."""

    def __init__(self, tasy_adapter: Optional[TasySurgicalAdapter] = None):
        """
        Initialize the surgical equipment worker.

        Args:
            tasy_adapter: Optional TASY surgical adapter for integration
        """
        self.tasy_adapter = tasy_adapter or TasySurgicalAdapter()
        self.topic = TOPIC

    @require_tenant
    @track_task_execution(TOPIC)
    async def execute(self, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute surgical equipment availability and sterilization check.

        Args:
            variables: Task variables containing equipment check input

        Returns:
            Dictionary containing equipment check results

        Raises:
            SurgicalOperationsException: If required fields are missing or validation fails
        """
        tenant_id = get_required_tenant()
        logger.info(
            "Starting surgical equipment check",
            tenant_id=tenant_id,
            surgery_id=variables.get("surgery_id"),
        )

        try:
            # Parse input
            input_data = SurgicalEquipmentInput(**variables)
        except Exception as e:
            logger.error(
                "Failed to parse surgical equipment input",
                error=str(e),
                tenant_id=tenant_id,
            )
            raise SurgicalOperationsException(
                message=_("Invalid surgical equipment input: {error}").format(error=str(e)),
                details={"error": str(e), "variables": variables},
            ) from e

        # Generate check ID
        check_id = str(uuid.uuid4())
        check_timestamp = datetime.now(timezone.utc)

        # Initialize tracking lists
        missing_equipment: List[str] = []
        expired_sterilization: List[str] = []

        # Check each equipment item
        all_equipment_available = True
        all_sterilization_valid = True

        for equipment in input_data.required_equipment:
            # Check availability
            if not equipment.available:
                all_equipment_available = False
                missing_equipment.append(equipment.name)
                logger.warning(
                    "Equipment not available",
                    equipment_id=equipment.equipment_id,
                    equipment_name=equipment.name,
                    surgery_id=input_data.surgery_id,
                    tenant_id=tenant_id,
                )

            # Check sterilization status
            if equipment.sterilization_status == "not_required":
                # No sterilization check needed for this equipment
                logger.debug(
                    "Equipment does not require sterilization",
                    equipment_id=equipment.equipment_id,
                    equipment_name=equipment.name,
                )
            elif equipment.sterilization_status == "sterile":
                # Check expiration if provided
                if equipment.expiration_date:
                    if equipment.expiration_date < check_timestamp:
                        all_sterilization_valid = False
                        expired_sterilization.append(equipment.name)
                        logger.warning(
                            "Equipment sterilization expired",
                            equipment_id=equipment.equipment_id,
                            equipment_name=equipment.name,
                            expiration_date=equipment.expiration_date.isoformat(),
                            surgery_id=input_data.surgery_id,
                            tenant_id=tenant_id,
                        )
            elif equipment.sterilization_status in ["pending", "expired"]:
                all_sterilization_valid = False
                if equipment.sterilization_status == "expired":
                    expired_sterilization.append(equipment.name)
                logger.warning(
                    "Equipment sterilization not valid",
                    equipment_id=equipment.equipment_id,
                    equipment_name=equipment.name,
                    sterilization_status=equipment.sterilization_status,
                    surgery_id=input_data.surgery_id,
                    tenant_id=tenant_id,
                )
            else:
                # Unknown sterilization status
                all_sterilization_valid = False
                logger.warning(
                    "Unknown sterilization status",
                    equipment_id=equipment.equipment_id,
                    equipment_name=equipment.name,
                    sterilization_status=equipment.sterilization_status,
                    surgery_id=input_data.surgery_id,
                    tenant_id=tenant_id,
                )

        # Overall equipment readiness
        equipment_ready = all_equipment_available and all_sterilization_valid

        # WHO checklist confirmation (Time Out phase)
        who_timeout_equipment_confirmed = (
            equipment_ready and input_data.who_checklist_phase == "time_out"
        )

        # Create output
        output = SurgicalEquipmentOutput(
            check_id=check_id,
            surgery_id=input_data.surgery_id,
            all_equipment_available=all_equipment_available,
            all_sterilization_valid=all_sterilization_valid,
            equipment_ready=equipment_ready,
            missing_equipment=missing_equipment,
            expired_sterilization=expired_sterilization,
            check_timestamp=check_timestamp,
            who_timeout_equipment_confirmed=who_timeout_equipment_confirmed,
        )

        logger.info(
            "Surgical equipment check completed",
            check_id=check_id,
            surgery_id=input_data.surgery_id,
            equipment_ready=equipment_ready,
            all_equipment_available=all_equipment_available,
            all_sterilization_valid=all_sterilization_valid,
            missing_count=len(missing_equipment),
            expired_count=len(expired_sterilization),
            tenant_id=tenant_id,
        )

        return output.model_dump(mode="json")
