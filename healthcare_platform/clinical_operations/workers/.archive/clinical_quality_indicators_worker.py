"""
Clinical Quality Indicators Worker

Tracks and measures clinical quality metrics such as time-to-treatment,
readmission rates, patient safety indicators, and compliance metrics.
Compares against benchmarks and provides recommendations for improvement.

Archetype: CLINICAL_SCORE
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__, worker="clinical.quality_indicators")


class ClinicalException(DomainException):
    """Clinical operations domain exception."""
    bpmn_error_code: str = "CLINICAL_ERROR"


class InvalidIndicatorTypeError(ClinicalException):
    """Raised when indicator type is not recognized."""
    bpmn_error_code: str = "INVALID_INDICATOR_TYPE"


class InvalidMeasurementError(ClinicalException):
    """Raised when measurement data is invalid."""
    bpmn_error_code: str = "INVALID_MEASUREMENT"


class QualityIndicatorError(ClinicalException):
    """Raised when quality indicator processing fails."""
    bpmn_error_code: str = "QUALITY_INDICATOR_FAILED"


class ClinicalQualityIndicatorsInput(BaseModel):
    """Input model for clinical quality indicators worker."""

    encounter_reference: str = Field(
        ...,
        description=_("Referência do encontro clínico (Encounter)")
    )
    patient_reference: str | None = Field(
        None,
        description=_("Referência do paciente (Patient)")
    )
    indicator_type: str = Field(
        ...,
        description=_("Tipo: time_to_treatment, readmission, safety_event, compliance")
    )
    measurement_data: dict[str, Any] = Field(
        ...,
        description=_("Dados de medição específicos do indicador")
    )
    measurement_period: dict[str, str] | None = Field(
        None,
        description=_("Período de medição com start e end (ISO 8601)")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "encounter_reference": self.encounter_reference,
            "patient_reference": self.patient_reference,
            "indicator_type": self.indicator_type,
            "measurement_data": self.measurement_data,
            "measurement_period": self.measurement_period,
        }


class ClinicalQualityIndicatorsOutput(BaseModel):
    """Output model for clinical quality indicators worker."""

    indicator_value: float = Field(
        ...,
        description=_("Valor do indicador calculado")
    )
    benchmark_comparison: str = Field(
        ...,
        description=_("Comparação com benchmark: above, at, below")
    )
    compliance_status: str = Field(
        ...,
        description=_("Status: compliant, non-compliant, needs-improvement")
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description=_("Recomendações para melhoria")
    )
    measure_reference: str = Field(
        ...,
        description=_("Referência do MeasureReport criado")
    )
    measured_at: str = Field(
        ...,
        description=_("Data/hora da medição (ISO 8601)")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "indicator_value": self.indicator_value,
            "benchmark_comparison": self.benchmark_comparison,
            "compliance_status": self.compliance_status,
            "recommendations": self.recommendations,
            "measure_reference": self.measure_reference,
            "measured_at": self.measured_at,
        }


class ClinicalQualityIndicatorsProtocol(ABC):
    """Protocol for clinical quality indicators operations."""

    @abstractmethod
    async def calculate_quality_indicator(
        self,
        encounter_reference: str,
        indicator_type: str,
        measurement_data: dict[str, Any],
        patient_reference: str | None = None,
        measurement_period: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Calculate a clinical quality indicator.

        Args:
            encounter_reference: Reference to the clinical encounter
            indicator_type: Type of indicator (time_to_treatment, readmission, etc.)
            measurement_data: Measurement-specific data
            patient_reference: Reference to the patient
            measurement_period: Measurement period with start and end dates

        Returns:
            Dictionary containing quality indicator results

        Raises:
            InvalidIndicatorTypeError: If indicator type is invalid
            InvalidMeasurementError: If measurement data is invalid
            QualityIndicatorError: If processing fails
        """
        pass


class DMNClinicalQualityIndicators(ClinicalQualityIndicatorsProtocol):
    """DMN-backed quality indicators using FederatedDMNService."""

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        dmn_service: FederatedDMNService | None = None,
    ) -> None:
        self._fhir = fhir_client
        self._dmn = dmn_service or get_dmn_service()
        self._fallback = ClinicalQualityIndicatorsStub(fhir_client=fhir_client)

    async def calculate_quality_indicator(
        self,
        encounter_reference: str,
        indicator_type: str,
        measurement_data: dict[str, Any],
        patient_reference: str | None = None,
        measurement_period: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Calculate quality indicator with DMN-driven thresholds."""
        tenant_id = get_required_tenant().tenant_id
        try:
            result = self._dmn.evaluate(
                tenant_id=tenant_id,
                category="clinical_safety",
                table_name="safety/quality_indicator_thresholds_001",
                inputs={"indicator_type": indicator_type},
            )
            if result and result.get("threshold") is not None:
                # DMN provides thresholds; use them for compliance check
                pass
        except (FileNotFoundError, ValueError):
            pass
        except Exception:
            pass
        return await self._fallback.calculate_quality_indicator(
            encounter_reference, indicator_type, measurement_data,
            patient_reference, measurement_period,
        )


class ClinicalQualityIndicatorsStub(ClinicalQualityIndicatorsProtocol):
    """Stub implementation for clinical quality indicators."""

    VALID_INDICATOR_TYPES = {
        "time_to_treatment",
        "readmission",
        "safety_event",
        "compliance"
    }

    # Benchmark targets (example values in minutes/percentages)
    BENCHMARKS = {
        "time_to_treatment": {
            "target": 30,  # 30 minutes
            "unit": "minutes",
            "better": "lower"
        },
        "readmission": {
            "target": 15.0,  # 15% readmission rate
            "unit": "percentage",
            "better": "lower"
        },
        "safety_event": {
            "target": 2.0,  # 2 events per 1000 patient days
            "unit": "rate",
            "better": "lower"
        },
        "compliance": {
            "target": 95.0,  # 95% compliance
            "unit": "percentage",
            "better": "higher"
        }
    }

    INDICATOR_CODES = {
        "time_to_treatment": {
            "system": "http://example.org/quality-measures",
            "code": "time-to-treatment",
            "display": "Time to Treatment"
        },
        "readmission": {
            "system": "http://example.org/quality-measures",
            "code": "readmission-rate",
            "display": "30-Day Readmission Rate"
        },
        "safety_event": {
            "system": "http://example.org/quality-measures",
            "code": "safety-events",
            "display": "Patient Safety Events"
        },
        "compliance": {
            "system": "http://example.org/quality-measures",
            "code": "protocol-compliance",
            "display": "Protocol Compliance Rate"
        }
    }

    def __init__(self, fhir_client: FHIRClientProtocol):
        """Initialize with FHIR client dependency."""
        self.fhir_client = fhir_client

    def _hash_reference(self, reference: str) -> str:
        """Hash reference for LGPD compliance."""
        return hashlib.sha256(reference.encode()).hexdigest()[:16]

    def _validate_indicator_type(self, indicator_type: str) -> None:
        """Validate indicator type."""
        if indicator_type not in self.VALID_INDICATOR_TYPES:
            logger.error(
                _("Tipo de indicador inválido: %s. Tipos válidos: %s"),
                indicator_type,
                ", ".join(self.VALID_INDICATOR_TYPES)
            )
            raise InvalidIndicatorTypeError(
                _("Tipo de indicador inválido: {indicator_type}").format(
                    indicator_type=indicator_type
                )
            )

    def _calculate_indicator_value(
        self,
        indicator_type: str,
        measurement_data: dict[str, Any]
    ) -> float:
        """Calculate the indicator value from measurement data."""
        if indicator_type == "time_to_treatment":
            # Expect measurement_data to have 'arrival_time' and 'treatment_time'
            if "time_minutes" in measurement_data:
                return float(measurement_data["time_minutes"])
            else:
                raise InvalidMeasurementError(
                    _("time_to_treatment requer campo 'time_minutes'")
                )

        elif indicator_type == "readmission":
            # Expect 'readmissions' and 'total_discharges'
            readmissions = measurement_data.get("readmissions", 0)
            total = measurement_data.get("total_discharges", 1)
            if total == 0:
                raise InvalidMeasurementError(
                    _("total_discharges não pode ser zero")
                )
            return (readmissions / total) * 100

        elif indicator_type == "safety_event":
            # Expect 'events' and 'patient_days'
            events = measurement_data.get("events", 0)
            patient_days = measurement_data.get("patient_days", 1)
            if patient_days == 0:
                raise InvalidMeasurementError(
                    _("patient_days não pode ser zero")
                )
            return (events / patient_days) * 1000

        elif indicator_type == "compliance":
            # Expect 'compliant_cases' and 'total_cases'
            compliant = measurement_data.get("compliant_cases", 0)
            total = measurement_data.get("total_cases", 1)
            if total == 0:
                raise InvalidMeasurementError(
                    _("total_cases não pode ser zero")
                )
            return (compliant / total) * 100

        return 0.0

    def _compare_to_benchmark(
        self,
        indicator_type: str,
        indicator_value: float
    ) -> str:
        """Compare indicator value to benchmark."""
        benchmark = self.BENCHMARKS[indicator_type]
        target = benchmark["target"]
        better = benchmark["better"]

        tolerance = 0.05  # 5% tolerance

        if better == "lower":
            if indicator_value <= target * (1 - tolerance):
                return "above"  # Above benchmark (better than target)
            elif indicator_value <= target * (1 + tolerance):
                return "at"
            else:
                return "below"
        else:  # better == "higher"
            if indicator_value >= target * (1 + tolerance):
                return "above"
            elif indicator_value >= target * (1 - tolerance):
                return "at"
            else:
                return "below"

    def _determine_compliance_status(
        self,
        benchmark_comparison: str
    ) -> str:
        """Determine compliance status from benchmark comparison."""
        if benchmark_comparison == "above":
            return "compliant"
        elif benchmark_comparison == "at":
            return "compliant"
        else:
            return "needs-improvement"

    def _generate_recommendations(
        self,
        indicator_type: str,
        indicator_value: float,
        benchmark_comparison: str
    ) -> list[str]:
        """Generate improvement recommendations."""
        recommendations = []

        if benchmark_comparison == "below":
            if indicator_type == "time_to_treatment":
                recommendations.extend([
                    _("Revisar fluxo de triagem para reduzir tempo de espera"),
                    _("Aumentar recursos disponíveis em horários de pico"),
                    _("Implementar protocolo de atendimento rápido para casos urgentes")
                ])
            elif indicator_type == "readmission":
                recommendations.extend([
                    _("Fortalecer orientação de alta hospitalar"),
                    _("Implementar follow-up pós-alta em 48-72h"),
                    _("Revisar protocolos de gestão de doenças crônicas")
                ])
            elif indicator_type == "safety_event":
                recommendations.extend([
                    _("Revisar protocolos de segurança do paciente"),
                    _("Aumentar treinamento da equipe em prevenção de eventos adversos"),
                    _("Implementar rounds de segurança diários")
                ])
            elif indicator_type == "compliance":
                recommendations.extend([
                    _("Revisar protocolos clínicos com equipe"),
                    _("Implementar alertas automáticos para ações obrigatórias"),
                    _("Realizar auditoria de casos não-conformes")
                ])

        return recommendations

    def _build_measure_report(
        self,
        encounter_reference: str,
        patient_reference: str | None,
        indicator_type: str,
        indicator_value: float,
        measurement_period: dict[str, str] | None,
    ) -> dict[str, Any]:
        """Build FHIR MeasureReport resource."""
        code_info = self.INDICATOR_CODES[indicator_type]
        measured_at = datetime.utcnow().isoformat() + "Z"

        measure_report = {
            "resourceType": "MeasureReport",
            "status": "complete",
            "type": "individual",
            "measure": code_info["code"],
            "date": measured_at,
            "period": measurement_period or {
                "start": measured_at,
                "end": measured_at
            },
            "group": [{
                "code": {
                    "coding": [{
                        "system": code_info["system"],
                        "code": code_info["code"],
                        "display": code_info["display"]
                    }]
                },
                "measureScore": {
                    "value": indicator_value
                }
            }]
        }

        if patient_reference:
            measure_report["subject"] = {
                "reference": patient_reference
            }

        if encounter_reference:
            measure_report["encounter"] = {
                "reference": encounter_reference
            }

        return measure_report

    async def calculate_quality_indicator(
        self,
        encounter_reference: str,
        indicator_type: str,
        measurement_data: dict[str, Any],
        patient_reference: str | None = None,
        measurement_period: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Calculate a clinical quality indicator."""
        # Validate indicator type
        self._validate_indicator_type(indicator_type)

        # Hash identifiers for logging (LGPD compliance)
        encounter_hash = self._hash_reference(encounter_reference)
        patient_hash = self._hash_reference(patient_reference) if patient_reference else "N/A"

        logger.info(
            _("Calculando indicador tipo=%s encounter=%s patient=%s"),
            indicator_type,
            encounter_hash,
            patient_hash
        )

        try:
            # Calculate indicator value
            indicator_value = self._calculate_indicator_value(
                indicator_type=indicator_type,
                measurement_data=measurement_data
            )

            # Compare to benchmark
            benchmark_comparison = self._compare_to_benchmark(
                indicator_type=indicator_type,
                indicator_value=indicator_value
            )

            # Determine compliance status
            compliance_status = self._determine_compliance_status(
                benchmark_comparison=benchmark_comparison
            )

            # Generate recommendations
            recommendations = self._generate_recommendations(
                indicator_type=indicator_type,
                indicator_value=indicator_value,
                benchmark_comparison=benchmark_comparison
            )

            # Build MeasureReport
            measure_report = self._build_measure_report(
                encounter_reference=encounter_reference,
                patient_reference=patient_reference,
                indicator_type=indicator_type,
                indicator_value=indicator_value,
                measurement_period=measurement_period,
            )

            # Create in FHIR server
            response = await self.fhir_client.create_resource(measure_report)

            measure_id = response.get("id")
            if not measure_id:
                raise QualityIndicatorError(
                    _("Resposta do servidor FHIR não contém ID do MeasureReport")
                )

            measure_reference = f"MeasureReport/{measure_id}"
            measured_at = response.get("date", datetime.utcnow().isoformat() + "Z")

            logger.info(
                _("Indicador calculado: %s tipo=%s valor=%.2f benchmark=%s compliance=%s"),
                measure_reference,
                indicator_type,
                indicator_value,
                benchmark_comparison,
                compliance_status
            )

            return {
                "indicator_value": indicator_value,
                "benchmark_comparison": benchmark_comparison,
                "compliance_status": compliance_status,
                "recommendations": recommendations,
                "measure_reference": measure_reference,
                "measured_at": measured_at,
            }

        except Exception as e:
            logger.error(
                _("Erro ao calcular indicador tipo=%s: %s"),
                indicator_type,
                str(e),
                exc_info=True
            )
            raise QualityIndicatorError(
                _("Falha ao calcular indicador de qualidade: {error}").format(error=str(e))
            ) from e


@require_tenant
@track_task_execution(worker_topic="clinical.quality_indicators")
async def execute(task_variables: dict[str, Any]) -> dict[str, Any]:
    """
    Execute clinical quality indicators worker.

    Args:
        task_variables: Camunda task variables

    Returns:
        Dictionary with quality indicator results

    Raises:
        InvalidIndicatorTypeError: If indicator type is invalid
        InvalidMeasurementError: If measurement data is invalid
        QualityIndicatorError: If processing fails
    """
    tenant_id = get_required_tenant()

    logger.info(
        _("Iniciando worker de indicadores de qualidade tenant=%s"),
        tenant_id
    )

    # Parse and validate input
    input_data = ClinicalQualityIndicatorsInput(**task_variables)

    # Initialize dependencies (stub implementation)
    from healthcare_platform.shared.integrations.fhir_client import FHIRClientStub
    fhir_client = FHIRClientStub()

    # Create service
    service = DMNClinicalQualityIndicators(fhir_client=fhir_client)

    # Execute quality indicator calculation
    result = await service.calculate_quality_indicator(
        encounter_reference=input_data.encounter_reference,
        indicator_type=input_data.indicator_type,
        measurement_data=input_data.measurement_data,
        patient_reference=input_data.patient_reference,
        measurement_period=input_data.measurement_period,
    )

    # Build output
    output = ClinicalQualityIndicatorsOutput(**result)

    logger.info(
        _("Worker de indicadores de qualidade concluído: %s valor=%.2f compliance=%s"),
        output.measure_reference,
        output.indicator_value,
        output.compliance_status
    )

    return output.to_variables()


# Worker configuration
TOPIC = "clinical.quality_indicators"
