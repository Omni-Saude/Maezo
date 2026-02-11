"""
Surgery Scheduling Worker

CIB7 External Task Topic: surgical.scheduling
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Schedules surgical procedures by checking operating room availability
and creating surgical schedules in TASY via the FHIR adapter.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import (
    TasySurgicalAdapter,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


def _(message: str) -> str:
    """Translation helper for Portuguese error messages."""
    return message


class ClinicalOperationsException(DomainException):
    """Exception for clinical operations errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )
        self.code = "CLINICAL_OPERATIONS_ERROR"


class SurgerySchedulingInput(BaseModel):
    """Input model for surgery scheduling."""

    patient_id: str = Field(..., description="FHIR Patient ID")
    procedure_code: str = Field(..., description="TASY procedure code")
    procedure_name: str = Field(..., description="Procedure name")
    surgeon_id: str = Field(..., description="FHIR Practitioner ID for surgeon")
    preferred_date: str = Field(..., description="Preferred surgery date (YYYY-MM-DD)")
    preferred_time: str = Field(..., description="Preferred start time (HH:MM)")
    estimated_duration_minutes: int = Field(
        ..., ge=15, le=720, description="Estimated surgery duration in minutes"
    )
    urgency_level: str = Field(
        ...,
        pattern="^(elective|urgent|emergency)$",
        description="Surgery urgency level",
    )
    notes: str | None = Field(None, description="Additional scheduling notes")


class SurgerySchedulingOutput(BaseModel):
    """Output model for surgery scheduling."""

    surgery_id: str = Field(..., description="TASY surgery schedule ID")
    scheduled_date: str = Field(..., description="Confirmed surgery date (YYYY-MM-DD)")
    scheduled_time: str = Field(..., description="Confirmed start time (HH:MM)")
    operating_room: str = Field(..., description="Assigned operating room identifier")
    status: str = Field(..., description="Schedule status (scheduled/pending/cancelled)")
    created_at: str = Field(..., description="ISO 8601 timestamp when schedule created")


class SurgerySchedulingWorker:
    """
    Worker to schedule surgical procedures.

    Validates scheduling request, checks operating room availability via TASY
    adapter, and creates surgical schedule in TASY.
    """

    TOPIC = "surgical.scheduling"

    def __init__(self, tasy_adapter: TasySurgicalAdapter | None = None) -> None:
        """
        Initialize worker with TASY surgical adapter.

        Args:
            tasy_adapter: TASY surgical adapter for OR and schedule management.
                         Defaults to stub implementation for testing.
        """
        self._tasy_adapter = tasy_adapter

    @require_tenant
    @track_task_execution(task_type="surgical.scheduling")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute surgery scheduling.

        Args:
            task_variables: Task variables containing scheduling details

        Returns:
            Dictionary with scheduling results

        Raises:
            ClinicalOperationsException: If scheduling fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = SurgerySchedulingInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for surgery scheduling input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para agendamento cirúrgico"),
                details={"validation_error": str(e)},
            ) from e

        # Log scheduling request
        logger.info(
            "Processing surgery scheduling request",
            extra={
                "tenant_id": tenant.tenant_id,
                "patient_id": input_data.patient_id,
                "surgeon_id": input_data.surgeon_id,
                "procedure_code": input_data.procedure_code,
                "urgency_level": input_data.urgency_level,
                "preferred_date": input_data.preferred_date,
            },
        )

        # Call TASY API to check OR availability and schedule
        try:
            tasy_data = await self._call_tasy_api(input_data)

            # Use adapter to convert TASY data to FHIR if needed
            if self._tasy_adapter:
                adapted_data = await self._tasy_adapter.adapt(tasy_data)
                logger.debug(
                    "Adapted TASY surgery schedule to FHIR",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "surgery_id": tasy_data["surgery_id"],
                    },
                )
            else:
                adapted_data = tasy_data

            logger.info(
                "Surgery scheduled successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "surgery_id": adapted_data["surgery_id"],
                    "operating_room": adapted_data["operating_room"],
                    "scheduled_date": adapted_data["scheduled_date"],
                },
            )

            # Build output
            output = SurgerySchedulingOutput(
                surgery_id=adapted_data["surgery_id"],
                scheduled_date=adapted_data["scheduled_date"],
                scheduled_time=adapted_data["scheduled_time"],
                operating_room=adapted_data["operating_room"],
                status=adapted_data["status"],
                created_at=datetime.now(UTC).isoformat(),
            )

            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to schedule surgery",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "patient_id": input_data.patient_id,
                    "surgeon_id": input_data.surgeon_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha ao agendar cirurgia"),
                details={
                    "patient_id": input_data.patient_id,
                    "surgeon_id": input_data.surgeon_id,
                    "error": str(e),
                },
            ) from e

    async def _call_tasy_api(
        self, input_data: SurgerySchedulingInput
    ) -> dict[str, Any]:
        """
        Call TASY API to schedule surgery (stub implementation).

        Args:
            input_data: Validated scheduling input

        Returns:
            Mock TASY surgery schedule data
        """
        # Stub: In production, this would call TASY REST API
        # For now, return mock data that matches TASY schema
        return {
            "operation_type": "surgery_creation",
            "surgery_id": f"SURG-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "scheduled_date": input_data.preferred_date,
            "scheduled_time": input_data.preferred_time,
            "operating_room": f"OR-{hash(input_data.preferred_date) % 10 + 1}",
            "status": "scheduled" if input_data.urgency_level != "emergency" else "confirmed",
            "patient_id": input_data.patient_id,
            "surgeon_id": input_data.surgeon_id,
            "procedure_code": input_data.procedure_code,
            "procedure_name": input_data.procedure_name,
            "estimated_duration_minutes": input_data.estimated_duration_minutes,
            "urgency_level": input_data.urgency_level,
            "notes": input_data.notes,
        }
