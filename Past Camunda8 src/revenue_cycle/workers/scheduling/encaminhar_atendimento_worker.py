"""
EncaminharAtendimentoWorker - Route patients to scheduled services with guidance.

Business Rule: RN-SCH-003.md
Regulatory Compliance: LGPD (Privacy in service routing), Benchmark: Patient Flow Management
Migrated from: com.hospital.revenuecycle.delegates.scheduling.EncaminharAtendimentoDelegate

This worker routes and directs patients to their scheduled services including
room assignments, provider routing, wayfinding instructions, and check-in guidance.

Topic: encaminhar-atendimento
BPMN Task: Task_Encaminhar_Atendimento (Encaminhar Atendimento)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog
from pydantic import ValidationError

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.scheduling.scheduling_models import (
    EncaminharAtendimentoInput,
    EncaminharAtendimentoOutput,
    RouteInstruction,
)

logger = structlog.get_logger(__name__)


class ServiceRoutingError(Exception):
    """Raised when service routing fails."""

    pass


@worker(topic="encaminhar-atendimento", max_jobs=8, lock_duration=30000)
class EncaminharAtendimentoWorker(BaseWorker):
    """
    Zeebe worker for directing patient to service.

    BPMN Task: Task_Encaminhar_Atendimento
    Topic: encaminhar-atendimento

    This worker:
    - Assigns service room or facility location
    - Routes patient to appropriate provider
    - Generates detailed navigation instructions
    - Calculates estimated wait times
    - Generates check-in instructions
    - Tracks patient flow through service

    Input Variables:
        - patientId: Patient identifier (required)
        - appointmentId: Appointment identifier (required)
        - serviceCode: Service code (required)
        - providerId: Provider identifier (required)
        - providerName: Provider name (optional)
        - appointmentDate: Date in YYYY-MM-DD (optional)
        - appointmentTime: Time in HH:MM (optional)
        - patientName: Patient name (optional)
        - location: Facility location (optional)
        - checkInRequired: Whether check-in is required (default: true)
        - estimatedWaitTime: Pre-calculated wait time (optional, in minutes)

    Output Variables:
        - routeId: Unique routing identifier
        - assignedRoom: Assigned service room/location
        - instructions: List of step-by-step instructions (RouteInstruction[])
        - estimatedWaitTime: Estimated wait time in minutes
        - patientId: Patient identifier
        - appointmentId: Appointment identifier
        - providerId: Provider identifier
        - providerName: Provider name
        - checkInInstructions: Specific check-in instructions
        - contactPhone: Provider/location contact phone
        - routedAt: Timestamp of routing
        - status: Routing status (ROUTED)
    """

    def __init__(
        self,
        settings=None,
        wayfinding_service=None,
        location_service=None,
        notification_service=None,
        **kwargs
    ):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            wayfinding_service: Optional wayfinding service (for testing)
            location_service: Optional location service (for testing)
            notification_service: Optional notification service (for testing)
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._wayfinding_service = wayfinding_service
        self._location_service = location_service
        self._notification_service = notification_service
        self._routed_patients: dict[str, EncaminharAtendimentoOutput] = {}

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "encaminhar_atendimento"

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """Extract appointment ID for idempotency key."""
        appointment_id = variables.get("appointmentId", "")
        patient_id = variables.get("patientId", "")
        return f"{patient_id}:{appointment_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the service routing task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with routing details
        """
        self._logger.info(
            "Processing service routing",
            patient_id=variables.get("patientId"),
            appointment_id=variables.get("appointmentId"),
        )

        try:
            # Parse and validate input
            input_data = EncaminharAtendimentoInput.model_validate(variables)

            # Assign service room
            assigned_room = await self._assign_room(input_data)

            # Generate route ID
            route_id = self._generate_route_id(input_data.appointment_id)

            # Generate detailed instructions
            instructions = await self._generate_instructions(
                input_data=input_data,
                assigned_room=assigned_room,
            )

            # Determine estimated wait time
            estimated_wait_time = input_data.estimated_wait_time or 15

            # Generate check-in instructions
            check_in_instructions = self._generate_check_in_instructions(
                assigned_room=assigned_room,
                check_in_required=input_data.check_in_required,
            )

            # Get contact phone
            contact_phone = await self._get_contact_phone(input_data)

            # Notify patient of routing
            await self._send_routing_notification(
                input_data=input_data,
                assigned_room=assigned_room,
            )

            # Create output
            output = EncaminharAtendimentoOutput(
                routeId=route_id,
                assignedRoom=assigned_room,
                instructions=instructions,
                estimatedWaitTime=estimated_wait_time,
                patientId=input_data.patient_id,
                appointmentId=input_data.appointment_id,
                providerId=input_data.provider_id,
                providerName=input_data.provider_name or "Provider",
                specialty=input_data.specialty or "General",
                location=input_data.location or "Hospital Main Building",
                checkInInstructions=check_in_instructions,
                contactPhone=contact_phone,
            )

            # Store for idempotency
            self._routed_patients[route_id] = output

            # Add tenant_id to output if present
            output_dict = output.model_dump(by_alias=True)
            if input_data.tenant_id:
                output_dict["tenantId"] = input_data.tenant_id

            self._logger.info(
                "Service routing completed",
                patient_id=input_data.patient_id,
                route_id=route_id,
                assigned_room=assigned_room,
            )

            return WorkerResult.ok(output_dict)

        except ValidationError as e:
            self._logger.error(
                "Service routing validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_ROUTING_DATA",
                error_message=f"Validation failed: {e}",
            )

        except ServiceRoutingError as e:
            self._logger.error(
                "Service routing error",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code="SERVICE_ROUTING_ERROR",
                error_message=str(e),
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error routing service",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Service routing failed: {e}",
                retry=True,
            )

    async def _assign_room(
        self,
        input_data: EncaminharAtendimentoInput,
    ) -> str:
        """
        Assign a room or facility location for the service.

        Args:
            input_data: Routing input data

        Returns:
            Assigned room identifier
        """
        self._logger.debug(
            "Assigning room",
            patient_id=input_data.patient_id,
            specialty=input_data.specialty,
        )

        if self._location_service:
            room = await self._location_service.assign_room(
                specialty=input_data.specialty,
                service_code=input_data.service_code,
            )
            return room

        # Fallback: Generate deterministic room assignment
        room_floor = (hash(input_data.patient_id) % 5) + 1
        room_number = (hash(input_data.appointment_id) % 20) + 1
        return f"Room {room_floor}-{room_number:02d}"

    def _generate_route_id(self, appointment_id: str) -> str:
        """
        Generate a unique route ID.

        Args:
            appointment_id: Appointment ID

        Returns:
            Route ID in format ROUTE-{appointment_id}-{random}
        """
        random_suffix = uuid4().hex[:6].upper()
        return f"ROUTE-{appointment_id}-{random_suffix}"

    async def _generate_instructions(
        self,
        input_data: EncaminharAtendimentoInput,
        assigned_room: str,
    ) -> list[RouteInstruction]:
        """
        Generate step-by-step routing instructions.

        Args:
            input_data: Routing input data
            assigned_room: Assigned room location

        Returns:
            List of routing instructions
        """
        instructions = [
            RouteInstruction(
                stepNumber=1,
                instruction="Report to reception desk",
                location="Main Entrance Reception",
                durationMinutes=5,
            ),
            RouteInstruction(
                stepNumber=2,
                instruction=f"Proceed to {assigned_room}",
                location=assigned_room,
                durationMinutes=3,
            ),
            RouteInstruction(
                stepNumber=3,
                instruction=f"Check in at the kiosk",
                location=assigned_room,
                durationMinutes=2,
            ),
            RouteInstruction(
                stepNumber=4,
                instruction=f"Wait for {input_data.provider_name or 'your provider'}",
                location=assigned_room,
                durationMinutes=input_data.estimated_wait_time or 15,
            ),
        ]

        return instructions

    def _generate_check_in_instructions(
        self,
        assigned_room: str,
        check_in_required: bool,
    ) -> str:
        """
        Generate check-in instructions for the patient.

        Args:
            assigned_room: Assigned room location
            check_in_required: Whether check-in is required

        Returns:
            Check-in instructions string
        """
        if not check_in_required:
            return "No check-in required. Proceed directly to your appointment."

        return (
            f"Please check in at the kiosk in {assigned_room} upon arrival. "
            "Have your insurance card and appointment confirmation ready. "
            "You will receive a notification when your provider is ready."
        )

    async def _get_contact_phone(
        self,
        input_data: EncaminharAtendimentoInput,
    ) -> str:
        """
        Get contact phone for location or provider.

        Args:
            input_data: Routing input data

        Returns:
            Contact phone number
        """
        if self._location_service:
            phone = await self._location_service.get_location_phone(
                input_data.location or "Main"
            )
            return phone or ""

        return ""

    async def _send_routing_notification(
        self,
        input_data: EncaminharAtendimentoInput,
        assigned_room: str,
    ) -> None:
        """
        Send routing notification to patient.

        Args:
            input_data: Routing input data
            assigned_room: Assigned room
        """
        self._logger.info(
            "Sending routing notification",
            patient_id=input_data.patient_id,
            appointment_id=input_data.appointment_id,
        )

        if self._notification_service:
            await self._notification_service.send_routing_notification(
                patient_id=input_data.patient_id,
                appointment_id=input_data.appointment_id,
                assigned_room=assigned_room,
                provider_name=input_data.provider_name or "your provider",
            )
