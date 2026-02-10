"""Validate Appointment Rules Worker - Patient Access Domain.

CIB7 External Task Topic: scheduling.validate_rules
BPMN Error Code: PATIENT_ACCESS_ERROR

Validates business rules for appointment scheduling including minimum intervals,
maximum appointments per day, and specialty-specific constraints.
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


class AppointmentRulesInput(BaseModel):
    """Input for appointment rules validation."""

    patient_id: str = Field(..., description="FHIR Patient reference")
    practitioner_id: str = Field(..., description="FHIR Practitioner reference")
    specialty_code: str = Field(..., description="Medical specialty code")
    proposed_datetime: datetime = Field(..., description="Proposed appointment datetime")
    service_type: str = Field(..., description="Service type code")
    duration_minutes: int = Field(30, description="Appointment duration in minutes")


class RuleViolation(BaseModel):
    """Rule violation details."""

    rule_code: str = Field(..., description="Rule identifier")
    rule_name: str = Field(..., description="Rule name")
    violation_message: str = Field(..., description="Violation description")
    severity: str = Field("ERROR", description="Severity: ERROR, WARNING, INFO")


class AppointmentRulesOutput(BaseModel):
    """Output from appointment rules validation."""

    is_valid: bool = Field(..., description="Overall validation result")
    violations: list[RuleViolation] = Field(default_factory=list)
    warnings: list[RuleViolation] = Field(default_factory=list)
    validation_timestamp: datetime = Field(default_factory=datetime.utcnow)
    message: str = Field("", description="Summary message")


class AppointmentRulesValidator(ABC):
    """Protocol for validating appointment rules."""

    @abstractmethod
    async def validate_rules(
        self,
        patient_id: str,
        practitioner_id: str,
        specialty_code: str,
        proposed_datetime: datetime,
        service_type: str,
        duration_minutes: int,
        tenant_id: str | None = None,
    ) -> tuple[bool, list[RuleViolation], list[RuleViolation]]:
        """Validate appointment business rules.

        Args:
            patient_id: FHIR Patient reference
            practitioner_id: FHIR Practitioner reference
            specialty_code: Medical specialty code
            proposed_datetime: Proposed appointment datetime
            service_type: Service type code
            duration_minutes: Appointment duration in minutes
            tenant_id: Tenant identifier

        Returns:
            Tuple of (is_valid, violations, warnings)

        Raises:
            PatientAccessException: If validation fails
        """
        ...


class StubAppointmentRulesValidator(AppointmentRulesValidator):
    """Stub implementation for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()

    SPECIALTY_MIN_INTERVALS = {
        "cardiologia": 30,
        "clinica_geral": 15,
        "ortopedia": 30,
        "pediatria": 20,
        "ginecologia": 30,
    }

    MAX_APPOINTMENTS_PER_DAY = {
        "cardiologia": 12,
        "clinica_geral": 20,
        "ortopedia": 10,
        "pediatria": 16,
        "ginecologia": 12,
    }

    async def validate_rules(
        self,
        patient_id: str,
        practitioner_id: str,
        specialty_code: str,
        proposed_datetime: datetime,
        service_type: str,
        duration_minutes: int,
        tenant_id: str | None = None,
    ) -> tuple[bool, list[RuleViolation], list[RuleViolation]]:
        """Validate appointment rules using DMN."""
        violations: list[RuleViolation] = []
        warnings: list[RuleViolation] = []

        # Try DMN evaluation for timing and scope rules
        try:
            timing_result = self.dmn_service.evaluate(
                tenant_id=tenant_id or get_required_tenant(),
                category='authorization',
                table_name='auth_timing_003',
                inputs={
                    'service_type': service_type,
                    'specialty_code': specialty_code,
                    'proposed_datetime': proposed_datetime.isoformat(),
                    'duration_minutes': duration_minutes
                }
            )
            # Extract violations from DMN result
            dmn_violations = timing_result.get('violations', [])
            for v in dmn_violations:
                violations.append(RuleViolation(**v))

            # Try scope validation
            scope_result = self.dmn_service.evaluate(
                tenant_id=tenant_id or get_required_tenant(),
                category='authorization',
                table_name='auth_scope_003',
                inputs={
                    'practitioner_id': practitioner_id,
                    'specialty_code': specialty_code,
                    'service_type': service_type
                }
            )
            dmn_warnings = scope_result.get('warnings', [])
            for w in dmn_warnings:
                warnings.append(RuleViolation(**w))

            # If DMN provided violations, return early
            if violations or dmn_violations:
                return len(violations) == 0, violations, warnings
        except (FileNotFoundError, ValueError):
            # Fallback to hardcoded validation
            pass

        # Rule 1: Check minimum interval for specialty
        min_interval = self.SPECIALTY_MIN_INTERVALS.get(specialty_code, 15)
        if duration_minutes < min_interval:
            violations.append(
                RuleViolation(
                    rule_code="MIN_INTERVAL",
                    rule_name=_("Intervalo mínimo entre consultas"),
                    violation_message=_(
                        "Duração de {duration} min é menor que o mínimo de {min_interval} min para {specialty}"
                    ).format(
                        duration=duration_minutes,
                        min_interval=min_interval,
                        specialty=specialty_code,
                    ),
                    severity="ERROR",
                )
            )

        # Rule 2: Check business hours (8:00 - 18:00)
        if proposed_datetime.hour < 8 or proposed_datetime.hour >= 18:
            violations.append(
                RuleViolation(
                    rule_code="BUSINESS_HOURS",
                    rule_name=_("Horário comercial"),
                    violation_message=_("Agendamento fora do horário comercial (8:00-18:00)"),
                    severity="ERROR",
                )
            )

        # Rule 3: Check weekend scheduling
        if proposed_datetime.weekday() >= 5:  # Saturday = 5, Sunday = 6
            warnings.append(
                RuleViolation(
                    rule_code="WEEKEND_APPOINTMENT",
                    rule_name=_("Agendamento em fim de semana"),
                    violation_message=_("Agendamento proposto para fim de semana"),
                    severity="WARNING",
                )
            )

        # Rule 4: Check max appointments per day (stub assumes under limit)
        max_daily = self.MAX_APPOINTMENTS_PER_DAY.get(specialty_code, 15)
        # In real implementation, would query existing appointments
        # Stub assumes valid

        # Rule 5: Check advance booking (at least 1 hour in future)
        from datetime import timedelta

        min_advance = datetime.utcnow() + timedelta(hours=1)
        if proposed_datetime < min_advance:
            violations.append(
                RuleViolation(
                    rule_code="MIN_ADVANCE_BOOKING",
                    rule_name=_("Antecedência mínima"),
                    violation_message=_("Agendamento deve ser feito com pelo menos 1 hora de antecedência"),
                    severity="ERROR",
                )
            )

        is_valid = len(violations) == 0

        return is_valid, violations, warnings


class ValidateAppointmentRulesWorker:
    """Worker for validating appointment business rules.

    Validates constraints such as minimum intervals between appointments,
    maximum appointments per day, specialty-specific rules, and business hours.
    """

    TOPIC = "scheduling.validate_rules"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol | None = None,
        rules_validator: AppointmentRulesValidator | None = None,
    ) -> None:
        """Initialize worker with dependencies.

        Args:
            fhir_client: FHIR client for resource access
            rules_validator: Rules validator implementation
        """
        self.fhir_client = fhir_client
        self.rules_validator = rules_validator or StubAppointmentRulesValidator()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute appointment rules validation task.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with validation results and violations

        Raises:
            PatientAccessException: If validation execution fails
        """
        tenant_id = get_required_tenant()
        self.logger.info(
            _("Iniciando validação de regras de agendamento"),
            extra={
                "tenant_id": tenant_id,
                "patient_id": task_variables.get("patient_id"),
                "practitioner_id": task_variables.get("practitioner_id"),
            },
        )

        try:
            # Parse and validate input
            input_data = AppointmentRulesInput(**task_variables)

            # Validate rules
            is_valid, violations, warnings = await self.rules_validator.validate_rules(
                patient_id=input_data.patient_id,
                practitioner_id=input_data.practitioner_id,
                specialty_code=input_data.specialty_code,
                proposed_datetime=input_data.proposed_datetime,
                service_type=input_data.service_type,
                duration_minutes=input_data.duration_minutes,
                tenant_id=tenant_id,
            )

            # Build output
            if is_valid:
                message = _("Todas as regras de agendamento foram validadas com sucesso")
            else:
                message = _("Foram encontradas {count} violações de regras").format(
                    count=len(violations)
                )

            output = AppointmentRulesOutput(
                is_valid=is_valid,
                violations=violations,
                warnings=warnings,
                message=message,
            )

            self.logger.info(
                _("Validação de regras concluída"),
                extra={
                    "tenant_id": tenant_id,
                    "is_valid": is_valid,
                    "violations_count": len(violations),
                    "warnings_count": len(warnings),
                },
            )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                _("Erro ao validar regras de agendamento"),
                extra={"tenant_id": tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise PatientAccessException(
                message=_("Falha na validação de regras: {error}").format(error=str(e)),
                details={
                    "tenant_id": tenant_id,
                    "patient_id": task_variables.get("patient_id"),
                    "error": str(e),
                },
            ) from e
