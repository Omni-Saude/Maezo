"""Calculate Estimated Duration Worker - Patient Access Domain.

CIB7 External Task Topic: scheduling.calculate_duration
BPMN Error Code: PATIENT_ACCESS_ERROR

Estimates appointment duration based on service type, specialty, and historical data.
Uses pattern analysis to provide accurate time estimates for resource planning.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
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


class DurationCalculationInput(BaseModel):
    """Input for duration calculation."""

    service_type: str = Field(..., description="Service type code")
    specialty_code: str = Field(..., description="Medical specialty code")
    patient_id: str | None = Field(None, description="Optional patient for history analysis")
    practitioner_id: str | None = Field(None, description="Optional practitioner for patterns")
    procedure_codes: list[str] = Field(default_factory=list, description="Procedure codes")
    complexity_level: str = Field("medium", description="Complexity: low, medium, high")
    is_first_visit: bool = Field(False, description="First visit typically takes longer")


class DurationBreakdown(BaseModel):
    """Detailed duration breakdown."""

    base_duration_minutes: int = Field(..., description="Base duration for service type")
    specialty_adjustment_minutes: int = Field(0, description="Specialty-specific adjustment")
    complexity_adjustment_minutes: int = Field(0, description="Complexity adjustment")
    first_visit_adjustment_minutes: int = Field(0, description="First visit adjustment")
    procedure_adjustment_minutes: int = Field(0, description="Procedure-specific adjustment")
    buffer_minutes: int = Field(5, description="Buffer for overruns")


class DurationCalculationOutput(BaseModel):
    """Output from duration calculation."""

    estimated_duration_minutes: int = Field(..., description="Total estimated duration")
    breakdown: DurationBreakdown = Field(..., description="Detailed breakdown")
    confidence_level: str = Field("medium", description="Confidence: low, medium, high")
    recommended_buffer_minutes: int = Field(5, description="Recommended time buffer")
    based_on_historical_data: bool = Field(False, description="Based on historical patterns")
    message: str = Field("", description="Explanation message")


class DurationCalculator(ABC):
    """Protocol for calculating appointment duration."""

    @abstractmethod
    async def calculate_duration(
        self,
        service_type: str,
        specialty_code: str,
        patient_id: str | None = None,
        practitioner_id: str | None = None,
        procedure_codes: list[str] | None = None,
        complexity_level: str = "medium",
        is_first_visit: bool = False,
        tenant_id: str | None = None,
    ) -> tuple[int, DurationBreakdown, str]:
        """Calculate estimated appointment duration.

        Args:
            service_type: Service type code
            specialty_code: Medical specialty code
            patient_id: Optional patient for history analysis
            practitioner_id: Optional practitioner for patterns
            procedure_codes: Optional procedure codes
            complexity_level: Complexity level (low/medium/high)
            is_first_visit: Whether this is first visit
            tenant_id: Tenant identifier

        Returns:
            Tuple of (estimated_minutes, breakdown, confidence_level)

        Raises:
            PatientAccessException: If calculation fails
        """
        ...


class StubDurationCalculator(DurationCalculator):
    """Stub implementation for testing."""

    def __init__(self):
        self.dmn_service = FederatedDMNService()
        # DMN integration point: auth_timing_005
        # Inputs: {'service_type': service_type, 'specialty_code': specialty_code}
        # Call: self.dmn_service.evaluate(tenant_id=..., category='authorization', table_name='auth_timing_005', inputs={...})


    # Base durations by service type (minutes)
    BASE_DURATIONS = {
        "consulta": 30,
        "exame_simples": 15,
        "exame_complexo": 45,
        "cirurgia": 120,
        "procedimento": 60,
        "urgencia": 20,
        "retorno": 20,
    }

    # Specialty adjustments (additional minutes)
    SPECIALTY_ADJUSTMENTS = {
        "cardiologia": 10,
        "clinica_geral": 0,
        "ortopedia": 15,
        "pediatria": 5,
        "ginecologia": 10,
        "neurologia": 15,
        "psiquiatria": 20,
    }

    # Complexity adjustments
    COMPLEXITY_ADJUSTMENTS = {
        "low": -5,
        "medium": 0,
        "high": 10,
    }

    async def calculate_duration(
        self,
        service_type: str,
        specialty_code: str,
        patient_id: str | None = None,
        practitioner_id: str | None = None,
        procedure_codes: list[str] | None = None,
        complexity_level: str = "medium",
        is_first_visit: bool = False,
        tenant_id: str | None = None,
    ) -> tuple[int, DurationBreakdown, str]:
        """Calculate duration using stub logic."""
        # Get base duration
        base_duration = self.BASE_DURATIONS.get(service_type, 30)

        # Get specialty adjustment
        specialty_adjustment = self.SPECIALTY_ADJUSTMENTS.get(specialty_code, 0)

        # Get complexity adjustment
        complexity_adjustment = self.COMPLEXITY_ADJUSTMENTS.get(complexity_level, 0)

        # First visit typically takes longer
        first_visit_adjustment = 10 if is_first_visit else 0

        # Procedure adjustments (stub: +5 minutes per procedure)
        procedure_adjustment = len(procedure_codes or []) * 5

        # Standard buffer
        buffer = 5

        # Calculate total
        total_duration = (
            base_duration
            + specialty_adjustment
            + complexity_adjustment
            + first_visit_adjustment
            + procedure_adjustment
            + buffer
        )

        # Build breakdown
        breakdown = DurationBreakdown(
            base_duration_minutes=base_duration,
            specialty_adjustment_minutes=specialty_adjustment,
            complexity_adjustment_minutes=complexity_adjustment,
            first_visit_adjustment_minutes=first_visit_adjustment,
            procedure_adjustment_minutes=procedure_adjustment,
            buffer_minutes=buffer,
        )

        # Determine confidence
        # In real implementation, would base on historical data availability
        if patient_id and practitioner_id:
            confidence = "high"
        elif patient_id or practitioner_id:
            confidence = "medium"
        else:
            confidence = "low"

        return total_duration, breakdown, confidence


class CalculateEstimatedDurationWorker:
    """Worker for calculating appointment duration.

    Estimates appointment duration based on service type, specialty,
    complexity, and historical patterns to support accurate scheduling.
    """

    TOPIC = "scheduling.calculate_duration"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol | None = None,
        duration_calculator: DurationCalculator | None = None,
    ) -> None:
        """Initialize worker with dependencies.

        Args:
            fhir_client: FHIR client for historical data access
            duration_calculator: Duration calculator implementation
        """
        self.fhir_client = fhir_client
        self.duration_calculator = duration_calculator or StubDurationCalculator()
        self.logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute duration calculation task.

        Args:
            task_variables: Task variables from Camunda

        Returns:
            Dictionary with estimated duration and breakdown

        Raises:
            PatientAccessException: If calculation fails
        """
        tenant_id = get_required_tenant()
        self.logger.info(
            _("Iniciando cálculo de duração estimada"),
            extra={
                "tenant_id": tenant_id,
                "service_type": task_variables.get("service_type"),
                "specialty_code": task_variables.get("specialty_code"),
            },
        )

        try:
            # Parse and validate input
            input_data = DurationCalculationInput(**task_variables)

            # Calculate duration
            (
                estimated_minutes,
                breakdown,
                confidence_level,
            ) = await self.duration_calculator.calculate_duration(
                service_type=input_data.service_type,
                specialty_code=input_data.specialty_code,
                patient_id=input_data.patient_id,
                practitioner_id=input_data.practitioner_id,
                procedure_codes=input_data.procedure_codes,
                complexity_level=input_data.complexity_level,
                is_first_visit=input_data.is_first_visit,
                tenant_id=tenant_id,
            )

            # Build explanation message
            message = _(
                "Duração estimada de {duration} minutos baseada em {service_type} para {specialty}"
            ).format(
                duration=estimated_minutes,
                service_type=input_data.service_type,
                specialty=input_data.specialty_code,
            )

            if input_data.is_first_visit:
                message += _(" (primeira visita)")

            # Build output
            output = DurationCalculationOutput(
                estimated_duration_minutes=estimated_minutes,
                breakdown=breakdown,
                confidence_level=confidence_level,
                recommended_buffer_minutes=breakdown.buffer_minutes,
                based_on_historical_data=(
                    input_data.patient_id is not None or input_data.practitioner_id is not None
                ),
                message=message,
            )

            self.logger.info(
                _("Duração calculada"),
                extra={
                    "tenant_id": tenant_id,
                    "estimated_minutes": estimated_minutes,
                    "confidence_level": confidence_level,
                    "service_type": input_data.service_type,
                    "specialty_code": input_data.specialty_code,
                },
            )

            return output.model_dump(mode="json")

        except PatientAccessException:
            raise
        except Exception as e:
            self.logger.error(
                _("Erro ao calcular duração estimada"),
                extra={
                    "tenant_id": tenant_id,
                    "service_type": task_variables.get("service_type"),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PatientAccessException(
                message=_("Falha no cálculo de duração: {error}").format(error=str(e)),
                details={
                    "tenant_id": tenant_id,
                    "service_type": task_variables.get("service_type"),
                    "specialty_code": task_variables.get("specialty_code"),
                    "error": str(e),
                },
            ) from e
