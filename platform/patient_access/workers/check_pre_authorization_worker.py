"""Check Pre-Authorization Worker - Patient Access Domain.

CIB7 External Task Topic: scheduling.check_pre_auth
BPMN Error Code: PATIENT_ACCESS_ERROR

Checks if appointment requires insurance pre-authorization and validates
existing authorizations with health insurance providers (ANS).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
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


class PreAuthCheckInput(BaseModel):
    """Input for pre-authorization check."""

    patient_id: str = Field(..., description="FHIR Patient reference")
    coverage_id: str = Field(..., description="FHIR Coverage reference")
    service_type: str = Field(..., description="Service type code")
    procedure_codes: list[str] = Field(default_factory=list, description="Procedure codes")
    specialty_code: str = Field(..., description="Medical specialty code")
    practitioner_id: str = Field(..., description="FHIR Practitioner reference")
    proposed_date: datetime = Field(..., description="Proposed appointment date")
    estimated_cost: float | None = Field(None, description="Estimated cost in BRL")


class AuthorizationDetails(BaseModel):
    """Pre-authorization details."""

    authorization_number: str = Field(..., description="Authorization reference number")
    status: str = Field(..., description="Status: approved, pending, denied")
    approved_date: datetime | None = Field(None, description="Approval date")
    expiration_date: datetime | None = Field(None, description="Expiration date")
    approved_procedures: list[str] = Field(default_factory=list, description="Approved procedures")
    authorized_amount: float | None = Field(None, description="Authorized amount in BRL")
    notes: str | None = Field(None, description="Additional notes")


class PreAuthCheckOutput(BaseModel):
    """Output from pre-authorization check."""

    pre_auth_required: bool = Field(..., description="Whether pre-auth is required")
    authorization_status: str = Field(
        "not_required", description="Status: approved, pending, denied, not_required"
    )
    authorization_number: str | None = Field(None, description="Authorization number if exists")
    authorization_details: AuthorizationDetails | None = Field(
        None, description="Full authorization details"
    )
    requires_action: bool = Field(False, description="Whether action is needed")
    action_message: str | None = Field(None, description="Action required message")
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    message: str = Field("", description="Status message")


class PreAuthorizationChecker(ABC):
    """Protocol for checking pre-authorization."""

    @abstractmethod
    async def check_pre_authorization(
        self,
        patient_id: str,
        coverage_id: str,
        service_type: str,
        procedure_codes: list[str],
        specialty_code: str,
        practitioner_id: str,
        proposed_date: datetime,
        estimated_cost: float | None = None,
        tenant_id: str | None = None,
    ) -> tuple[bool, str, AuthorizationDetails | None]:
        """Check pre-authorization requirements.

        Args:
            patient_id: FHIR Patient reference
            coverage_id: FHIR Coverage reference
            service_type: Service type code
            procedure_codes: Procedure codes to check
            specialty_code: Medical specialty code
            practitioner_id: FHIR Practitioner reference
            proposed_date: Proposed appointment date
            estimated_cost: Optional estimated cost
            tenant_id: Tenant identifier

        Returns:
            Tuple of (pre_auth_required, status, authorization_details)

        Raises:
            PatientAccessException: If check fails
        """
        ...


class StubPreAuthorizationChecker(PreAuthorizationChecker):
    """Stub implementation for testing."""

    # Service types requiring pre-authorization
    REQUIRES_PRE_AUTH = {
        "cirurgia",
        "procedimento",
        "exame_complexo",
        "internacao",
        "terapia_intensiva",
    }

    # Procedures requiring pre-authorization (TUSS codes)
    HIGH_COST_PROCEDURES = {
        "40101010",  # Cirurgia cardíaca
        "40201020",  # Ressonância magnética
        "40301030",  # Tomografia computadorizada
        "40401040",  # PET-CT
        "40501050",  # Quimioterapia
    }

    async def check_pre_authorization(
        self,
        patient_id: str,
        coverage_id: str,
        service_type: str,
        procedure_codes: list[str],
        specialty_code: str,
        practitioner_id: str,
        proposed_date: datetime,
        estimated_cost: float | None = None,
        tenant_id: str | None = None,
    ) -> tuple[bool, str, AuthorizationDetails | None]:
        """Check pre-authorization with stub logic."""
        # Check if service type requires pre-auth
        requires_pre_auth = service_type in self.REQUIRES_PRE_AUTH

        # Check if any procedure requires pre-auth
        if not requires_pre_auth:
            requires_pre_auth = any(
                code in self.HIGH_COST_PROCEDURES for code in procedure_codes
            )

        # Check if estimated cost is high (>= 1000 BRL)
        if not requires_pre_auth and estimated_cost:
            requires_pre_auth = estimated_cost >= 1000.0

        if not requires_pre_auth:
            return False, "not_required", None

        # In real implementation, would:
        # 1. Query FHIR Coverage resource for insurance details
        # 2. Call ANS/insurance provider API to check authorization
        # 3. Validate existing authorizations
        # 4. Check expiration dates
        # 5. Verify approved procedures match request

        # Stub: Create mock authorization
        from datetime import timedelta
        import uuid

        auth_number = f"AUTH-{uuid.uuid4().hex[:8].upper()}"
        auth_details = AuthorizationDetails(
            authorization_number=auth_number,
            status="approved",
            approved_date=datetime.utcnow(),
            expiration_date=datetime.utcnow() + timedelta(days=90),
            approved_procedures=procedure_codes,
            authorized_amount=estimated_cost,
            notes=_("Autorização gerada automaticamente pelo sistema stub"),
        )

        return True, "approved", auth_details


class CheckPreAuthorizationWorker:
    """Worker for checking insurance pre-authorization.

    Validates whether appointments require insurance pre-authorization
    and checks the status of existing authorizations with health plans.
    """

    TOPIC = "scheduling.check_pre_auth"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol | None = None,
        pre_auth_checker: PreAuthorizationChecker | None = None,
    ) -> None:
        """Initialize worker with dependencies.

        Args:
            fhir_client: FHIR client for Coverage resource access
            pre_auth_checker: Pre-authorization checker implementation
        """
        self.fhir_client = fhir_client
        self.pre_auth_checker = pre_auth_checker or StubPreAuthorizationChecker()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute pre-authorization check task.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with authorization status and details

        Raises:
            PatientAccessException: If pre-auth check fails
        """
        tenant_id = get_required_tenant()
        self.logger.info(
            _("Iniciando verificação de autorização prévia"),
            extra={
                "tenant_id": tenant_id,
                "patient_id": task_variables.get("patient_id"),
                "coverage_id": task_variables.get("coverage_id"),
                "service_type": task_variables.get("service_type"),
            },
        )

        try:
            # Parse and validate input
            input_data = PreAuthCheckInput(**task_variables)

            # Check pre-authorization
            (
                pre_auth_required,
                auth_status,
                auth_details,
            ) = await self.pre_auth_checker.check_pre_authorization(
                patient_id=input_data.patient_id,
                coverage_id=input_data.coverage_id,
                service_type=input_data.service_type,
                procedure_codes=input_data.procedure_codes,
                specialty_code=input_data.specialty_code,
                practitioner_id=input_data.practitioner_id,
                proposed_date=input_data.proposed_date,
                estimated_cost=input_data.estimated_cost,
                tenant_id=tenant_id,
            )

            # Determine if action is required
            requires_action = pre_auth_required and auth_status not in ["approved", "not_required"]

            # Build action message
            action_message = None
            if requires_action:
                if auth_status == "pending":
                    action_message = _(
                        "Aguardando aprovação da autorização prévia pela operadora"
                    )
                elif auth_status == "denied":
                    action_message = _("Autorização prévia foi negada. Contatar operadora")
                else:
                    action_message = _("É necessário solicitar autorização prévia à operadora")

            # Build status message
            if not pre_auth_required:
                message = _("Autorização prévia não é necessária para este procedimento")
            elif auth_status == "approved":
                message = _(
                    "Autorização prévia aprovada: {number}"
                ).format(number=auth_details.authorization_number if auth_details else "N/A")
            elif auth_status == "pending":
                message = _("Autorização prévia pendente de aprovação")
            elif auth_status == "denied":
                message = _("Autorização prévia negada")
            else:
                message = _("Autorização prévia necessária. Solicitação pendente")

            # Build output
            output = PreAuthCheckOutput(
                pre_auth_required=pre_auth_required,
                authorization_status=auth_status,
                authorization_number=auth_details.authorization_number if auth_details else None,
                authorization_details=auth_details,
                requires_action=requires_action,
                action_message=action_message,
                message=message,
            )

            self.logger.info(
                _("Verificação de autorização concluída"),
                extra={
                    "tenant_id": tenant_id,
                    "pre_auth_required": pre_auth_required,
                    "authorization_status": auth_status,
                    "requires_action": requires_action,
                },
            )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                _("Erro ao verificar autorização prévia"),
                extra={
                    "tenant_id": tenant_id,
                    "patient_id": task_variables.get("patient_id"),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                message=_("Falha na verificação de autorização: {error}").format(error=str(e)),
                details={
                    "tenant_id": tenant_id,
                    "patient_id": task_variables.get("patient_id"),
                    "coverage_id": task_variables.get("coverage_id"),
                    "error": str(e),
                },
            ) from e
