"""
ConsultarAgendaWorker - Query hospital scheduling system for appointment availability.

Business Rule: RN-SCH-001.md
Regulatory Compliance: LGPD (Privacy in scheduling), Benchmark: Scheduling Integration
Migrated from: com.hospital.revenuecycle.delegates.scheduling.ConsultarAgendaDelegate

This worker checks availability and retrieves appointment schedule information
from the hospital scheduling system. Supports filtering by date range, provider,
and specialty.

Topic: consultar-agenda
BPMN Task: Task_Consultar_Agenda (Consultar Agenda)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog
from pydantic import ValidationError

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.scheduling.scheduling_models import (
    AvailableSlot,
    ConsultarAgendaInput,
    ConsultarAgendaOutput,
)

logger = structlog.get_logger(__name__)


class SchedulingQueryError(Exception):
    """Raised when scheduling query fails."""

    pass


@worker(topic="consultar-agenda", max_jobs=8, lock_duration=30000)
class ConsultarAgendaWorker(BaseWorker):
    """
    Zeebe worker for querying appointment scheduling.

    BPMN Task: Task_Consultar_Agenda
    Topic: consultar-agenda

    This worker queries the scheduling system for:
    - Available appointment slots
    - Provider schedules and availability
    - Room/facility availability
    - Service capacity and constraints
    - Filter by date range, provider, specialty, and time preference

    Input Variables:
        - patientId: Patient identifier (required)
        - serviceCode: Service code for appointment (required)
        - dateRangeStart: Start date in YYYY-MM-DD (optional)
        - dateRangeEnd: End date in YYYY-MM-DD (optional)
        - providerCode: Preferred provider code (optional)
        - specialty: Medical specialty (optional)
        - maxResults: Maximum slots to return (default: 10)
        - preferredTime: MORNING/AFTERNOON/EVENING (optional)

    Output Variables:
        - availableSlots: List of available slots (AvailableSlot[])
        - schedulingAvailable: Whether scheduling is available (boolean)
        - slotCount: Number of available slots (integer)
        - serviceCode: Requested service code
        - patientId: Patient identifier
        - queriedAt: Timestamp of query
    """

    def __init__(
        self,
        settings=None,
        scheduling_service=None,
        **kwargs
    ):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            scheduling_service: Optional scheduling service (for testing)
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._scheduling_service = scheduling_service

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "consultar_agenda"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the scheduling query task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with available slots
        """
        self._logger.info(
            "Processing scheduling query",
            patient_id=variables.get("patientId"),
            service_code=variables.get("serviceCode"),
        )

        try:
            # Parse and validate input
            input_data = ConsultarAgendaInput.model_validate(variables)

            # Validate date range if provided
            if input_data.date_range_start and input_data.date_range_end:
                await self._validate_date_range(
                    input_data.date_range_start,
                    input_data.date_range_end,
                )

            # Query available slots from scheduling system
            available_slots = await self._query_available_slots(input_data)

            # Filter results based on preferences
            filtered_slots = await self._filter_slots(
                available_slots,
                input_data,
            )

            # Limit results
            limited_slots = filtered_slots[: input_data.max_results]

            # Create output
            output = ConsultarAgendaOutput(
                availableSlots=limited_slots,
                schedulingAvailable=len(limited_slots) > 0,
                slotCount=len(limited_slots),
                serviceCode=input_data.service_code,
                patientId=input_data.patient_id,
            )

            # Add tenant_id to output if present
            output_dict = output.model_dump(by_alias=True)
            if input_data.tenant_id:
                output_dict["tenantId"] = input_data.tenant_id

            self._logger.info(
                "Scheduling query completed",
                patient_id=input_data.patient_id,
                service_code=input_data.service_code,
                available_slots=len(limited_slots),
            )

            return WorkerResult.ok(output_dict)

        except ValidationError as e:
            self._logger.error(
                "Scheduling query validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_SCHEDULING_QUERY",
                error_message=f"Validation failed: {e}",
            )

        except SchedulingQueryError as e:
            self._logger.error(
                "Scheduling query error",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code="SCHEDULING_QUERY_ERROR",
                error_message=str(e),
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error querying schedule",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Scheduling query failed: {e}",
                retry=True,
            )

    async def _validate_date_range(
        self,
        start_date: str,
        end_date: str,
    ) -> None:
        """
        Validate date range is valid.

        Args:
            start_date: Start date in YYYY-MM-DD
            end_date: End date in YYYY-MM-DD

        Raises:
            SchedulingQueryError: If date range is invalid
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")

            if start > end:
                raise SchedulingQueryError(
                    f"Start date {start_date} cannot be after end date {end_date}"
                )

            # Check if range is not too far in the future (max 6 months)
            max_date = datetime.utcnow() + timedelta(days=180)
            if end > max_date:
                self._logger.warning(
                    "Date range extends beyond typical scheduling window",
                    end_date=end_date,
                    max_date=max_date.strftime("%Y-%m-%d"),
                )

        except ValueError as e:
            raise SchedulingQueryError(f"Invalid date format: {e}")

    async def _query_available_slots(
        self,
        input_data: ConsultarAgendaInput,
    ) -> list[AvailableSlot]:
        """
        Query available slots from scheduling service.

        Args:
            input_data: Scheduling query input

        Returns:
            List of available slots
        """
        self._logger.debug(
            "Querying scheduling system",
            patient_id=input_data.patient_id,
            service_code=input_data.service_code,
        )

        if self._scheduling_service:
            return await self._scheduling_service.get_available_slots(
                service_code=input_data.service_code,
                provider_code=input_data.provider_code,
                date_range_start=input_data.date_range_start,
                date_range_end=input_data.date_range_end,
            )

        # Fallback: Return mock slots for testing
        return self._generate_mock_slots(input_data)

    def _generate_mock_slots(self, input_data: ConsultarAgendaInput) -> list[AvailableSlot]:
        """
        Generate mock available slots for testing.

        Args:
            input_data: Scheduling query input

        Returns:
            List of mock available slots
        """
        slots = []
        base_date = datetime.utcnow() + timedelta(days=1)

        for i in range(3):
            slot_date = base_date + timedelta(days=i)
            slot = AvailableSlot(
                slotId=f"SLOT-{input_data.patient_id}-{i+1}",
                date=slot_date.strftime("%Y-%m-%d"),
                time="09:00" if i % 2 == 0 else "14:00",
                providerName="Dr. Silva" if i % 2 == 0 else "Dr. Santos",
                providerId=f"PROV-{i+1}",
                specialty=input_data.specialty or "General",
                serviceCode=input_data.service_code,
                estimatedDurationMinutes=45,
                location="Hospital Main Building",
            )
            slots.append(slot)

        return slots

    async def _filter_slots(
        self,
        slots: list[AvailableSlot],
        input_data: ConsultarAgendaInput,
    ) -> list[AvailableSlot]:
        """
        Filter slots based on preferences.

        Args:
            slots: Available slots
            input_data: Query input with filter criteria

        Returns:
            Filtered slots
        """
        filtered = slots

        # Filter by provider if specified
        if input_data.provider_code:
            filtered = [
                s for s in filtered
                if s.provider_id == input_data.provider_code
            ]

        # Filter by specialty if specified
        if input_data.specialty:
            filtered = [
                s for s in filtered
                if s.specialty.lower() == input_data.specialty.lower()
            ]

        # Filter by time preference if specified
        if input_data.preferred_time:
            filtered = self._filter_by_time_preference(
                filtered,
                input_data.preferred_time,
            )

        return filtered

    def _filter_by_time_preference(
        self,
        slots: list[AvailableSlot],
        preferred_time: str,
    ) -> list[AvailableSlot]:
        """
        Filter slots by time preference.

        Args:
            slots: Available slots
            preferred_time: MORNING/AFTERNOON/EVENING

        Returns:
            Slots matching time preference
        """
        filtered = []

        for slot in slots:
            try:
                hour = int(slot.time.split(":")[0])

                if preferred_time.upper() == "MORNING" and 6 <= hour < 12:
                    filtered.append(slot)
                elif preferred_time.upper() == "AFTERNOON" and 12 <= hour < 18:
                    filtered.append(slot)
                elif preferred_time.upper() == "EVENING" and 18 <= hour < 22:
                    filtered.append(slot)

            except (ValueError, IndexError):
                # Skip slots with invalid time format
                continue

        return filtered
