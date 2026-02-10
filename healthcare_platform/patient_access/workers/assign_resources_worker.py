"""Assign Resources Worker - Patient Access Domain.

CIB7 External Task Topic: scheduling.assign_resources
BPMN Error Code: PATIENT_ACCESS_ERROR

Allocates resources (rooms, equipment, staff) for appointments.
Creates FHIR Slot reservations and handles resource conflicts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution


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


class ResourceRequirement(BaseModel):
    """Resource requirement specification."""

    resource_type: str = Field(..., description="Type: room, equipment, staff")
    resource_code: str = Field(..., description="Specific resource code")
    quantity: int = Field(1, description="Required quantity")
    required: bool = Field(True, description="Is resource mandatory")


class AssignedResource(BaseModel):
    """Assigned resource details."""

    resource_reference: str = Field(..., description="FHIR resource reference")
    resource_type: str = Field(..., description="Type: Location, Device, Practitioner")
    resource_code: str = Field(..., description="Resource code")
    slot_reference: str = Field(..., description="Associated Slot reference")
    status: str = Field("busy", description="Reservation status")


class AssignResourcesInput(BaseModel):
    """Input for resource assignment."""

    appointment_reference: str = Field(..., description="FHIR Appointment reference")
    start_datetime: datetime = Field(..., description="Start time for resource allocation")
    end_datetime: datetime = Field(..., description="End time for resource allocation")
    service_type: str = Field(..., description="Service type code")
    resource_requirements: list[ResourceRequirement] = Field(
        default_factory=list, description="Required resources"
    )
    location_id: str | None = Field(None, description="Preferred location")


class AssignResourcesOutput(BaseModel):
    """Output from resource assignment."""

    assigned_resources: list[AssignedResource] = Field(default_factory=list)
    all_resources_assigned: bool = Field(False, description="All requirements met")
    missing_resources: list[str] = Field(default_factory=list, description="Unmet requirements")
    conflicts: list[str] = Field(default_factory=list, description="Resource conflicts detected")
    message: str = Field("", description="Status message")


class ResourceAssigner(ABC):
    """Protocol for assigning resources."""

    @abstractmethod
    async def assign_resources(
        self,
        appointment_reference: str,
        start_datetime: datetime,
        end_datetime: datetime,
        service_type: str,
        resource_requirements: list[ResourceRequirement],
        location_id: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[list[AssignedResource], list[str], list[str]]:
        """Assign resources for appointment.

        Args:
            appointment_reference: FHIR Appointment reference
            start_datetime: Start time for allocation
            end_datetime: End time for allocation
            service_type: Service type code
            resource_requirements: Required resources
            location_id: Preferred location
            tenant_id: Tenant identifier

        Returns:
            Tuple of (assigned_resources, missing_resources, conflicts)

        Raises:
            PatientAccessException: If assignment fails
        """
        ...


class StubResourceAssigner(ResourceAssigner):
    """Stub implementation for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()
        # DMN integration point: auth_timing_004
        # Inputs: {'resource_type': 'room', 'appointment_id': appointment_id}
        # Call: self.dmn_service.evaluate(tenant_id=..., category='authorization', table_name='auth_timing_004', inputs={...})


    async def assign_resources(
        self,
        appointment_reference: str,
        start_datetime: datetime,
        end_datetime: datetime,
        service_type: str,
        resource_requirements: list[ResourceRequirement],
        location_id: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[list[AssignedResource], list[str], list[str]]:
        """Assign mock resources."""
        import uuid

        assigned: list[AssignedResource] = []
        missing: list[str] = []
        conflicts: list[str] = []

        # Default resources for common service types
        default_resources = {
            "consulta": [
                ResourceRequirement(resource_type="room", resource_code="exam_room", quantity=1),
            ],
            "exame_simples": [
                ResourceRequirement(resource_type="room", resource_code="exam_room", quantity=1),
                ResourceRequirement(resource_type="equipment", resource_code="ecg_machine", quantity=1),
            ],
            "cirurgia": [
                ResourceRequirement(resource_type="room", resource_code="operating_room", quantity=1),
                ResourceRequirement(resource_type="equipment", resource_code="surgical_set", quantity=1),
                ResourceRequirement(
                    resource_type="staff", resource_code="surgical_nurse", quantity=2
                ),
            ],
            "procedimento": [
                ResourceRequirement(resource_type="room", resource_code="procedure_room", quantity=1),
                ResourceRequirement(
                    resource_type="equipment", resource_code="procedure_kit", quantity=1
                ),
            ],
        }

        # Use provided requirements or defaults
        requirements = resource_requirements or default_resources.get(service_type, [])

        # Assign resources (stub assumes all available)
        for req in requirements:
            resource_id = str(uuid.uuid4())
            slot_id = str(uuid.uuid4())

            # Map resource type to FHIR type
            fhir_type_map = {
                "room": "Location",
                "equipment": "Device",
                "staff": "Practitioner",
            }
            fhir_type = fhir_type_map.get(req.resource_type, "Resource")

            assigned.append(
                AssignedResource(
                    resource_reference=f"{fhir_type}/{resource_id}",
                    resource_type=fhir_type,
                    resource_code=req.resource_code,
                    slot_reference=f"Slot/{slot_id}",
                    status="busy",
                )
            )

        # In real implementation:
        # 1. Query FHIR for available resources matching requirements
        # 2. Check for conflicts in Schedule/Slot resources
        # 3. Reserve slots by updating status to "busy"
        # 4. Link slots to Appointment
        # 5. Handle partial allocations and conflicts

        return assigned, missing, conflicts


class AssignResourcesWorker:
    """Worker for assigning resources to appointments.

    Allocates rooms, equipment, and staff for appointments by creating
    FHIR Slot reservations and managing resource availability.
    """

    TOPIC = "scheduling.assign_resources"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol | None = None,
        resource_assigner: ResourceAssigner | None = None,
    ) -> None:
        """Initialize worker with dependencies.

        Args:
            fhir_client: FHIR client for resource access
            resource_assigner: Resource assigner implementation
        """
        self.fhir_client = fhir_client
        self.resource_assigner = resource_assigner or StubResourceAssigner()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute resource assignment task.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with assigned resources and status

        Raises:
            PatientAccessException: If resource assignment fails
        """
        tenant_id = get_required_tenant()
        self.logger.info(
            _("Iniciando alocação de recursos"),
            extra={
                "tenant_id": tenant_id,
                "appointment_reference": task_variables.get("appointment_reference"),
                "service_type": task_variables.get("service_type"),
            },
        )

        try:
            # Parse and validate input
            input_data = AssignResourcesInput(**task_variables)

            # Assign resources
            (
                assigned_resources,
                missing_resources,
                conflicts,
            ) = await self.resource_assigner.assign_resources(
                appointment_reference=input_data.appointment_reference,
                start_datetime=input_data.start_datetime,
                end_datetime=input_data.end_datetime,
                service_type=input_data.service_type,
                resource_requirements=input_data.resource_requirements,
                location_id=input_data.location_id,
                tenant_id=tenant_id,
            )

            # Determine overall success
            all_assigned = len(missing_resources) == 0 and len(conflicts) == 0

            # Build message
            if all_assigned:
                message = _("Todos os recursos foram alocados com sucesso")
            elif missing_resources:
                message = _(
                    "Recursos alocados parcialmente. {count} recursos não disponíveis"
                ).format(count=len(missing_resources))
            else:
                message = _("Conflitos detectados durante alocação de recursos")

            # Build output
            output = AssignResourcesOutput(
                assigned_resources=assigned_resources,
                all_resources_assigned=all_assigned,
                missing_resources=missing_resources,
                conflicts=conflicts,
                message=message,
            )

            self.logger.info(
                _("Alocação de recursos concluída"),
                extra={
                    "tenant_id": tenant_id,
                    "appointment_reference": input_data.appointment_reference,
                    "assigned_count": len(assigned_resources),
                    "missing_count": len(missing_resources),
                    "conflicts_count": len(conflicts),
                },
            )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                _("Erro ao alocar recursos"),
                extra={
                    "tenant_id": tenant_id,
                    "appointment_reference": task_variables.get("appointment_reference"),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                message=_("Falha na alocação de recursos: {error}").format(error=str(e)),
                details={
                    "tenant_id": tenant_id,
                    "appointment_reference": task_variables.get("appointment_reference"),
                    "error": str(e),
                },
            ) from e
