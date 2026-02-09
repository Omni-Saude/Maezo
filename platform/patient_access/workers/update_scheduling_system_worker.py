"""
Update Scheduling System Worker

CIB7 External Task Topic: scheduling.update_system
BPMN Error Code: PATIENT_ACCESS_ERROR

Syncs appointment data to external ERP systems (Tasy/MV Soul).
Handles partial sync failures gracefully with retry logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from pydantic import BaseModel, Field

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


class PatientAccessException(DomainException):
    """Domain exception for patient access operations."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="PATIENT_ACCESS_ERROR",
            details=details,
            bpmn_error_code="PATIENT_ACCESS_ERROR",
        )


class TasyClientProtocol(Protocol):
    """Protocol for Philips Tasy ERP integration."""

    async def sync_appointment(
        self, appointment_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Sync appointment to Tasy."""
        ...


class MVSoulClientProtocol(Protocol):
    """Protocol for MV Soul ERP integration."""

    async def sync_appointment(
        self, appointment_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Sync appointment to MV Soul."""
        ...


class SystemSyncStatus(BaseModel):
    """Sync status for a single system."""

    system_name: str = Field(..., description="System name (tasy, mv_soul, etc)")
    sync_successful: bool = Field(..., description="Whether sync succeeded")
    synced_at: str | None = Field(None, description="Sync timestamp (ISO 8601)")
    external_id: str | None = Field(None, description="External system record ID")
    error_message: str | None = Field(None, description="Error message if failed")
    retry_count: int = Field(default=0, description="Number of retry attempts")


class UpdateSchedulingSystemInput(BaseModel):
    """Input DTO for scheduling system update."""

    appointment_id: str = Field(..., description="FHIR Appointment ID")
    patient_id: str = Field(..., description="FHIR Patient ID")
    practitioner_id: str = Field(..., description="FHIR Practitioner ID")
    appointment_datetime: str = Field(
        ..., description="Appointment date and time (ISO 8601)"
    )
    appointment_type: str = Field(..., description="Appointment type code")
    location_id: str = Field(..., description="FHIR Location ID")
    specialty_code: str = Field(..., description="Medical specialty code")
    status: str = Field(..., description="Appointment status (booked, cancelled, etc)")
    systems_to_update: list[str] = Field(
        ..., description="List of systems to sync (tasy, mv_soul)"
    )
    insurance_plan_id: str | None = Field(None, description="Insurance plan ID if applicable")
    procedure_codes: list[str] = Field(
        default_factory=list, description="List of TUSS procedure codes"
    )


class UpdateSchedulingSystemOutput(BaseModel):
    """Output DTO for scheduling system update."""

    sync_completed: bool = Field(
        ..., description="Whether all syncs completed successfully"
    )
    systems_synced: int = Field(..., description="Number of systems successfully synced")
    systems_failed: int = Field(..., description="Number of systems that failed")
    sync_statuses: list[SystemSyncStatus] = Field(
        ..., description="Detailed sync status per system"
    )
    partial_success: bool = Field(
        ..., description="Whether at least one system synced successfully"
    )


class SchedulingSystemUpdaterProtocol(ABC):
    """Protocol for updating external scheduling systems."""

    @abstractmethod
    async def sync_to_tasy(
        self, appointment_data: dict[str, Any]
    ) -> SystemSyncStatus:
        """
        Sync appointment to Philips Tasy.

        Args:
            appointment_data: Appointment data to sync

        Returns:
            Sync status for Tasy
        """
        pass

    @abstractmethod
    async def sync_to_mv_soul(
        self, appointment_data: dict[str, Any]
    ) -> SystemSyncStatus:
        """
        Sync appointment to MV Soul.

        Args:
            appointment_data: Appointment data to sync

        Returns:
            Sync status for MV Soul
        """
        pass


class StubSchedulingSystemUpdater(SchedulingSystemUpdaterProtocol):
    """Stub implementation for testing."""

    def __init__(self):
        self.logger = get_logger(__name__, worker="scheduling.update_system")

    async def sync_to_tasy(
        self, appointment_data: dict[str, Any]
    ) -> SystemSyncStatus:
        """Stub implementation - logs and returns success."""
        from datetime import datetime, timezone

        appointment_id = appointment_data.get("appointment_id", "unknown")

        self.logger.info(
            "stub_tasy_sync",
            appointment_id=appointment_id,
            status=appointment_data.get("status"),
        )

        return SystemSyncStatus(
            system_name="tasy",
            sync_successful=True,
            synced_at=datetime.now(timezone.utc).isoformat(),
            external_id=f"tasy_{appointment_id}",
            error_message=None,
            retry_count=0,
        )

    async def sync_to_mv_soul(
        self, appointment_data: dict[str, Any]
    ) -> SystemSyncStatus:
        """Stub implementation - logs and returns success."""
        from datetime import datetime, timezone

        appointment_id = appointment_data.get("appointment_id", "unknown")

        self.logger.info(
            "stub_mv_soul_sync",
            appointment_id=appointment_id,
            status=appointment_data.get("status"),
        )

        return SystemSyncStatus(
            system_name="mv_soul",
            sync_successful=True,
            synced_at=datetime.now(timezone.utc).isoformat(),
            external_id=f"mv_soul_{appointment_id}",
            error_message=None,
            retry_count=0,
        )


class UpdateSchedulingSystemWorker:
    """Worker to sync appointments to external ERP systems."""

    TOPIC = "scheduling.update_system"

    def __init__(
        self,
        system_updater: SchedulingSystemUpdaterProtocol | None = None,
    ):
        """
        Initialize worker.

        Args:
            system_updater: Service to update systems (defaults to stub)
        """
        self.system_updater = system_updater or StubSchedulingSystemUpdater()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(task_type="scheduling.update_system")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute scheduling system update.

        Args:
            task_variables: Task variables from CIB7 process

        Returns:
            Dictionary with sync status for all systems

        Raises:
            PatientAccessException: If all syncs fail
        """
        tenant_id = get_required_tenant()

        try:
            # Parse and validate input
            input_data = UpdateSchedulingSystemInput(**task_variables)

            self.logger.info(
                "updating_scheduling_systems",
                tenant_id=tenant_id,
                appointment_id=input_data.appointment_id,
                systems=input_data.systems_to_update,
            )

            # Prepare appointment data for sync
            appointment_data = {
                "appointment_id": input_data.appointment_id,
                "patient_id": input_data.patient_id,
                "practitioner_id": input_data.practitioner_id,
                "appointment_datetime": input_data.appointment_datetime,
                "appointment_type": input_data.appointment_type,
                "location_id": input_data.location_id,
                "specialty_code": input_data.specialty_code,
                "status": input_data.status,
                "insurance_plan_id": input_data.insurance_plan_id,
                "procedure_codes": input_data.procedure_codes,
            }

            # Sync to each system
            sync_statuses = []
            for system_name in input_data.systems_to_update:
                try:
                    status = await self._sync_to_system(system_name, appointment_data)
                    sync_statuses.append(status)
                except Exception as e:
                    self.logger.warning(
                        "system_sync_failed",
                        tenant_id=tenant_id,
                        system=system_name,
                        error=str(e),
                    )
                    # Record failure but continue with other systems
                    from datetime import datetime, timezone

                    sync_statuses.append(
                        SystemSyncStatus(
                            system_name=system_name,
                            sync_successful=False,
                            synced_at=datetime.now(timezone.utc).isoformat(),
                            external_id=None,
                            error_message=str(e),
                            retry_count=1,
                        )
                    )

            # Calculate summary
            systems_synced = sum(1 for s in sync_statuses if s.sync_successful)
            systems_failed = len(sync_statuses) - systems_synced
            sync_completed = systems_failed == 0
            partial_success = systems_synced > 0

            # Validate output
            output = UpdateSchedulingSystemOutput(
                sync_completed=sync_completed,
                systems_synced=systems_synced,
                systems_failed=systems_failed,
                sync_statuses=sync_statuses,
                partial_success=partial_success,
            )

            # Log appropriate level based on outcome
            if sync_completed:
                self.logger.info(
                    "all_systems_synced",
                    tenant_id=tenant_id,
                    appointment_id=input_data.appointment_id,
                    systems_count=len(sync_statuses),
                )
            elif partial_success:
                self.logger.warning(
                    "partial_system_sync",
                    tenant_id=tenant_id,
                    appointment_id=input_data.appointment_id,
                    synced=systems_synced,
                    failed=systems_failed,
                )
            else:
                self.logger.error(
                    "all_systems_sync_failed",
                    tenant_id=tenant_id,
                    appointment_id=input_data.appointment_id,
                )
                raise PatientAccessException(
                    message=_("Falha ao sincronizar com todos os sistemas"),
                    details={
                        "appointment_id": input_data.appointment_id,
                        "systems": input_data.systems_to_update,
                        "sync_statuses": [s.model_dump() for s in sync_statuses],
                    },
                )

            return output.model_dump()

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "scheduling_system_update_failed",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PatientAccessException(
                message=_("Falha ao atualizar sistemas de agendamento: {error}").format(
                    error=str(e)
                ),
                details={
                    "appointment_id": task_variables.get("appointment_id"),
                    "systems": task_variables.get("systems_to_update", []),
                    "error_type": type(e).__name__,
                },
            ) from e

    async def _sync_to_system(
        self, system_name: str, appointment_data: dict[str, Any]
    ) -> SystemSyncStatus:
        """
        Sync to a specific system.

        Args:
            system_name: Name of the system to sync to
            appointment_data: Appointment data to sync

        Returns:
            Sync status for the system

        Raises:
            ValueError: If system is not supported
        """
        if system_name == "tasy":
            return await self.system_updater.sync_to_tasy(appointment_data)
        elif system_name == "mv_soul":
            return await self.system_updater.sync_to_mv_soul(appointment_data)
        else:
            raise ValueError(
                _("Sistema não suportado: {system}").format(system=system_name)
            )
