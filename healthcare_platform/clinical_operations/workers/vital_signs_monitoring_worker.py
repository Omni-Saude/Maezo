"""Monitor vital signs and generate clinical alerts.

CIB7 External Task Topic: clinical.vital_signs
BPMN Error Codes: CLINICAL_ERROR
"""
from __future__ import annotations

from abc import ABC, abstractmethod
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


# ── Constants & Validation ────────────────────────────────────────────


class ClinicalException(DomainException):
    """Exception for clinical operations."""

    bpmn_error_code: str = "CLINICAL_ERROR"


# Normal vital signs ranges (adult)
NORMAL_RANGES = {
    "temperature_celsius": (36.0, 37.5),
    "systolic_bp": (90, 140),
    "diastolic_bp": (60, 90),
    "heart_rate": (60, 100),
    "respiratory_rate": (12, 20),
    "oxygen_saturation": (95, 100),
}


# ── Data Transfer Objects ─────────────────────────────────────────────


class VitalSignAlert(BaseModel):
    """Vital sign alert."""

    parameter: str = Field(..., description="Vital sign parameter name")
    value: float = Field(..., description="Measured value")
    normal_range: str = Field(..., description="Normal range for this parameter")
    severity: str = Field(..., description="Alert severity (INFO/WARNING/CRITICAL)")
    message: str = Field(..., description="Alert message")


class VitalSignsMonitoringInput(BaseModel):
    """Input variables for vital signs monitoring."""

    encounter_reference: str = Field(..., description="FHIR Encounter reference")
    patient_reference: str = Field(..., description="FHIR Patient reference")
    vital_signs: dict[str, Any] = Field(
        default_factory=dict, description="Vital signs measurements"
    )
    tenant_id: str = Field(default="")


class VitalSignsMonitoringOutput(BaseModel):
    """Output variables for vital signs monitoring."""

    vital_signs_status: str
    alerts: list[dict[str, Any]]
    severity_level: str
    requires_immediate_attention: bool

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "vital_signs_status": self.vital_signs_status,
            "alerts": self.alerts,
            "severity_level": self.severity_level,
            "requires_immediate_attention": self.requires_immediate_attention,
        }


# ── Protocol ──────────────────────────────────────────────────────────


class VitalSignsAnalyzer(ABC):
    """Protocol for vital signs analysis engines."""

    @abstractmethod
    def analyze(
        self,
        vital_signs: dict[str, Any],
        patient_age: int | None,
    ) -> list[VitalSignAlert]:
        """Analyze vital signs and generate alerts.

        Args:
            vital_signs: Dictionary of vital sign measurements
            patient_age: Patient age in years

        Returns:
            List of alerts for abnormal values
        """
        ...


# ── Stub Implementation ──────────────────────────────────────────────


class DMNVitalSignsAnalyzer(VitalSignsAnalyzer):
    """DMN-backed vital signs analyzer using FederatedDMNService."""

    _VITAL_SIGN_TABLES = {
        "temperature_celsius": "vit/temperature/vit_temperature_001",
        "systolic_bp": "vit/blood_pressure/vit_bp_systolic_001",
        "diastolic_bp": "vit/blood_pressure/vit_bp_diastolic_001",
        "heart_rate": "vit/heart_rate/vit_hr_001",
        "respiratory_rate": "vit/respiratory/vit_rr_001",
        "oxygen_saturation": "vit/spo2/vit_spo2_001",
    }

    def __init__(self, dmn_service: FederatedDMNService | None = None) -> None:
        self._dmn = dmn_service or get_dmn_service()
        self._logger = get_logger(__name__, component="dmn_vitals")
        self._fallback = StubVitalSignsAnalyzer()

    def analyze(
        self,
        vital_signs: dict[str, Any],
        patient_age: int | None,
    ) -> list[VitalSignAlert]:
        """Analyze vital signs via DMN decision tables."""
        alerts: list[VitalSignAlert] = []
        tenant_id = get_required_tenant().tenant_id
        dmn_hit = False

        for param, table_name in self._VITAL_SIGN_TABLES.items():
            value = vital_signs.get(param)
            if value is None:
                continue
            try:
                inputs: dict[str, Any] = {"value": float(value)}
                if patient_age is not None:
                    inputs["patient_age"] = patient_age
                result = self._dmn.evaluate(
                    tenant_id=tenant_id,
                    category="clinical_safety",
                    table_name=table_name,
                    inputs=inputs,
                )
                if result and result.get("severity"):
                    dmn_hit = True
                    alerts.append(
                        VitalSignAlert(
                            parameter=param,
                            value=float(value),
                            normal_range=result.get("normal_range", ""),
                            severity=result.get("severity", "WARNING"),
                            message=result.get("message", f"{param} anormal"),
                        )
                    )
            except (FileNotFoundError, ValueError):
                continue
            except Exception as exc:
                self._logger.warning(
                    "dmn_vitals_check_error",
                    parameter=param, error=str(exc),
                )

        if not dmn_hit:
            return self._fallback.analyze(vital_signs, patient_age)
        return alerts


class StubVitalSignsAnalyzer(VitalSignsAnalyzer):
    """Range-based vital signs analyzer for development/testing.

    Compares vital signs against normal ranges and generates alerts
    for values outside acceptable thresholds.
    """

    def analyze(
        self,
        vital_signs: dict[str, Any],
        patient_age: int | None,
    ) -> list[VitalSignAlert]:
        """Analyze using normal range thresholds."""
        alerts: list[VitalSignAlert] = []

        # Temperature
        temp = vital_signs.get("temperature_celsius")
        if temp is not None:
            temp = float(temp)
            min_temp, max_temp = NORMAL_RANGES["temperature_celsius"]
            if temp < min_temp:
                severity = "CRITICAL" if temp < 35.0 else "WARNING"
                alerts.append(
                    VitalSignAlert(
                        parameter="temperature_celsius",
                        value=temp,
                        normal_range=f"{min_temp}-{max_temp}°C",
                        severity=severity,
                        message=_(
                            "Hipotermia detectada: {value}°C (normal: {range})"
                        ).format(value=temp, range=f"{min_temp}-{max_temp}°C"),
                    )
                )
            elif temp > max_temp:
                severity = "CRITICAL" if temp > 39.0 else "WARNING"
                alerts.append(
                    VitalSignAlert(
                        parameter="temperature_celsius",
                        value=temp,
                        normal_range=f"{min_temp}-{max_temp}°C",
                        severity=severity,
                        message=_(
                            "Febre detectada: {value}°C (normal: {range})"
                        ).format(value=temp, range=f"{min_temp}-{max_temp}°C"),
                    )
                )

        # Blood Pressure - Systolic
        systolic = vital_signs.get("systolic_bp")
        if systolic is not None:
            systolic = int(systolic)
            min_bp, max_bp = NORMAL_RANGES["systolic_bp"]
            if systolic < min_bp:
                severity = "CRITICAL" if systolic < 80 else "WARNING"
                alerts.append(
                    VitalSignAlert(
                        parameter="systolic_bp",
                        value=systolic,
                        normal_range=f"{min_bp}-{max_bp} mmHg",
                        severity=severity,
                        message=_(
                            "Hipotensão arterial: {value} mmHg (normal: {range})"
                        ).format(value=systolic, range=f"{min_bp}-{max_bp} mmHg"),
                    )
                )
            elif systolic > max_bp:
                severity = "CRITICAL" if systolic > 180 else "WARNING"
                alerts.append(
                    VitalSignAlert(
                        parameter="systolic_bp",
                        value=systolic,
                        normal_range=f"{min_bp}-{max_bp} mmHg",
                        severity=severity,
                        message=_(
                            "Hipertensão arterial: {value} mmHg (normal: {range})"
                        ).format(value=systolic, range=f"{min_bp}-{max_bp} mmHg"),
                    )
                )

        # Blood Pressure - Diastolic
        diastolic = vital_signs.get("diastolic_bp")
        if diastolic is not None:
            diastolic = int(diastolic)
            min_bp, max_bp = NORMAL_RANGES["diastolic_bp"]
            if diastolic < min_bp or diastolic > max_bp:
                severity = "WARNING"
                if diastolic > 110:
                    severity = "CRITICAL"
                alerts.append(
                    VitalSignAlert(
                        parameter="diastolic_bp",
                        value=diastolic,
                        normal_range=f"{min_bp}-{max_bp} mmHg",
                        severity=severity,
                        message=_(
                            "PA diastólica anormal: {value} mmHg (normal: {range})"
                        ).format(value=diastolic, range=f"{min_bp}-{max_bp} mmHg"),
                    )
                )

        # Heart Rate
        hr = vital_signs.get("heart_rate")
        if hr is not None:
            hr = int(hr)
            min_hr, max_hr = NORMAL_RANGES["heart_rate"]
            if hr < min_hr:
                severity = "CRITICAL" if hr < 50 else "WARNING"
                alerts.append(
                    VitalSignAlert(
                        parameter="heart_rate",
                        value=hr,
                        normal_range=f"{min_hr}-{max_hr} bpm",
                        severity=severity,
                        message=_(
                            "Bradicardia: {value} bpm (normal: {range})"
                        ).format(value=hr, range=f"{min_hr}-{max_hr} bpm"),
                    )
                )
            elif hr > max_hr:
                severity = "CRITICAL" if hr > 120 else "WARNING"
                alerts.append(
                    VitalSignAlert(
                        parameter="heart_rate",
                        value=hr,
                        normal_range=f"{min_hr}-{max_hr} bpm",
                        severity=severity,
                        message=_(
                            "Taquicardia: {value} bpm (normal: {range})"
                        ).format(value=hr, range=f"{min_hr}-{max_hr} bpm"),
                    )
                )

        # Respiratory Rate
        rr = vital_signs.get("respiratory_rate")
        if rr is not None:
            rr = int(rr)
            min_rr, max_rr = NORMAL_RANGES["respiratory_rate"]
            if rr < min_rr:
                severity = "CRITICAL" if rr < 10 else "WARNING"
                alerts.append(
                    VitalSignAlert(
                        parameter="respiratory_rate",
                        value=rr,
                        normal_range=f"{min_rr}-{max_rr} irpm",
                        severity=severity,
                        message=_(
                            "Bradipneia: {value} irpm (normal: {range})"
                        ).format(value=rr, range=f"{min_rr}-{max_rr} irpm"),
                    )
                )
            elif rr > max_rr:
                severity = "CRITICAL" if rr > 30 else "WARNING"
                alerts.append(
                    VitalSignAlert(
                        parameter="respiratory_rate",
                        value=rr,
                        normal_range=f"{min_rr}-{max_rr} irpm",
                        severity=severity,
                        message=_(
                            "Taquipneia: {value} irpm (normal: {range})"
                        ).format(value=rr, range=f"{min_rr}-{max_rr} irpm"),
                    )
                )

        # Oxygen Saturation
        spo2 = vital_signs.get("oxygen_saturation")
        if spo2 is not None:
            spo2 = int(spo2)
            min_spo2, max_spo2 = NORMAL_RANGES["oxygen_saturation"]
            if spo2 < min_spo2:
                severity = "CRITICAL" if spo2 < 90 else "WARNING"
                alerts.append(
                    VitalSignAlert(
                        parameter="oxygen_saturation",
                        value=spo2,
                        normal_range=f"{min_spo2}-{max_spo2}%",
                        severity=severity,
                        message=_(
                            "Hipoxemia: SpO2 {value}% (normal: {range})"
                        ).format(value=spo2, range=f"{min_spo2}-{max_spo2}%"),
                    )
                )

        return alerts


# ── Worker ────────────────────────────────────────────────────────────


class VitalSignsMonitoringWorker:
    """Monitors vital signs and generates clinical alerts.

    Analyzes vital sign measurements against normal ranges and
    generates alerts for abnormal values requiring clinical attention.
    """

    TOPIC = "clinical.vital_signs"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        analyzer: VitalSignsAnalyzer | None = None,
    ) -> None:
        self._fhir = fhir_client
        self._analyzer = analyzer or DMNVitalSignsAnalyzer()
        self._logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(metric_name="vital_signs_monitoring")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Monitor vital signs and generate alerts.

        Task Variables (input):
            encounter_reference: str - FHIR Encounter reference
            patient_reference: str - FHIR Patient reference
            vital_signs: dict - Vital sign measurements
            tenant_id: str - Tenant identifier (set via context)

        Returns:
            vital_signs_status: str - Overall status (NORMAL/ABNORMAL/CRITICAL)
            alerts: list[dict] - Generated alerts
            severity_level: str - Highest severity level
            requires_immediate_attention: bool - Needs immediate attention
        """
        ctx = get_required_tenant()
        encounter_reference: str = task_variables.get("encounter_reference", "")
        patient_reference: str = task_variables.get("patient_reference", "")
        vital_signs: dict[str, Any] = task_variables.get("vital_signs", {})

        if not encounter_reference or not patient_reference:
            raise ClinicalException(
                _("Referências de encontro e paciente são obrigatórias"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        if not vital_signs:
            raise ClinicalException(
                _("Sinais vitais são obrigatórios para monitoramento"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        self._logger.info(
            "monitoring_vital_signs",
            encounter_reference=encounter_reference,
            patient_reference=patient_reference,
            vital_signs_count=len(vital_signs),
            tenant_id=ctx.tenant_id,
        )

        # ── Fetch patient age from FHIR ──────────────────────────────

        try:
            patient_resource = await self._fhir.read(patient_reference)
            patient_age = self._calculate_age(
                patient_resource.get("birthDate")
            )
        except Exception as e:
            self._logger.warning(
                "fhir_patient_read_failed",
                patient_reference=patient_reference,
                error=str(e),
                tenant_id=ctx.tenant_id,
            )
            patient_age = None

        # ── Analyze vital signs ──────────────────────────────────────

        alerts = self._analyzer.analyze(
            vital_signs=vital_signs,
            patient_age=patient_age,
        )

        # ── Determine overall status and severity ────────────────────

        if not alerts:
            vital_signs_status = "NORMAL"
            severity_level = "INFO"
            requires_immediate_attention = False
        else:
            # Find highest severity
            severity_levels = [a.severity for a in alerts]
            if "CRITICAL" in severity_levels:
                vital_signs_status = "CRITICAL"
                severity_level = "CRITICAL"
                requires_immediate_attention = True
            elif "WARNING" in severity_levels:
                vital_signs_status = "ABNORMAL"
                severity_level = "WARNING"
                requires_immediate_attention = False
            else:
                vital_signs_status = "ABNORMAL"
                severity_level = "INFO"
                requires_immediate_attention = False

        # ── Convert alerts to dict format ────────────────────────────

        alerts_list = [
            {
                "parameter": a.parameter,
                "value": a.value,
                "normal_range": a.normal_range,
                "severity": a.severity,
                "message": a.message,
            }
            for a in alerts
        ]

        output = VitalSignsMonitoringOutput(
            vital_signs_status=vital_signs_status,
            alerts=alerts_list,
            severity_level=severity_level,
            requires_immediate_attention=requires_immediate_attention,
        )

        self._logger.info(
            "vital_signs_monitoring_complete",
            status=vital_signs_status,
            alerts_count=len(alerts),
            severity_level=severity_level,
            requires_immediate_attention=requires_immediate_attention,
            tenant_id=ctx.tenant_id,
        )

        return output.to_variables()

    @staticmethod
    def _calculate_age(birth_date: str | None) -> int | None:
        """Calculate age in years from ISO birth date."""
        if not birth_date:
            return None
        try:
            from datetime import datetime
            birth = datetime.fromisoformat(birth_date.replace("Z", "+00:00"))
            today = datetime.now()
            age = today.year - birth.year
            if (today.month, today.day) < (birth.month, birth.day):
                age -= 1
            return age
        except Exception:
            return None
