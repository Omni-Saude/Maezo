"""
Create Patient Record Worker

CIB7 External Task Topic: patient.create_record
BPMN Error Code: PATIENT_ACCESS_ERROR

Creates FHIR Patient resource with demographics.
Maps patient data to FHIR Patient structure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
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
    """Exception for patient access domain errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.bpmn_error_code = "PATIENT_ACCESS_ERROR"


class CreatePatientRecordInput(BaseModel):
    """Input model for creating patient record."""

    cpf_hash: str = Field(..., description="Hash SHA-256 do CPF")
    cns_hash: str | None = Field(None, description="Hash SHA-256 do CNS")
    name: str = Field(..., description="Nome completo do paciente")
    birth_date: str = Field(..., description="Data de nascimento (YYYY-MM-DD)")
    gender: str = Field(..., description="Gênero (male/female/other/unknown)")


class CreatePatientRecordOutput(BaseModel):
    """Output model for creating patient record."""

    patient_reference: str = Field(..., description="Referência FHIR do paciente")
    patient_id: str = Field(..., description="ID do paciente")
    created: bool = Field(..., description="Se o paciente foi criado com sucesso")


class PatientRecordCreator(ABC):
    """Protocol for creating patient records."""

    @abstractmethod
    async def build_fhir_patient(
        self,
        cpf_hash: str,
        cns_hash: str | None,
        name: str,
        birth_date: str,
        gender: str,
    ) -> dict[str, Any]:
        """Build FHIR Patient resource."""
        pass

    @abstractmethod
    async def validate_patient_resource(self, patient: dict[str, Any]) -> bool:
        """Validate FHIR Patient resource."""
        pass


class StubPatientRecordCreator(PatientRecordCreator):
    """Stub implementation for testing."""

    async def build_fhir_patient(
        self,
        cpf_hash: str,
        cns_hash: str | None,
        name: str,
        birth_date: str,
        gender: str,
    ) -> dict[str, Any]:
        """Build FHIR Patient resource."""
        identifiers = [
            {
                "system": "urn:brasil:gov:cpf",
                "value": cpf_hash,
                "use": "official",
            }
        ]

        if cns_hash:
            identifiers.append(
                {
                    "system": "urn:brasil:gov:cns",
                    "value": cns_hash,
                    "use": "official",
                }
            )

        return {
            "resourceType": "Patient",
            "identifier": identifiers,
            "name": [{"use": "official", "text": name}],
            "birthDate": birth_date,
            "gender": gender,
            "active": True,
        }

    async def validate_patient_resource(self, patient: dict[str, Any]) -> bool:
        """Validate FHIR Patient resource."""
        required_fields = ["resourceType", "identifier", "name", "birthDate", "gender"]
        return all(field in patient for field in required_fields)


class CreatePatientRecordWorker:
    """Worker for creating patient records."""

    TOPIC = "patient.create_record"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        creator: PatientRecordCreator | None = None,
    ):
        """Initialize worker with FHIR client and creator."""
        self.fhir_client = fhir_client
        self.creator = creator or StubPatientRecordCreator()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(task_type="patient.create_record")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute patient record creation.

        Args:
            task_variables: Task variables containing patient data

        Returns:
            Patient reference and creation status

        Raises:
            PatientAccessException: If creation fails
        """
        tenant_id = get_required_tenant()
        self.logger.info(
            "Criando registro de paciente",
            extra={"tenant_id": tenant_id, "task_variables": task_variables},
        )

        try:
            # Parse input
            input_data = CreatePatientRecordInput(**task_variables)

            # Build FHIR Patient resource
            patient_resource = await self.creator.build_fhir_patient(
                cpf_hash=input_data.cpf_hash,
                cns_hash=input_data.cns_hash,
                name=input_data.name,
                birth_date=input_data.birth_date,
                gender=input_data.gender,
            )

            self.logger.info(
                "Recurso FHIR Patient construído",
                extra={"tenant_id": tenant_id, "resource": patient_resource},
            )

            # Validate resource
            is_valid = await self.creator.validate_patient_resource(patient_resource)
            if not is_valid:
                raise PatientAccessException(
                    _("Recurso FHIR Patient inválido"),
                    details={"resource": patient_resource},
                )

            # Create patient in FHIR server
            try:
                created_patient = await self.fhir_client.create(
                    "Patient", patient_resource
                )

                patient_id = created_patient.get("id")
                if not patient_id:
                    raise PatientAccessException(
                        _("ID do paciente não retornado pelo servidor FHIR"),
                        details={"response": created_patient},
                    )

                patient_reference = f"Patient/{patient_id}"

                self.logger.info(
                    "Paciente criado com sucesso",
                    extra={
                        "tenant_id": tenant_id,
                        "patient_id": patient_id,
                        "patient_reference": patient_reference,
                    },
                )

                output = CreatePatientRecordOutput(
                    patient_reference=patient_reference,
                    patient_id=patient_id,
                    created=True,
                )

                return output.model_dump()

            except Exception as fhir_error:
                self.logger.error(
                    "Erro ao criar paciente no FHIR",
                    extra={"tenant_id": tenant_id, "error": str(fhir_error)},
                    exc_info=True,
                )
                raise PatientAccessException(
                    _("Erro ao criar paciente no FHIR: {error}").format(
                        error=str(fhir_error)
                    ),
                    details={"original_error": str(fhir_error)},
                )

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "Erro ao criar registro de paciente",
                extra={"tenant_id": tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise PatientAccessException(
                _("Erro ao criar registro de paciente: {error}").format(error=str(e)),
                details={"original_error": str(e)},
            )
