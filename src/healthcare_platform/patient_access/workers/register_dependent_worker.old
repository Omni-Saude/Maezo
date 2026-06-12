"""
Dependent Registration Worker.

CIB7 External Task Topic: patient.register_dependent
BPMN Error Code: PATIENT_ACCESS_ERROR

Registers family members as dependents on insurance plans.
Links dependents to primary holders via FHIR RelatedPerson resources.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

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
    """Exception for patient access domain errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "PATIENT_ACCESS_ERROR",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, error_code, details)
        self.bpmn_error_code = "PATIENT_ACCESS_ERROR"


RelationshipType = Literal["spouse", "child", "parent", "sibling", "other"]


class DependentRegistrationInput(BaseModel):
    """Input for dependent registration."""

    dependent_patient_id: str = Field(..., description="Dependent patient identifier")
    primary_holder_patient_id: str = Field(..., description="Primary holder patient identifier")
    relationship_type: RelationshipType = Field(..., description="Type of relationship")
    insurance_plan_id: str = Field(..., description="Insurance plan identifier")


class DependentRegistrationOutput(BaseModel):
    """Output from dependent registration."""

    dependent_patient_id: str = Field(..., description="Dependent patient identifier")
    primary_holder_patient_id: str = Field(..., description="Primary holder patient identifier")
    related_person_id: str = Field(..., description="FHIR RelatedPerson resource ID")
    relationship_type: RelationshipType = Field(..., description="Type of relationship")
    insurance_plan_id: str = Field(..., description="Insurance plan identifier")
    registration_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Registration timestamp"
    )


class DependentRegistrarProtocol(ABC):
    """Protocol for dependent registration."""

    @abstractmethod
    async def validate_primary_holder(self, patient_id: str, insurance_plan_id: str) -> bool:
        """
        Validate that the primary holder is active on the insurance plan.

        Args:
            patient_id: Primary holder patient ID
            insurance_plan_id: Insurance plan ID

        Returns:
            True if valid, False otherwise
        """
        pass

    @abstractmethod
    async def validate_dependent_eligibility(
        self, dependent_patient_id: str, relationship_type: RelationshipType
    ) -> tuple[bool, str | None]:
        """
        Validate dependent eligibility (e.g., age limits for children).

        Args:
            dependent_patient_id: Dependent patient ID
            relationship_type: Type of relationship

        Returns:
            Tuple of (is_eligible, reason_if_not)
        """
        pass

    @abstractmethod
    async def create_fhir_related_person(
        self,
        dependent_patient_id: str,
        primary_holder_patient_id: str,
        relationship_type: RelationshipType,
    ) -> str:
        """
        Create FHIR RelatedPerson resource linking dependent to primary holder.

        Args:
            dependent_patient_id: Dependent patient ID
            primary_holder_patient_id: Primary holder patient ID
            relationship_type: Type of relationship

        Returns:
            RelatedPerson resource ID
        """
        pass

    @abstractmethod
    async def link_to_insurance_plan(
        self, dependent_patient_id: str, insurance_plan_id: str, primary_holder_patient_id: str
    ) -> None:
        """
        Link dependent to insurance plan under primary holder.

        Args:
            dependent_patient_id: Dependent patient ID
            insurance_plan_id: Insurance plan ID
            primary_holder_patient_id: Primary holder patient ID
        """
        pass


class StubDependentRegistrar(DependentRegistrarProtocol):
    """Stub implementation of dependent registrar for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()
        # DMN integration point: auth_scope_004
        # Inputs: {'dependent_relationship': dependent_relationship, 'subscriber_id': subscriber_id}
        # Call: self.dmn_service.evaluate(tenant_id=..., category='authorization', table_name='auth_scope_004', inputs={...})


    def __init__(self):
        self._active_plans: dict[str, set[str]] = {}  # plan_id -> set of patient_ids
        self._related_persons: dict[str, dict[str, Any]] = {}  # id -> data
        self._next_rp_id = 1

    async def validate_primary_holder(self, patient_id: str, insurance_plan_id: str) -> bool:
        """Validate primary holder is active on plan."""
        if insurance_plan_id not in self._active_plans:
            self._active_plans[insurance_plan_id] = {patient_id}
            return True

        return patient_id in self._active_plans[insurance_plan_id]

    async def validate_dependent_eligibility(
        self, dependent_patient_id: str, relationship_type: RelationshipType
    ) -> tuple[bool, str | None]:
        """Validate dependent eligibility."""
        # In stub, accept all relationships
        # In production, would check age limits for children, etc.
        if relationship_type not in ["spouse", "child", "parent", "sibling", "other"]:
            return False, _("Tipo de relacionamento inválido")

        return True, None

    async def create_fhir_related_person(
        self,
        dependent_patient_id: str,
        primary_holder_patient_id: str,
        relationship_type: RelationshipType,
    ) -> str:
        """Create FHIR RelatedPerson resource."""
        rp_id = f"RelatedPerson/{self._next_rp_id}"
        self._next_rp_id += 1

        self._related_persons[rp_id] = {
            "dependent_patient_id": dependent_patient_id,
            "primary_holder_patient_id": primary_holder_patient_id,
            "relationship_type": relationship_type,
        }

        return rp_id

    async def link_to_insurance_plan(
        self, dependent_patient_id: str, insurance_plan_id: str, primary_holder_patient_id: str
    ) -> None:
        """Link dependent to insurance plan."""
        if insurance_plan_id not in self._active_plans:
            self._active_plans[insurance_plan_id] = set()

        self._active_plans[insurance_plan_id].add(dependent_patient_id)


class RegisterDependentWorker:
    """
    Worker for registering dependents on insurance plans.

    Validates primary holder status, creates FHIR RelatedPerson resources,
    and links dependents to insurance plans.
    """

    TOPIC = "patient.register_dependent"

    def __init__(
        self,
        registrar: DependentRegistrarProtocol | None = None,
        fhir_client: FHIRClientProtocol | None = None,
    ):
        """
        Initialize the dependent registration worker.

        Args:
            registrar: Dependent registrar implementation
            fhir_client: FHIR client for resource operations
        """
        self.registrar = registrar or StubDependentRegistrar()
        self.fhir_client = fhir_client
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute dependent registration.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with registration results

        Raises:
            PatientAccessException: If registration fails
        """
        tenant_id = get_required_tenant()

        try:
            # Parse input
            input_data = DependentRegistrationInput(**task_variables)

            self.logger.info(
                "Registering dependent",
                extra={
                    "tenant_id": tenant_id,
                    "dependent_id": input_data.dependent_patient_id,
                    "holder_id": input_data.primary_holder_patient_id,
                    "relationship": input_data.relationship_type,
                },
            )

            # Validate primary holder
            is_valid_holder = await self.registrar.validate_primary_holder(
                input_data.primary_holder_patient_id, input_data.insurance_plan_id
            )
            if not is_valid_holder:
                raise PatientAccessException(
                    _("Titular do plano não encontrado ou inativo no plano especificado"),
                    details={
                        "tenant_id": tenant_id,
                        "holder_id": input_data.primary_holder_patient_id,
                        "plan_id": input_data.insurance_plan_id,
                    },
                )

            # Validate dependent eligibility
            is_eligible, reason = await self.registrar.validate_dependent_eligibility(
                input_data.dependent_patient_id, input_data.relationship_type
            )
            if not is_eligible:
                raise PatientAccessException(
                    _("Dependente não elegível: {reason}").format(reason=reason or "desconhecido"),
                    details={
                        "tenant_id": tenant_id,
                        "dependent_id": input_data.dependent_patient_id,
                        "reason": reason,
                    },
                )

            # Create FHIR RelatedPerson resource
            related_person_id = await self.registrar.create_fhir_related_person(
                input_data.dependent_patient_id,
                input_data.primary_holder_patient_id,
                input_data.relationship_type,
            )

            # Link to insurance plan
            await self.registrar.link_to_insurance_plan(
                input_data.dependent_patient_id,
                input_data.insurance_plan_id,
                input_data.primary_holder_patient_id,
            )

            output = DependentRegistrationOutput(
                dependent_patient_id=input_data.dependent_patient_id,
                primary_holder_patient_id=input_data.primary_holder_patient_id,
                related_person_id=related_person_id,
                relationship_type=input_data.relationship_type,
                insurance_plan_id=input_data.insurance_plan_id,
            )

            self.logger.info(
                "Dependent registered successfully",
                extra={
                    "tenant_id": tenant_id,
                    "dependent_id": input_data.dependent_patient_id,
                    "holder_id": input_data.primary_holder_patient_id,
                    "related_person_id": related_person_id,
                },
            )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                "Dependent registration failed",
                extra={
                    "tenant_id": tenant_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                _("Falha ao registrar dependente: {error}").format(error=str(e)),
                details={"tenant_id": tenant_id, "error": str(e)},
            )
