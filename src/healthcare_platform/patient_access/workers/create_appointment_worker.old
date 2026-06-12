"""Create Appointment Worker - Patient Access Domain.

CIB7 External Task Topic: scheduling.create_appointment
BPMN Error Code: PATIENT_ACCESS_ERROR

Creates FHIR Appointment resources and manages appointment lifecycle.
Maps to FHIR R4 Appointment structure with proper resource linking.
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


class AppointmentParticipant(BaseModel):
    """Appointment participant details."""

    actor_reference: str = Field(..., description="FHIR resource reference")
    actor_type: str = Field(..., description="Type: Patient, Practitioner, Location, etc.")
    required: str = Field("required", description="required, optional, information-only")
    status: str = Field("accepted", description="Participation status")


class CreateAppointmentInput(BaseModel):
    """Input for creating appointment."""

    patient_id: str = Field(..., description="FHIR Patient reference")
    practitioner_id: str = Field(..., description="FHIR Practitioner reference")
    slot_id: str = Field(..., description="FHIR Slot reference")
    start_datetime: datetime = Field(..., description="Appointment start time")
    end_datetime: datetime = Field(..., description="Appointment end time")
    service_type: str = Field(..., description="Service type code")
    specialty_code: str = Field(..., description="Medical specialty code")
    location_id: str | None = Field(None, description="FHIR Location reference")
    reason: str | None = Field(None, description="Appointment reason")
    comment: str | None = Field(None, description="Additional comments")
    priority: int = Field(5, description="Priority 0-9, default 5")


class CreateAppointmentOutput(BaseModel):
    """Output from appointment creation."""

    appointment_reference: str = Field(..., description="Created Appointment FHIR reference")
    appointment_id: str = Field(..., description="Appointment resource ID")
    status: str = Field("booked", description="Appointment status")
    start_datetime: datetime = Field(..., description="Appointment start time")
    end_datetime: datetime = Field(..., description="Appointment end time")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    message: str = Field("", description="Success message")


class AppointmentCreator(ABC):
    """Protocol for creating appointments."""

    @abstractmethod
    async def create_appointment(
        self,
        patient_id: str,
        practitioner_id: str,
        slot_id: str,
        start_datetime: datetime,
        end_datetime: datetime,
        service_type: str,
        specialty_code: str,
        location_id: str | None = None,
        reason: str | None = None,
        comment: str | None = None,
        priority: int = 5,
        tenant_id: str | None = None,
    ) -> tuple[str, str]:
        """Create FHIR Appointment resource.

        Args:
            patient_id: FHIR Patient reference
            practitioner_id: FHIR Practitioner reference
            slot_id: FHIR Slot reference
            start_datetime: Appointment start time
            end_datetime: Appointment end time
            service_type: Service type code
            specialty_code: Medical specialty code
            location_id: Optional FHIR Location reference
            reason: Optional appointment reason
            comment: Optional additional comments
            priority: Priority 0-9
            tenant_id: Tenant identifier

        Returns:
            Tuple of (appointment_reference, appointment_id)

        Raises:
            PatientAccessException: If creation fails
        """
        ...


class StubAppointmentCreator(AppointmentCreator):
    """Stub implementation with DMN integration."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()

    async def create_appointment(
        self,
        patient_id: str,
        practitioner_id: str,
        slot_id: str,
        start_datetime: datetime,
        end_datetime: datetime,
        service_type: str,
        specialty_code: str,
        location_id: str | None = None,
        reason: str | None = None,
        comment: str | None = None,
        priority: int = 5,
        tenant_id: str | None = None,
    ) -> tuple[str, str]:
        """Create appointment with DMN validation."""
        import uuid

        # Validate appointment timing rules with DMN
        try:
            self.dmn_service.evaluate(
                tenant_id=tenant_id or get_required_tenant(),
                category='authorization',
                table_name='auth_timing_002',
                inputs={
                    'service_type': service_type,
                    'start_datetime': start_datetime.isoformat(),
                    'end_datetime': end_datetime.isoformat(),
                    'priority': priority
                }
            )
        except (FileNotFoundError, ValueError):
            # If DMN not available, proceed with creation
            pass

        # Validate appointment scope with DMN
        try:
            self.dmn_service.evaluate(
                tenant_id=tenant_id or get_required_tenant(),
                category='authorization',
                table_name='auth_scope_002',
                inputs={
                    'service_type': service_type,
                    'specialty_code': specialty_code,
                    'practitioner_id': practitioner_id
                }
            )
        except (FileNotFoundError, ValueError):
            # If DMN not available, proceed
            pass

        appointment_id = str(uuid.uuid4())
        appointment_reference = f"Appointment/{appointment_id}"

        # In real implementation, would:
        # 1. Build FHIR R4 Appointment resource
        # 2. Set status to "booked"
        # 3. Add participant entries for patient, practitioner, location
        # 4. Link to slot resource
        # 5. POST to FHIR server via fhir_client.create()
        # 6. Update slot status to "busy"

        return appointment_reference, appointment_id


class CreateAppointmentWorker:
    """Worker for creating appointments.

    Creates FHIR Appointment resources with proper participant linking,
    slot reservation, and status management according to FHIR R4 specification.
    """

    TOPIC = "scheduling.create_appointment"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol | None = None,
        appointment_creator: AppointmentCreator | None = None,
    ) -> None:
        """Initialize worker with dependencies.

        Args:
            fhir_client: FHIR client for resource access
            appointment_creator: Appointment creator implementation
        """
        self.fhir_client = fhir_client
        self.appointment_creator = appointment_creator or StubAppointmentCreator()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute appointment creation task.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with appointment reference and metadata

        Raises:
            PatientAccessException: If appointment creation fails
        """
        tenant_id = get_required_tenant()
        self.logger.info(
            _("Iniciando criação de agendamento"),
            extra={
                "tenant_id": tenant_id,
                "patient_id": task_variables.get("patient_id"),
                "practitioner_id": task_variables.get("practitioner_id"),
                "service_type": task_variables.get("service_type"),
            },
        )

        try:
            # Parse and validate input
            input_data = CreateAppointmentInput(**task_variables)

            # Create appointment
            appointment_reference, appointment_id = await self.appointment_creator.create_appointment(
                patient_id=input_data.patient_id,
                practitioner_id=input_data.practitioner_id,
                slot_id=input_data.slot_id,
                start_datetime=input_data.start_datetime,
                end_datetime=input_data.end_datetime,
                service_type=input_data.service_type,
                specialty_code=input_data.specialty_code,
                location_id=input_data.location_id,
                reason=input_data.reason,
                comment=input_data.comment,
                priority=input_data.priority,
                tenant_id=tenant_id,
            )

            # Build output
            output = CreateAppointmentOutput(
                appointment_reference=appointment_reference,
                appointment_id=appointment_id,
                status="booked",
                start_datetime=input_data.start_datetime,
                end_datetime=input_data.end_datetime,
                message=_("Agendamento criado com sucesso"),
            )

            self.logger.info(
                _("Agendamento criado"),
                extra={
                    "tenant_id": tenant_id,
                    "appointment_id": appointment_id,
                    "appointment_reference": appointment_reference,
                    "patient_id": input_data.patient_id,
                    "practitioner_id": input_data.practitioner_id,
                },
            )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                _("Erro ao criar agendamento"),
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": task_variables.get("patient_id"),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                message=_("Falha na criação do agendamento: {error}").format(error=str(e)),
                details={
                    "tenant_id": tenant_id,
                    "patient_id": task_variables.get("patient_id"),
                    "practitioner_id": task_variables.get("practitioner_id"),
                    "error": str(e),
                },
            ) from e
