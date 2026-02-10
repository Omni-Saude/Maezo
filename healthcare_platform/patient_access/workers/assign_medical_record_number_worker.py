"""
Medical Record Number Assignment Worker.

CIB7 External Task Topic: patient.assign_mrn
BPMN Error Code: PATIENT_ACCESS_ERROR

Generates unique Medical Record Numbers (MRN) and validates against CNES
(Cadastro Nacional de Estabelecimentos de Saúde).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution


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


class MRNAssignmentInput(BaseModel):
    """Input for MRN assignment."""

    patient_id: str = Field(..., description="Patient identifier")
    facility_cnes_code: str = Field(..., description="CNES code of the facility")
    patient_cpf_hash: str = Field(..., description="SHA-256 hash of patient CPF")


class MRNAssignmentOutput(BaseModel):
    """Output from MRN assignment."""

    patient_id: str = Field(..., description="Patient identifier")
    mrn: str = Field(..., description="Assigned Medical Record Number")
    facility_cnes_code: str = Field(..., description="CNES code of the facility")
    sequence_number: int = Field(..., description="Sequence number within facility")
    formatted_mrn: str = Field(..., description="Formatted MRN (CNES-SEQUENCE)")


class MRNAssignerProtocol(ABC):
    """Protocol for MRN assignment."""

    @abstractmethod
    async def validate_cnes_code(self, cnes_code: str) -> tuple[bool, str | None]:
        """
        Validate CNES code format and existence.

        Args:
            cnes_code: CNES code to validate

        Returns:
            Tuple of (is_valid, facility_name_or_error)
        """
        pass

    @abstractmethod
    async def get_next_sequence_number(
        self, facility_cnes_code: str, patient_cpf_hash: str
    ) -> int:
        """
        Get the next sequence number for a facility.

        Args:
            facility_cnes_code: CNES code of the facility
            patient_cpf_hash: SHA-256 hash of patient CPF for idempotency

        Returns:
            Next sequence number
        """
        pass

    @abstractmethod
    async def check_mrn_exists(self, mrn: str) -> bool:
        """
        Check if an MRN already exists.

        Args:
            mrn: MRN to check

        Returns:
            True if MRN exists, False otherwise
        """
        pass

    @abstractmethod
    async def store_mrn_assignment(
        self, patient_id: str, mrn: str, facility_cnes_code: str, sequence_number: int
    ) -> None:
        """
        Store MRN assignment.

        Args:
            patient_id: Patient identifier
            mrn: Assigned MRN
            facility_cnes_code: CNES code
            sequence_number: Sequence number
        """
        pass


class StubMRNAssigner(MRNAssignerProtocol):
    """Stub implementation of MRN assigner for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()
        # DMN integration point: auth_coding_003
        # Inputs: {'patient_id': patient_id, 'facility_code': facility_code}
        # Call: self.dmn_service.evaluate(tenant_id=..., category='authorization', table_name='auth_coding_003', inputs={...})


    def __init__(self):
        self._sequence_counters: dict[str, int] = {}
        self._mrn_registry: dict[str, dict[str, Any]] = {}
        self._patient_mrn_map: dict[str, str] = {}  # patient_cpf_hash -> mrn

    async def validate_cnes_code(self, cnes_code: str) -> tuple[bool, str | None]:
        """Validate CNES code format."""
        # Remove non-digits
        cnes_digits = "".join(filter(str.isdigit, cnes_code))

        if len(cnes_digits) != 7:
            return False, _("Código CNES deve conter 7 dígitos")

        # In stub, accept any 7-digit code
        return True, f"Facility-{cnes_digits}"

    async def get_next_sequence_number(
        self, facility_cnes_code: str, patient_cpf_hash: str
    ) -> int:
        """Get next sequence number with idempotency check."""
        # Check if patient already has an MRN at this facility
        idempotency_key = f"{facility_cnes_code}:{patient_cpf_hash}"
        if idempotency_key in self._patient_mrn_map:
            # Return existing sequence number
            existing_mrn = self._patient_mrn_map[idempotency_key]
            return self._mrn_registry[existing_mrn]["sequence_number"]

        # Get next sequence
        if facility_cnes_code not in self._sequence_counters:
            self._sequence_counters[facility_cnes_code] = 1
        else:
            self._sequence_counters[facility_cnes_code] += 1

        return self._sequence_counters[facility_cnes_code]

    async def check_mrn_exists(self, mrn: str) -> bool:
        """Check if MRN exists."""
        return mrn in self._mrn_registry

    async def store_mrn_assignment(
        self, patient_id: str, mrn: str, facility_cnes_code: str, sequence_number: int
    ) -> None:
        """Store MRN assignment."""
        self._mrn_registry[mrn] = {
            "patient_id": patient_id,
            "facility_cnes_code": facility_cnes_code,
            "sequence_number": sequence_number,
        }


class AssignMedicalRecordNumberWorker:
    """
    Worker for assigning Medical Record Numbers (MRN).

    Generates unique MRN in format {CNES_CODE}-{SEQUENCE} (e.g., "2077485-000123").
    Validates against CNES and ensures uniqueness per facility.
    """

    TOPIC = "patient.assign_mrn"

    def __init__(self, assigner: MRNAssignerProtocol | None = None):
        """
        Initialize the MRN assignment worker.

        Args:
            assigner: MRN assigner implementation
        """
        self.assigner = assigner or StubMRNAssigner()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    def _format_mrn(self, cnes_code: str, sequence: int) -> str:
        """
        Format MRN as CNES-SEQUENCE.

        Args:
            cnes_code: CNES code
            sequence: Sequence number

        Returns:
            Formatted MRN
        """
        # Remove non-digits from CNES
        cnes_digits = "".join(filter(str.isdigit, cnes_code))
        # Pad sequence to 6 digits
        sequence_str = str(sequence).zfill(6)
        return f"{cnes_digits}-{sequence_str}"

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute MRN assignment.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with MRN assignment results

        Raises:
            PatientAccessException: If assignment fails
        """
        tenant_id = get_required_tenant()

        try:
            # Parse input
            input_data = MRNAssignmentInput(**task_variables)

            self.logger.info(
                "Assigning MRN for patient",
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": input_data.patient_id,
                    "facility_cnes": input_data.facility_cnes_code,
                },
            )

            # Validate CNES code
            is_valid, facility_name = await self.assigner.validate_cnes_code(
                input_data.facility_cnes_code
            )
            if not is_valid:
                raise PatientAccessException(
                    _("Código CNES inválido: {error}").format(error=facility_name or "desconhecido"),
                    details={
                        "tenant_id": tenant_id,
                        "cnes_code": input_data.facility_cnes_code,
                    },
                )

            # Get next sequence number (with idempotency via patient_cpf_hash)
            sequence_number = await self.assigner.get_next_sequence_number(
                input_data.facility_cnes_code, input_data.patient_cpf_hash
            )

            # Format MRN
            formatted_mrn = self._format_mrn(input_data.facility_cnes_code, sequence_number)

            # Check for collision (should be extremely rare)
            if await self.assigner.check_mrn_exists(formatted_mrn):
                self.logger.warning(
                    "MRN collision detected, regenerating",
                    extra={
                        "tenant_id": tenant_id,
                        "mrn": formatted_mrn,
                    },
                )
                # In production, this would trigger retry logic
                raise PatientAccessException(
                    _("Colisão de MRN detectada, por favor tente novamente"),
                    details={"tenant_id": tenant_id, "mrn": formatted_mrn},
                )

            # Store MRN assignment
            await self.assigner.store_mrn_assignment(
                input_data.patient_id,
                formatted_mrn,
                input_data.facility_cnes_code,
                sequence_number,
            )

            output = MRNAssignmentOutput(
                patient_id=input_data.patient_id,
                mrn=formatted_mrn,
                facility_cnes_code=input_data.facility_cnes_code,
                sequence_number=sequence_number,
                formatted_mrn=formatted_mrn,
            )

            self.logger.info(
                "MRN assigned successfully",
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": input_data.patient_id,
                    "mrn": formatted_mrn,
                    "facility": facility_name,
                },
            )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "MRN assignment failed",
                extra={
                    "tenant_id": tenant_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                _("Falha ao atribuir número de prontuário: {error}").format(error=str(e)),
                details={"tenant_id": tenant_id, "error": str(e)},
            )
