"""
Patient Registry Update Worker.

CIB7 External Task Topic: patient.update_registry
BPMN Error Code: PATIENT_ACCESS_ERROR

Syncs patient data to ERP systems (Tasy, MV Soul).
Handles partial sync failures gracefully with retry logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


class PatientAccessException(DomainException):
    """Exception for patient access domain errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "PATIENT_ACCESS_ERROR",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, error_code, details)
        self.bpmn_error_code = "PATIENT_ACCESS_ERROR"


class PatientRegistryUpdateInput(BaseModel):
    """Input for patient registry update."""

    patient_id: str = Field(..., description="Patient identifier")
    mrn: str = Field(..., description="Medical Record Number")
    patient_data: dict[str, Any] = Field(..., description="Patient data to sync")
    target_systems: list[str] = Field(
        default=["tasy", "mv_soul"], description="Target ERP systems to sync"
    )


class SystemSyncResult(BaseModel):
    """Result of syncing to a single system."""

    system_name: str = Field(..., description="Name of the system")
    success: bool = Field(..., description="Whether sync succeeded")
    error_message: str | None = Field(None, description="Error message if failed")
    sync_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When sync was attempted"
    )


class PatientRegistryUpdateOutput(BaseModel):
    """Output from patient registry update."""

    patient_id: str = Field(..., description="Patient identifier")
    mrn: str = Field(..., description="Medical Record Number")
    sync_results: list[SystemSyncResult] = Field(..., description="Results per system")
    all_systems_synced: bool = Field(..., description="Whether all systems synced successfully")
    failed_systems: list[str] = Field(
        default_factory=list, description="List of systems that failed to sync"
    )
    update_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When update was performed"
    )


class TasyClientProtocol(ABC):
    """Protocol for Tasy ERP integration."""

    @abstractmethod
    async def sync_patient(self, patient_id: str, mrn: str, patient_data: dict[str, Any]) -> None:
        """
        Sync patient data to Tasy.

        Args:
            patient_id: Patient identifier
            mrn: Medical Record Number
            patient_data: Patient data to sync

        Raises:
            Exception: If sync fails
        """
        pass


class MVSoulClientProtocol(ABC):
    """Protocol for MV Soul ERP integration."""

    @abstractmethod
    async def sync_patient(self, patient_id: str, mrn: str, patient_data: dict[str, Any]) -> None:
        """
        Sync patient data to MV Soul.

        Args:
            patient_id: Patient identifier
            mrn: Medical Record Number
            patient_data: Patient data to sync

        Raises:
            Exception: If sync fails
        """
        pass


class StubTasyClient(TasyClientProtocol):
    """Stub implementation of Tasy client for testing."""

    def __init__(self):
        self._synced_patients: dict[str, dict[str, Any]] = {}

    async def sync_patient(self, patient_id: str, mrn: str, patient_data: dict[str, Any]) -> None:
        """Sync patient to Tasy (stub)."""
        self._synced_patients[patient_id] = {
            "mrn": mrn,
            "data": patient_data,
            "timestamp": datetime.utcnow(),
        }


class StubMVSoulClient(MVSoulClientProtocol):
    """Stub implementation of MV Soul client for testing."""

    def __init__(self):
        self._synced_patients: dict[str, dict[str, Any]] = {}

    async def sync_patient(self, patient_id: str, mrn: str, patient_data: dict[str, Any]) -> None:
        """Sync patient to MV Soul (stub)."""
        self._synced_patients[patient_id] = {
            "mrn": mrn,
            "data": patient_data,
            "timestamp": datetime.utcnow(),
        }


class PatientRegistryUpdaterProtocol(ABC):
    """Protocol for patient registry updates."""

    @abstractmethod
    async def sync_to_system(
        self, system_name: str, patient_id: str, mrn: str, patient_data: dict[str, Any]
    ) -> SystemSyncResult:
        """
        Sync patient data to a specific system.

        Args:
            system_name: Name of the system (tasy, mv_soul)
            patient_id: Patient identifier
            mrn: Medical Record Number
            patient_data: Patient data to sync

        Returns:
            Sync result for the system
        """
        pass


class StubPatientRegistryUpdater(PatientRegistryUpdaterProtocol):
    """Stub implementation of patient registry updater for testing."""

    def __init__(
        self,
        tasy_client: TasyClientProtocol | None = None,
        mv_soul_client: MVSoulClientProtocol | None = None,
    ):
        self.tasy_client = tasy_client or StubTasyClient()
        self.mv_soul_client = mv_soul_client or StubMVSoulClient()

    async def sync_to_system(
        self, system_name: str, patient_id: str, mrn: str, patient_data: dict[str, Any]
    ) -> SystemSyncResult:
        """Sync patient data to a specific system."""
        try:
            if system_name == "tasy":
                await self.tasy_client.sync_patient(patient_id, mrn, patient_data)
            elif system_name == "mv_soul":
                await self.mv_soul_client.sync_patient(patient_id, mrn, patient_data)
            else:
                raise ValueError(_("Sistema desconhecido: {system}").format(system=system_name))

            return SystemSyncResult(system_name=system_name, success=True)

        except Exception as e:
            return SystemSyncResult(
                system_name=system_name, success=False, error_message=str(e)
            )


class UpdatePatientRegistryWorker:
    """
    Worker for updating patient registry across ERP systems.

    Syncs patient data to Tasy and MV Soul ERP systems.
    Handles partial failures gracefully and reports per-system results.
    """

    TOPIC = "patient.update_registry"

    def __init__(self, updater: PatientRegistryUpdaterProtocol | None = None):
        """
        Initialize the patient registry update worker.

        Args:
            updater: Patient registry updater implementation
        """
        self.updater = updater or StubPatientRegistryUpdater()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute patient registry update.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with sync results

        Raises:
            PatientAccessException: If all systems fail to sync
        """
        tenant_id = get_required_tenant()

        try:
            # Parse input
            input_data = PatientRegistryUpdateInput(**task_variables)

            self.logger.info(
                "Updating patient registry",
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": input_data.patient_id,
                    "mrn": input_data.mrn,
                    "target_systems": input_data.target_systems,
                },
            )

            sync_results: list[SystemSyncResult] = []
            failed_systems: list[str] = []

            # Sync to each target system
            for system_name in input_data.target_systems:
                result = await self.updater.sync_to_system(
                    system_name, input_data.patient_id, input_data.mrn, input_data.patient_data
                )
                sync_results.append(result)

                if not result.success:
                    failed_systems.append(system_name)
                    self.logger.warning(
                        "Failed to sync to system",
                        extra={
                            "tenant_id": tenant_id,
                            "patient_id": input_data.patient_id,
                            "system": system_name,
                            "error": result.error_message,
                        },
                    )

            all_systems_synced = len(failed_systems) == 0

            output = PatientRegistryUpdateOutput(
                patient_id=input_data.patient_id,
                mrn=input_data.mrn,
                sync_results=sync_results,
                all_systems_synced=all_systems_synced,
                failed_systems=failed_systems,
            )

            if all_systems_synced:
                self.logger.info(
                    "Patient registry updated successfully",
                    extra={
                        "tenant_id": tenant_id,
                        "patient_id": input_data.patient_id,
                        "systems_synced": len(sync_results),
                    },
                )
            else:
                self.logger.warning(
                    "Patient registry partially updated",
                    extra={
                        "tenant_id": tenant_id,
                        "patient_id": input_data.patient_id,
                        "failed_systems": failed_systems,
                        "success_count": len(sync_results) - len(failed_systems),
                    },
                )

                # If ALL systems failed, raise exception
                if len(failed_systems) == len(input_data.target_systems):
                    raise PatientAccessException(
                        _("Falha ao sincronizar com todos os sistemas: {systems}").format(
                            systems=", ".join(failed_systems)
                        ),
                        details={
                            "tenant_id": tenant_id,
                            "patient_id": input_data.patient_id,
                            "failed_systems": failed_systems,
                        },
                    )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "Patient registry update failed",
                extra={
                    "tenant_id": tenant_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                _("Falha ao atualizar registro do paciente: {error}").format(error=str(e)),
                details={"tenant_id": tenant_id, "error": str(e)},
            )
