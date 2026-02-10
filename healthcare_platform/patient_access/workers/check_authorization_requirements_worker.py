"""
Check Authorization Requirements Worker

CIB7 External Task Topic: patient.check_authorization
BPMN Error Code: PATIENT_ACCESS_ERROR

Checks if procedure/service requires pre-authorization.
Validates against ANS rules and operator-specific rules.
"""

from __future__ import annotations

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

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.bpmn_error_code = "PATIENT_ACCESS_ERROR"


class CheckAuthorizationRequirementsInput(BaseModel):
    """Input model for checking authorization requirements."""

    procedure_code: str = Field(..., description="Código do procedimento (TUSS)")
    service_type: str = Field(..., description="Tipo de serviço")
    operator_code: str = Field(..., description="Código da operadora ANS")
    plan_code: str = Field(..., description="Código do plano")
    coverage_reference: str | None = Field(
        None, description="Referência FHIR da cobertura"
    )


class CheckAuthorizationRequirementsOutput(BaseModel):
    """Output model for checking authorization requirements."""

    requires_authorization: bool = Field(
        ..., description="Se requer autorização prévia"
    )
    authorization_type: str = Field(
        ..., description="Tipo de autorização (prior/concurrent/none)"
    )
    authorization_criteria: list[str] = Field(
        default_factory=list, description="Critérios para autorização"
    )
    estimated_approval_time: str | None = Field(
        None, description="Tempo estimado para aprovação"
    )


class AuthorizationRequirementChecker(ABC):
    """Protocol for checking authorization requirements."""

    @abstractmethod
    async def check_ans_rules(self, procedure_code: str) -> dict[str, Any]:
        """Check ANS rules for procedure."""
        pass

    @abstractmethod
    async def check_operator_rules(
        self, operator_code: str, plan_code: str, procedure_code: str
    ) -> dict[str, Any]:
        """Check operator-specific rules."""
        pass

    @abstractmethod
    async def get_authorization_criteria(
        self, procedure_code: str, service_type: str
    ) -> list[str]:
        """Get authorization criteria for procedure."""
        pass


class StubAuthorizationRequirementChecker(AuthorizationRequirementChecker):
    """Stub implementation with DMN integration."""

    # High-complexity procedures requiring authorization
    HIGH_COMPLEXITY_PROCEDURES = [
        "40101010",  # Cirurgia cardíaca
        "40201010",  # Neurocirurgia
        "40301010",  # Transplante
        "30701011",  # Ressonância magnética
        "30702011",  # Tomografia computadorizada
    ]

    def __init__(self):
        self.dmn_service = FederatedDMNService()

    async def check_ans_rules(self, procedure_code: str) -> dict[str, Any]:
        """Check ANS rules for procedure using DMN."""
        tenant_id = get_required_tenant()

        try:
            result = self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category='authorization',
                table_name='auth_urgency_001',
                inputs={'procedure_code': procedure_code}
            )
            return result
        except (FileNotFoundError, ValueError):
            # Fallback to hardcoded logic if DMN not available
            requires_auth = procedure_code in self.HIGH_COMPLEXITY_PROCEDURES

            return {
                "requires_authorization": requires_auth,
                "authorization_type": "prior" if requires_auth else "none",
                "ans_rule": (
                    "RN 428 - Procedimento de alta complexidade"
                    if requires_auth
                    else "Procedimento não requer autorização"
                ),
            }

    async def check_operator_rules(
        self, operator_code: str, plan_code: str, procedure_code: str
    ) -> dict[str, Any]:
        """Check operator-specific rules."""
        # Stub: operators may have additional rules
        return {
            "operator_requires_auth": False,
            "operator_rule": "Sem regras adicionais",
            "estimated_approval_time": "24-48h" if procedure_code in self.HIGH_COMPLEXITY_PROCEDURES else None,
        }

    async def get_authorization_criteria(
        self, procedure_code: str, service_type: str
    ) -> list[str]:
        """Get authorization criteria for procedure using DMN."""
        tenant_id = get_required_tenant()

        try:
            result = self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category='authorization',
                table_name='auth_documentation_001',
                inputs={
                    'procedure_code': procedure_code,
                    'service_type': service_type
                }
            )
            # Extract criteria from DMN result
            criteria = result.get('criteria', [])
            if isinstance(criteria, str):
                criteria = [criteria]
            return criteria
        except (FileNotFoundError, ValueError):
            # Fallback to hardcoded logic
            if procedure_code in self.HIGH_COMPLEXITY_PROCEDURES:
                return [
                    _("Laudo médico detalhado"),
                    _("Justificativa clínica"),
                    _("Exames complementares"),
                    _("CID-10 do diagnóstico"),
                ]
            return []


class CheckAuthorizationRequirementsWorker:
    """Worker for checking authorization requirements."""

    TOPIC = "patient.check_authorization"

    def __init__(
        self, checker: AuthorizationRequirementChecker | None = None
    ):
        """Initialize worker with checker."""
        self.checker = checker or StubAuthorizationRequirementChecker()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(task_type="patient.check_authorization")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute authorization requirements check.

        Args:
            task_variables: Task variables containing procedure and coverage data

        Returns:
            Authorization requirements result

        Raises:
            PatientAccessException: If check fails
        """
        tenant_id = get_required_tenant()
        self.logger.info(
            "Verificando requisitos de autorização",
            extra={"tenant_id": tenant_id, "task_variables": task_variables},
        )

        try:
            # Parse input
            input_data = CheckAuthorizationRequirementsInput(**task_variables)

            # Check ANS rules
            self.logger.info(
                "Verificando regras ANS",
                extra={
                    "tenant_id": tenant_id,
                    "procedure_code": input_data.procedure_code,
                },
            )

            ans_result = await self.checker.check_ans_rules(input_data.procedure_code)

            requires_authorization = ans_result.get("requires_authorization", False)
            authorization_type = ans_result.get("authorization_type", "none")

            self.logger.info(
                "Regras ANS verificadas",
                extra={
                    "tenant_id": tenant_id,
                    "requires_authorization": requires_authorization,
                    "ans_rule": ans_result.get("ans_rule"),
                },
            )

            # Check operator-specific rules
            self.logger.info(
                "Verificando regras da operadora",
                extra={
                    "tenant_id": tenant_id,
                    "operator_code": input_data.operator_code,
                    "plan_code": input_data.plan_code,
                },
            )

            operator_result = await self.checker.check_operator_rules(
                input_data.operator_code,
                input_data.plan_code,
                input_data.procedure_code,
            )

            # Combine results
            if operator_result.get("operator_requires_auth", False):
                requires_authorization = True
                authorization_type = "prior"

            estimated_approval_time = operator_result.get("estimated_approval_time")

            # Get authorization criteria
            authorization_criteria = []
            if requires_authorization:
                authorization_criteria = await self.checker.get_authorization_criteria(
                    input_data.procedure_code, input_data.service_type
                )

            self.logger.info(
                "Requisitos de autorização determinados",
                extra={
                    "tenant_id": tenant_id,
                    "requires_authorization": requires_authorization,
                    "authorization_type": authorization_type,
                    "criteria_count": len(authorization_criteria),
                },
            )

            output = CheckAuthorizationRequirementsOutput(
                requires_authorization=requires_authorization,
                authorization_type=authorization_type,
                authorization_criteria=authorization_criteria,
                estimated_approval_time=estimated_approval_time,
            )

            return output.model_dump()

        except Exception as e:
            self.logger.error(
                "Erro ao verificar requisitos de autorização",
                extra={"tenant_id": tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise PatientAccessException(
                _("Erro ao verificar requisitos de autorização: {error}").format(
                    error=str(e)
                ),
                details={"original_error": str(e)},
            )
