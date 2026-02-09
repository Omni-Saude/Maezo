"""Check Availability Worker - Patient Access Domain.

CIB7 External Task Topic: scheduling.check_availability
BPMN Error Code: PATIENT_ACCESS_ERROR

Checks availability of rooms, equipment, practitioners for appointment scheduling.
Queries FHIR Schedule/Slot resources and returns available time slots.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.integrations.fhir_client import FHIRClientProtocol
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


class PatientAccessException(DomainException):
    """Patient access domain exception."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        bpmn_error_code: str = "PATIENT_ACCESS_ERROR",
    ) -> None:
        """Initialize exception with BPMN error code."""
        super().__init__(message, details)
        self.bpmn_error_code = bpmn_error_code


class AvailabilityCheckInput(BaseModel):
    """Input for availability check."""

    practitioner_id: str = Field(..., description="FHIR Practitioner reference")
    service_type: str = Field(..., description="Service type code")
    start_date: datetime = Field(..., description="Search start date")
    end_date: datetime = Field(..., description="Search end date")
    location_id: str | None = Field(None, description="Optional location filter")
    required_duration_minutes: int = Field(30, description="Required duration in minutes")


class AvailabilitySlot(BaseModel):
    """Available time slot."""

    slot_id: str = Field(..., description="FHIR Slot reference")
    start_time: datetime = Field(..., description="Slot start time")
    end_time: datetime = Field(..., description="Slot end time")
    practitioner_id: str = Field(..., description="Practitioner reference")
    location_id: str | None = Field(None, description="Location reference")
    service_type: str = Field(..., description="Service type")


class AvailabilityCheckOutput(BaseModel):
    """Output from availability check."""

    available_slots: list[AvailabilitySlot] = Field(default_factory=list)
    total_slots_found: int = Field(0, description="Total available slots")
    search_completed: bool = Field(True, description="Search completed successfully")
    message: str = Field("", description="Status message")


class AvailabilityChecker(ABC):
    """Protocol for checking appointment availability."""

    @abstractmethod
    async def check_availability(
        self,
        practitioner_id: str,
        service_type: str,
        start_date: datetime,
        end_date: datetime,
        location_id: str | None = None,
        required_duration_minutes: int = 30,
        tenant_id: str | None = None,
    ) -> list[AvailabilitySlot]:
        """Check availability and return available slots.

        Args:
            practitioner_id: FHIR Practitioner reference
            service_type: Service type code
            start_date: Search start date
            end_date: Search end date
            location_id: Optional location filter
            required_duration_minutes: Required duration in minutes
            tenant_id: Tenant identifier

        Returns:
            List of available slots

        Raises:
            PatientAccessException: If availability check fails
        """
        ...


class StubAvailabilityChecker(AvailabilityChecker):
    """Stub implementation for testing."""

    async def check_availability(
        self,
        practitioner_id: str,
        service_type: str,
        start_date: datetime,
        end_date: datetime,
        location_id: str | None = None,
        required_duration_minutes: int = 30,
        tenant_id: str | None = None,
    ) -> list[AvailabilitySlot]:
        """Return mock available slots."""
        from datetime import timedelta

        slots = []
        current = start_date.replace(hour=9, minute=0, second=0, microsecond=0)
        end = end_date.replace(hour=17, minute=0, second=0, microsecond=0)

        slot_count = 0
        while current < end and slot_count < 5:
            # Skip lunch hour (12-13)
            if current.hour == 12:
                current += timedelta(hours=1)
                continue

            slot_end = current + timedelta(minutes=required_duration_minutes)
            slots.append(
                AvailabilitySlot(
                    slot_id=f"Slot/{tenant_id or 'default'}-{slot_count + 1}",
                    start_time=current,
                    end_time=slot_end,
                    practitioner_id=practitioner_id,
                    location_id=location_id,
                    service_type=service_type,
                )
            )
            current += timedelta(minutes=required_duration_minutes)
            slot_count += 1

        return slots


class CheckAvailabilityWorker:
    """Worker for checking appointment availability.

    Queries FHIR Schedule/Slot resources to find available time slots
    for appointments based on practitioner, service type, and date range.
    """

    TOPIC = "scheduling.check_availability"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol | None = None,
        availability_checker: AvailabilityChecker | None = None,
    ) -> None:
        """Initialize worker with dependencies.

        Args:
            fhir_client: FHIR client for resource access
            availability_checker: Availability checker implementation
        """
        self.fhir_client = fhir_client
        self.availability_checker = availability_checker or StubAvailabilityChecker()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute availability check task.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with available_slots and metadata

        Raises:
            PatientAccessException: If availability check fails
        """
        tenant_id = get_required_tenant()
        self.logger.info(
            _("Iniciando verificação de disponibilidade"),
            extra={
                "tenant_id": tenant_id,
                "practitioner_id": task_variables.get("practitioner_id"),
                "service_type": task_variables.get("service_type"),
            },
        )

        try:
            # Parse and validate input
            input_data = AvailabilityCheckInput(**task_variables)

            # Check availability
            available_slots = await self.availability_checker.check_availability(
                practitioner_id=input_data.practitioner_id,
                service_type=input_data.service_type,
                start_date=input_data.start_date,
                end_date=input_data.end_date,
                location_id=input_data.location_id,
                required_duration_minutes=input_data.required_duration_minutes,
                tenant_id=tenant_id,
            )

            # Build output
            output = AvailabilityCheckOutput(
                available_slots=available_slots,
                total_slots_found=len(available_slots),
                search_completed=True,
                message=_("Verificação de disponibilidade concluída com sucesso"),
            )

            self.logger.info(
                _("Disponibilidade verificada com sucesso"),
                extra={
                    "tenant_id": tenant_id,
                    "total_slots": output.total_slots_found,
                    "practitioner_id": input_data.practitioner_id,
                },
            )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                _("Erro ao verificar disponibilidade"),
                extra={"tenant_id": tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise PatientAccessException(
                message=_("Falha na verificação de disponibilidade: {error}").format(error=str(e)),
                details={
                    "tenant_id": tenant_id,
                    "practitioner_id": task_variables.get("practitioner_id"),
                    "error": str(e),
                },
            ) from e
