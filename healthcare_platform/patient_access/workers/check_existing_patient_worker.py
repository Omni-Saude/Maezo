"""
Check Existing Patient Worker

CIB7 External Task Topic: patient.check_existing
BPMN Error Code: PATIENT_ACCESS_ERROR

Searches FHIR for existing patient records using CPF and CNS hashes.
Returns existing patient reference if found.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.domain.value_objects import FHIRReference
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution


class PatientAccessException(DomainException):
    """Exception for patient access domain errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.bpmn_error_code = "PATIENT_ACCESS_ERROR"


class CheckExistingPatientInput(BaseModel):
    """Input model for checking existing patient."""

    cpf_hash: str = Field(..., description="Hash SHA-256 do CPF")
    cns_hash: str | None = Field(None, description="Hash SHA-256 do CNS")


class CheckExistingPatientOutput(BaseModel):
    """Output model for checking existing patient."""

    patient_exists: bool = Field(..., description="Se o paciente já existe")
    patient_reference: str | None = Field(
        None, description="Referência FHIR do paciente existente"
    )
    patient_id: str | None = Field(None, description="ID do paciente existente")


class PatientDuplicateChecker(ABC):
    """Protocol for checking duplicate patients."""

    @abstractmethod
    async def search_by_identifiers(
        self, cpf_hash: str, cns_hash: str | None
    ) -> list[dict[str, Any]]:
        """Search for patients by CPF and CNS hashes."""
        pass


class StubPatientDuplicateChecker(PatientDuplicateChecker):
    """Stub implementation for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()

    async def search_by_identifiers(
        self, cpf_hash: str, cns_hash: str | None
    ) -> list[dict[str, Any]]:
        """Search for patients by identifiers using DMN."""
        tenant_id = get_required_tenant()

        try:
            result = self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category='authorization',
                table_name='fed_auth_002',
                inputs={
                    'cpf_hash': cpf_hash,
                    'cns_hash': cns_hash or ''
                }
            )
            # DMN could return matching patient IDs or rules for duplicate detection
            return result.get('matches', [])
        except (FileNotFoundError, ValueError):
            # Fallback: stub returns no matches
            return []


class CheckExistingPatientWorker:
    """Worker for checking existing patient records."""

    TOPIC = "patient.check_existing"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        checker: PatientDuplicateChecker | None = None,
    ):
        """Initialize worker with FHIR client and checker."""
        self.fhir_client = fhir_client
        self.checker = checker or StubPatientDuplicateChecker()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(task_type="patient.check_existing")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute existing patient check.

        Args:
            task_variables: Task variables containing CPF and CNS hashes

        Returns:
            Patient existence status and reference if found

        Raises:
            PatientAccessException: If check fails
        """
        tenant_id = get_required_tenant()
        self.logger.info(
            "Verificando existência de paciente",
            extra={"tenant_id": tenant_id, "task_variables": task_variables},
        )

        try:
            # Parse input
            input_data = CheckExistingPatientInput(**task_variables)

            # Search for existing patient using FHIR client
            search_params = {
                "identifier": f"urn:brasil:gov:cpf|{input_data.cpf_hash}"
            }

            if input_data.cns_hash:
                search_params["identifier"] = [
                    f"urn:brasil:gov:cpf|{input_data.cpf_hash}",
                    f"urn:brasil:gov:cns|{input_data.cns_hash}",
                ]

            self.logger.info(
                "Buscando paciente no FHIR",
                extra={"tenant_id": tenant_id, "search_params": search_params},
            )

            try:
                search_results = await self.fhir_client.search(
                    "Patient", params=search_params
                )

                # Check if any patients found
                patients = search_results.get("entry", [])

                if patients:
                    # Return first matching patient
                    patient_resource = patients[0].get("resource", {})
                    patient_id = patient_resource.get("id")
                    patient_reference = f"Patient/{patient_id}"

                    self.logger.info(
                        "Paciente existente encontrado",
                        extra={
                            "tenant_id": tenant_id,
                            "patient_id": patient_id,
                            "patient_reference": patient_reference,
                        },
                    )

                    output = CheckExistingPatientOutput(
                        patient_exists=True,
                        patient_reference=patient_reference,
                        patient_id=patient_id,
                    )
                else:
                    self.logger.info(
                        "Nenhum paciente existente encontrado",
                        extra={"tenant_id": tenant_id},
                    )

                    output = CheckExistingPatientOutput(
                        patient_exists=False,
                        patient_reference=None,
                        patient_id=None,
                    )

                return output.model_dump()

            except Exception as fhir_error:
                self.logger.warning(
                    "Erro ao buscar paciente no FHIR",
                    extra={"tenant_id": tenant_id, "error": str(fhir_error)},
                )
                # Fallback to checker protocol
                results = await self.checker.search_by_identifiers(
                    input_data.cpf_hash, input_data.cns_hash
                )

                if results:
                    patient_id = results[0].get("id")
                    patient_reference = f"Patient/{patient_id}"

                    output = CheckExistingPatientOutput(
                        patient_exists=True,
                        patient_reference=patient_reference,
                        patient_id=patient_id,
                    )
                else:
                    output = CheckExistingPatientOutput(
                        patient_exists=False,
                        patient_reference=None,
                        patient_id=None,
                    )

                return output.model_dump()

        except Exception as e:
            self.logger.error(
                "Erro ao verificar existência de paciente",
                extra={"tenant_id": tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise PatientAccessException(
                _("Erro ao verificar existência de paciente: {error}").format(
                    error=str(e)
                ),
                details={"original_error": str(e)},
            )
