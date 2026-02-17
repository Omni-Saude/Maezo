"""Perform initial clinical assessment and triage using Manchester Protocol.

CIB7 External Task Topic: clinical.assessment
BPMN Error Codes: CLINICAL_ERROR
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service


# ── Constants & Validation ────────────────────────────────────────────


class ClinicalException(DomainException):
    """    Exception for clinical operations.
    
        Archetype: CLINICAL_SCORE
        """

    bpmn_error_code: str = "CLINICAL_ERROR"


# Manchester Protocol Triage Priorities (1-5)
TRIAGE_PRIORITY_IMMEDIATE = 1  # Red - Life-threatening
TRIAGE_PRIORITY_VERY_URGENT = 2  # Orange - Very urgent
TRIAGE_PRIORITY_URGENT = 3  # Yellow - Urgent
TRIAGE_PRIORITY_STANDARD = 4  # Green - Standard
TRIAGE_PRIORITY_NON_URGENT = 5  # Blue - Non-urgent


# ── Data Transfer Objects ─────────────────────────────────────────────


class VitalSigns(BaseModel):
    """Vital signs measurement."""

    temperature_celsius: float | None = Field(None, ge=30.0, le=45.0)
    systolic_bp: int | None = Field(None, ge=40, le=300)
    diastolic_bp: int | None = Field(None, ge=20, le=200)
    heart_rate: int | None = Field(None, ge=30, le=250)
    respiratory_rate: int | None = Field(None, ge=5, le=60)
    oxygen_saturation: int | None = Field(None, ge=50, le=100)


class ClinicalAssessmentInput(BaseModel):
    """Input variables for clinical assessment."""

    encounter_reference: str = Field(..., description="FHIR Encounter reference")
    patient_reference: str = Field(..., description="FHIR Patient reference")
    chief_complaint: str = Field(..., description="Chief complaint text")
    vital_signs: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = Field(default="")


class ClinicalAssessmentOutput(BaseModel):
    """Output variables for clinical assessment."""

    triage_priority: int
    assessment_summary: str
    risk_level: str
    recommended_actions: list[str]
    manchester_discriminator: str

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "triage_priority": self.triage_priority,
            "assessment_summary": self.assessment_summary,
            "risk_level": self.risk_level,
            "recommended_actions": self.recommended_actions,
            "manchester_discriminator": self.manchester_discriminator,
        }


# ── Protocol ──────────────────────────────────────────────────────────


class TriageEngine(ABC):
    """Protocol for clinical triage engines."""

    @abstractmethod
    def assess(
        self,
        chief_complaint: str,
        vital_signs: VitalSigns,
        patient_age: int | None,
    ) -> tuple[int, str, str]:
        """Assess patient and determine triage priority.

        Args:
            chief_complaint: Patient's chief complaint
            vital_signs: Measured vital signs
            patient_age: Patient age in years

        Returns:
            Tuple of (priority_level, discriminator, risk_level)
        """
        ...


# ── DMN Implementation ───────────────────────────────────────────────


class DMNTriageEngine(TriageEngine):
    """DMN-backed triage engine using FederatedDMNService."""

    def __init__(self, dmn_service: FederatedDMNService | None = None) -> None:
        self._dmn = dmn_service or get_dmn_service()
        self._logger = get_logger(__name__, component="dmn_triage")
        self._fallback = StubTriageEngine()

    def assess(
        self,
        chief_complaint: str,
        vital_signs: VitalSigns,
        patient_age: int | None,
    ) -> tuple[int, str, str]:
        """Assess triage priority via DMN decision tables."""
        tenant_id = get_required_tenant().tenant_id
        try:
            inputs: dict[str, Any] = {
                "chief_complaint": chief_complaint.lower().strip(),
            }
            if patient_age is not None:
                inputs["patient_age"] = patient_age
            if vital_signs.heart_rate is not None:
                inputs["heart_rate"] = vital_signs.heart_rate
            if vital_signs.systolic_bp is not None:
                inputs["systolic_bp"] = vital_signs.systolic_bp
            if vital_signs.oxygen_saturation is not None:
                inputs["oxygen_saturation"] = vital_signs.oxygen_saturation

            result = self._dmn.evaluate(
                tenant_id=tenant_id,
                category="clinical_safety",
                table_name="ews/triage/ews_triage_001",
                inputs=inputs,
            )
            if result and result.get("priority_level") is not None:
                return (
                    int(result["priority_level"]),
                    result.get("discriminator", "DMN_TRIAGE"),
                    result.get("risk_level", "MODERATE"),
                )
        except (FileNotFoundError, ValueError):
            pass
        except Exception as exc:
            self._logger.warning("dmn_triage_error", error=str(exc))
        return self._fallback.assess(chief_complaint, vital_signs, patient_age)


# ── Stub Implementation ──────────────────────────────────────────────

# Manchester Protocol discriminators mapping
_COMPLAINT_DISCRIMINATORS: dict[str, tuple[int, str]] = {
    # Immediate (Red)
    "parada cardiorrespiratória": (1, "PARADA_CARDIORESPIRATORIA"),
    "inconsciência": (1, "INCONSCIENCIA"),
    "convulsão ativa": (1, "CONVULSAO_ATIVA"),
    "choque": (1, "CHOQUE"),
    # Very Urgent (Orange)
    "dor torácica": (2, "DOR_TORACICA"),
    "dispneia grave": (2, "DISPNEIA_GRAVE"),
    "alteração do estado mental": (2, "ALTERACAO_MENTAL"),
    "cefaleia súbita intensa": (2, "CEFALEIA_SUBITA"),
    "dor abdominal intensa": (2, "DOR_ABDOMINAL_INTENSA"),
    # Urgent (Yellow)
    "febre alta": (3, "FEBRE_ALTA"),
    "vômitos persistentes": (3, "VOMITOS_PERSISTENTES"),
    "dor moderada": (3, "DOR_MODERADA"),
    "sangramento moderado": (3, "SANGRAMENTO_MODERADO"),
    # Standard (Green)
    "tosse": (4, "TOSSE"),
    "febre baixa": (4, "FEBRE_BAIXA"),
    "dor leve": (4, "DOR_LEVE"),
    "resfriado": (4, "RESFRIADO"),
    # Non-urgent (Blue)
    "certificado médico": (5, "CERTIFICADO_MEDICO"),
    "receita médica": (5, "RECEITA_MEDICA"),
    "resultado de exame": (5, "RESULTADO_EXAME"),
}


class StubTriageEngine(TriageEngine):
    """Manchester Protocol-based triage engine for development/testing.

    Uses simplified discriminators based on chief complaint keywords
    and vital signs thresholds.
    """

    def assess(
        self,
        chief_complaint: str,
        vital_signs: VitalSigns,
        patient_age: int | None,
    ) -> tuple[int, str, str]:
        """Assess using Manchester Protocol discriminators."""
        complaint_lower = chief_complaint.lower()

        # Check vital signs for critical values (override complaint)
        if vital_signs.oxygen_saturation and vital_signs.oxygen_saturation < 90:
            return (1, "HIPOXEMIA_CRITICA", "IMMEDIATE")

        if vital_signs.systolic_bp and vital_signs.systolic_bp < 90:
            return (1, "HIPOTENSAO_CRITICA", "IMMEDIATE")

        if vital_signs.heart_rate:
            if vital_signs.heart_rate > 150 or vital_signs.heart_rate < 50:
                return (2, "ARRITMIA_GRAVE", "VERY_URGENT")

        if vital_signs.respiratory_rate:
            if vital_signs.respiratory_rate > 30 or vital_signs.respiratory_rate < 10:
                return (2, "INSUFICIENCIA_RESPIRATORIA", "VERY_URGENT")

        if vital_signs.temperature_celsius:
            if vital_signs.temperature_celsius > 39.5:
                return (2, "FEBRE_ALTA", "VERY_URGENT")
            elif vital_signs.temperature_celsius > 38.0:
                return (3, "FEBRE_MODERADA", "URGENT")

        # Match chief complaint to discriminators
        for keyword, (priority, discriminator) in _COMPLAINT_DISCRIMINATORS.items():
            if keyword in complaint_lower:
                risk_level = self._priority_to_risk(priority)
                return (priority, discriminator, risk_level)

        # Default to standard priority
        return (4, "NAO_CLASSIFICADO", "STANDARD")

    @staticmethod
    def _priority_to_risk(priority: int) -> str:
        """Convert priority number to risk level string."""
        mapping = {
            1: "IMMEDIATE",
            2: "VERY_URGENT",
            3: "URGENT",
            4: "STANDARD",
            5: "NON_URGENT",
        }
        return mapping.get(priority, "STANDARD")


# ── Worker ────────────────────────────────────────────────────────────


class ClinicalAssessmentWorker:
    """Performs initial clinical assessment and triage.

    Uses Manchester Protocol to assign triage priority based on
    chief complaint and vital signs.
    """

    TOPIC = "clinical.assessment"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        triage_engine: TriageEngine | None = None,
        tasy_api_client: TasyApiClientProtocol | None = None,
    ) -> None:
        self._fhir = fhir_client
        self._triage = triage_engine or DMNTriageEngine()
        self._tasy_api_client = tasy_api_client
        self._logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(metric_name="clinical_assessment")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Perform clinical assessment and assign triage priority.

        Task Variables (input):
            encounter_reference: str - FHIR Encounter reference
            patient_reference: str - FHIR Patient reference
            chief_complaint: str - Patient's chief complaint
            vital_signs: dict - Vital signs measurements
            tenant_id: str - Tenant identifier (set via context)

        Returns:
            triage_priority: int - Priority 1-5 (Manchester Protocol)
            assessment_summary: str - Assessment summary text
            risk_level: str - Risk level (IMMEDIATE, VERY_URGENT, etc.)
            recommended_actions: list[str] - Recommended clinical actions
            manchester_discriminator: str - Manchester discriminator code
        """
        ctx = get_required_tenant()
        encounter_reference: str = task_variables.get("encounter_reference", "")
        patient_reference: str = task_variables.get("patient_reference", "")
        chief_complaint: str = task_variables.get("chief_complaint", "")
        vital_signs_dict: dict[str, Any] = task_variables.get("vital_signs", {})

        if not encounter_reference or not patient_reference:
            raise ClinicalException(
                _("Referências de encontro e paciente são obrigatórias"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        if not chief_complaint:
            raise ClinicalException(
                _("Queixa principal é obrigatória para avaliação clínica"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        self._logger.info(
            "starting_clinical_assessment",
            encounter_reference=encounter_reference,
            patient_reference=patient_reference,
            tenant_id=ctx.tenant_id,
        )

        # ── Fetch patient data from FHIR ─────────────────────────────

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

        # ── Parse vital signs ────────────────────────────────────────

        try:
            vital_signs = VitalSigns(**vital_signs_dict)
        except Exception as e:
            self._logger.warning(
                "vital_signs_parse_error",
                error=str(e),
                tenant_id=ctx.tenant_id,
            )
            vital_signs = VitalSigns()

        # ── Perform triage assessment ────────────────────────────────

        priority, discriminator, risk_level = self._triage.assess(
            chief_complaint=chief_complaint,
            vital_signs=vital_signs,
            patient_age=patient_age,
        )

        # ── Generate recommended actions ─────────────────────────────

        recommended_actions = self._generate_recommendations(
            priority=priority,
            discriminator=discriminator,
            vital_signs=vital_signs,
        )

        # ── Integrate TASY acuity scoring (optional) ─────────────────

        tasy_acuity = None
        if self._tasy_api_client:
            try:
                # Extract encounter ID from reference (e.g., "Encounter/123" -> "123")
                encounter_id = encounter_reference.split("/")[-1]
                tasy_acuity = await self._tasy_api_client.get_automated_acuity(encounter_id)
                self._logger.info(
                    "tasy_acuity_retrieved",
                    encounter_id=encounter_id,
                    tasy_acuity=tasy_acuity,
                    tenant_id=ctx.tenant_id,
                )
            except Exception as e:
                self._logger.warning(
                    "tasy_acuity_failed",
                    encounter_reference=encounter_reference,
                    error=str(e),
                    tenant_id=ctx.tenant_id,
                )

        # ── Build assessment summary ─────────────────────────────────

        assessment_summary = _(
            "Paciente apresenta: {complaint}. "
            "Prioridade Manchester: {priority} ({risk_level}). "
            "Discriminador: {discriminator}."
        ).format(
            complaint=chief_complaint,
            priority=priority,
            risk_level=risk_level,
            discriminator=discriminator,
        )

        # Add TASY acuity to summary if available
        if tasy_acuity:
            assessment_summary += _(" TASY Acuity: {acuity}.").format(
                acuity=tasy_acuity.get("acuity_level", "N/A")
            )

        output_data = ClinicalAssessmentOutput(
            triage_priority=priority,
            assessment_summary=assessment_summary,
            risk_level=risk_level,
            recommended_actions=recommended_actions,
            manchester_discriminator=discriminator,
        )

        # Convert to variables and add TASY data if available
        output_vars = output_data.to_variables()
        if tasy_acuity:
            output_vars["tasy_acuity"] = tasy_acuity

        self._logger.info(
            "clinical_assessment_complete",
            triage_priority=priority,
            risk_level=risk_level,
            discriminator=discriminator,
            tasy_acuity_present=tasy_acuity is not None,
            tenant_id=ctx.tenant_id,
        )

        return output_vars

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

    def _generate_recommendations(
        self,
        priority: int,
        discriminator: str,
        vital_signs: VitalSigns,
    ) -> list[str]:
        """Generate recommended clinical actions based on triage."""
        actions: list[str] = []

        if priority == 1:
            actions.append(_("Atendimento IMEDIATO - ativar equipe de emergência"))
            actions.append(_("Monitorizar sinais vitais continuamente"))
            actions.append(_("Garantir acesso venoso"))
            actions.append(_("Preparar para possível ressuscitação"))
        elif priority == 2:
            actions.append(_("Atendimento em até 10 minutos"))
            actions.append(_("Avaliar necessidade de exames complementares urgentes"))
            actions.append(_("Monitorizar sinais vitais a cada 15 minutos"))
        elif priority == 3:
            actions.append(_("Atendimento em até 60 minutos"))
            actions.append(_("Reavaliação periódica na sala de espera"))
            actions.append(_("Considerar analgesia se dor presente"))
        elif priority == 4:
            actions.append(_("Atendimento em até 120 minutos"))
            actions.append(_("Orientar paciente sobre tempo de espera"))
        else:
            actions.append(_("Atendimento não urgente"))
            actions.append(_("Orientar sobre alternativas ambulatoriais"))

        # Vital signs specific recommendations
        if vital_signs.oxygen_saturation and vital_signs.oxygen_saturation < 92:
            actions.append(_("Administrar oxigenoterapia"))

        if vital_signs.temperature_celsius and vital_signs.temperature_celsius > 38.5:
            actions.append(_("Considerar antitérmico"))

        return actions
