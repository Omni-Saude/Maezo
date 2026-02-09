"""Create and update care plans based on diagnosis and treatment goals.

CIB7 External Task Topic: clinical.care_planning
BPMN Error Codes: CLINICAL_ERROR
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.integrations.fhir_client import FHIRClientProtocol
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


# ── Constants & Validation ────────────────────────────────────────────


class ClinicalException(DomainException):
    """Exception for clinical operations."""

    bpmn_error_code: str = "CLINICAL_ERROR"


CID10_SYSTEM = "http://www.saude.gov.br/cid-10"


# ── Data Transfer Objects ─────────────────────────────────────────────


class CareActivity(BaseModel):
    """Planned care activity."""

    code: str = Field(..., description="Activity code")
    display: str = Field(..., description="Activity description")
    frequency: str = Field(..., description="Activity frequency")
    duration_days: int | None = Field(None, description="Expected duration in days")


class CarePlanningInput(BaseModel):
    """Input variables for care planning."""

    encounter_reference: str = Field(..., description="FHIR Encounter reference")
    patient_reference: str = Field(..., description="FHIR Patient reference")
    diagnosis_codes: list[dict[str, Any]] = Field(
        default_factory=list, description="CID-10 diagnosis codes"
    )
    treatment_goals: list[str] = Field(
        default_factory=list, description="Treatment goals"
    )
    tenant_id: str = Field(default="")


class CarePlanningOutput(BaseModel):
    """Output variables for care planning."""

    care_plan_reference: str
    care_plan_status: str
    planned_activities: list[dict[str, Any]]
    estimated_duration_days: int

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "care_plan_reference": self.care_plan_reference,
            "care_plan_status": self.care_plan_status,
            "planned_activities": self.planned_activities,
            "estimated_duration_days": self.estimated_duration_days,
        }


# ── Protocol ──────────────────────────────────────────────────────────


class CarePlanEngine(ABC):
    """Protocol for care plan generation engines."""

    @abstractmethod
    def generate_plan(
        self,
        diagnosis_codes: list[dict[str, Any]],
        treatment_goals: list[str],
    ) -> list[CareActivity]:
        """Generate care plan activities based on diagnosis and goals.

        Args:
            diagnosis_codes: CID-10 diagnosis codes with display text
            treatment_goals: Patient treatment goals

        Returns:
            List of planned care activities
        """
        ...


# ── Stub Implementation ──────────────────────────────────────────────

# CID-10 to standard care activities mapping
_CID10_CARE_ACTIVITIES: dict[str, list[CareActivity]] = {
    "E11": [  # Diabetes mellitus tipo 2
        CareActivity(
            code="GLUCOSE_MONITORING",
            display="Monitoramento de glicemia capilar",
            frequency="3x/dia",
            duration_days=90,
        ),
        CareActivity(
            code="DIET_COUNSELING",
            display="Orientação nutricional para diabetes",
            frequency="1x/mês",
            duration_days=90,
        ),
        CareActivity(
            code="HBA1C_FOLLOW",
            display="Acompanhamento de hemoglobina glicada",
            frequency="1x/3meses",
            duration_days=90,
        ),
    ],
    "I10": [  # Hipertensão essencial
        CareActivity(
            code="BP_MONITORING",
            display="Monitoramento de pressão arterial",
            frequency="2x/dia",
            duration_days=60,
        ),
        CareActivity(
            code="SODIUM_RESTRICTION",
            display="Orientação sobre restrição de sódio",
            frequency="1x/mês",
            duration_days=60,
        ),
        CareActivity(
            code="CARDIO_EXAM",
            display="Avaliação cardiológica de rotina",
            frequency="1x/6meses",
            duration_days=180,
        ),
    ],
    "J18": [  # Pneumonia
        CareActivity(
            code="ANTIBIOTIC_THERAPY",
            display="Antibioticoterapia conforme protocolo",
            frequency="8/8h",
            duration_days=7,
        ),
        CareActivity(
            code="RESP_PHYSIOTHERAPY",
            display="Fisioterapia respiratória",
            frequency="2x/dia",
            duration_days=7,
        ),
        CareActivity(
            code="CHEST_XRAY_FOLLOW",
            display="Raio-X de tórax de controle",
            frequency="1x/semana",
            duration_days=14,
        ),
    ],
    "I50": [  # Insuficiência cardíaca
        CareActivity(
            code="FLUID_RESTRICTION",
            display="Restrição hídrica",
            frequency="contínuo",
            duration_days=30,
        ),
        CareActivity(
            code="DAILY_WEIGHT",
            display="Pesagem diária",
            frequency="1x/dia",
            duration_days=30,
        ),
        CareActivity(
            code="CARDIO_REHAB",
            display="Reabilitação cardíaca",
            frequency="3x/semana",
            duration_days=90,
        ),
    ],
    "K35": [  # Apendicite aguda
        CareActivity(
            code="SURGICAL_PREP",
            display="Preparo pré-operatório",
            frequency="1x",
            duration_days=1,
        ),
        CareActivity(
            code="POST_OP_CARE",
            display="Cuidados pós-operatórios",
            frequency="contínuo",
            duration_days=7,
        ),
        CareActivity(
            code="WOUND_CARE",
            display="Cuidados com ferida operatória",
            frequency="1x/dia",
            duration_days=14,
        ),
    ],
}


class StubCarePlanEngine(CarePlanEngine):
    """CID-10-based care plan generation engine for development/testing.

    Maps diagnosis codes to standard care activities based on
    clinical protocols and best practices.
    """

    def generate_plan(
        self,
        diagnosis_codes: list[dict[str, Any]],
        treatment_goals: list[str],
    ) -> list[CareActivity]:
        """Generate care plan using CID-10 to activity mapping."""
        activities: dict[str, CareActivity] = {}

        # Map diagnosis codes to standard activities
        for diagnosis in diagnosis_codes:
            code = diagnosis.get("code", "")
            # Match on CID-10 chapter (first 3 chars)
            prefix = code[:3] if len(code) >= 3 else code
            mapped_activities = _CID10_CARE_ACTIVITIES.get(prefix, [])

            for activity in mapped_activities:
                if activity.code not in activities:
                    activities[activity.code] = activity

        # Add goal-based activities
        for goal in treatment_goals:
            goal_lower = goal.lower()
            if "dor" in goal_lower and "PAIN_MANAGEMENT" not in activities:
                activities["PAIN_MANAGEMENT"] = CareActivity(
                    code="PAIN_MANAGEMENT",
                    display="Manejo de dor conforme escala",
                    frequency="conforme necessário",
                    duration_days=14,
                )
            if "mobilização" in goal_lower and "MOBILITY" not in activities:
                activities["MOBILITY"] = CareActivity(
                    code="MOBILITY",
                    display="Mobilização e deambulação assistida",
                    frequency="3x/dia",
                    duration_days=7,
                )
            if "nutrição" in goal_lower and "NUTRITION" not in activities:
                activities["NUTRITION"] = CareActivity(
                    code="NUTRITION",
                    display="Avaliação e suporte nutricional",
                    frequency="1x/dia",
                    duration_days=14,
                )

        # Default activity if none matched
        if not activities:
            activities["GENERAL_CARE"] = CareActivity(
                code="GENERAL_CARE",
                display="Cuidados gerais de enfermagem",
                frequency="contínuo",
                duration_days=3,
            )

        return list(activities.values())


# ── Worker ────────────────────────────────────────────────────────────


class CarePlanningWorker:
    """Creates and updates care plans based on diagnosis.

    Generates structured care plans with planned activities,
    timelines, and treatment goals aligned with clinical protocols.
    """

    TOPIC = "clinical.care_planning"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        care_plan_engine: CarePlanEngine | None = None,
    ) -> None:
        self._fhir = fhir_client
        self._engine = care_plan_engine or StubCarePlanEngine()
        self._logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(metric_name="clinical_care_planning")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Create or update care plan based on diagnosis.

        Task Variables (input):
            encounter_reference: str - FHIR Encounter reference
            patient_reference: str - FHIR Patient reference
            diagnosis_codes: list[dict] - CID-10 diagnosis codes
            treatment_goals: list[str] - Treatment goals
            tenant_id: str - Tenant identifier (set via context)

        Returns:
            care_plan_reference: str - FHIR CarePlan reference
            care_plan_status: str - CarePlan status (draft/active/completed)
            planned_activities: list[dict] - Planned care activities
            estimated_duration_days: int - Estimated care plan duration
        """
        ctx = get_required_tenant()
        encounter_reference: str = task_variables.get("encounter_reference", "")
        patient_reference: str = task_variables.get("patient_reference", "")
        diagnosis_codes: list[dict[str, Any]] = task_variables.get(
            "diagnosis_codes", []
        )
        treatment_goals: list[str] = task_variables.get("treatment_goals", [])

        if not encounter_reference or not patient_reference:
            raise ClinicalException(
                _("Referências de encontro e paciente são obrigatórias"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        if not diagnosis_codes:
            raise ClinicalException(
                _("Códigos de diagnóstico são obrigatórios para plano de cuidados"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        self._logger.info(
            "starting_care_planning",
            encounter_reference=encounter_reference,
            patient_reference=patient_reference,
            diagnosis_count=len(diagnosis_codes),
            goals_count=len(treatment_goals),
            tenant_id=ctx.tenant_id,
        )

        # ── Generate care plan activities ────────────────────────────

        activities = self._engine.generate_plan(
            diagnosis_codes=diagnosis_codes,
            treatment_goals=treatment_goals,
        )

        # ── Calculate estimated duration ─────────────────────────────

        max_duration = max(
            (a.duration_days for a in activities if a.duration_days),
            default=7,
        )

        # ── Build FHIR CarePlan resource ─────────────────────────────

        care_plan_resource = self._build_care_plan_resource(
            patient_reference=patient_reference,
            encounter_reference=encounter_reference,
            diagnosis_codes=diagnosis_codes,
            treatment_goals=treatment_goals,
            activities=activities,
        )

        # ── Create CarePlan in FHIR ──────────────────────────────────

        try:
            created_plan = await self._fhir.create(care_plan_resource)
            care_plan_id = created_plan.get("id", "")
            care_plan_reference = f"CarePlan/{care_plan_id}"
            care_plan_status = created_plan.get("status", "draft")

            self._logger.info(
                "care_plan_created",
                care_plan_reference=care_plan_reference,
                status=care_plan_status,
                tenant_id=ctx.tenant_id,
            )
        except Exception as e:
            self._logger.error(
                "care_plan_creation_failed",
                error=str(e),
                tenant_id=ctx.tenant_id,
            )
            raise ClinicalException(
                _("Falha ao criar plano de cuidados no FHIR: {error}").format(
                    error=str(e)
                ),
                bpmn_error_code="CLINICAL_ERROR",
            )

        # ── Prepare output ───────────────────────────────────────────

        planned_activities_list = [
            {
                "code": a.code,
                "display": a.display,
                "frequency": a.frequency,
                "duration_days": a.duration_days,
            }
            for a in activities
        ]

        output = CarePlanningOutput(
            care_plan_reference=care_plan_reference,
            care_plan_status=care_plan_status,
            planned_activities=planned_activities_list,
            estimated_duration_days=max_duration,
        )

        self._logger.info(
            "care_planning_complete",
            care_plan_reference=care_plan_reference,
            activities_count=len(activities),
            estimated_duration_days=max_duration,
            tenant_id=ctx.tenant_id,
        )

        return output.to_variables()

    def _build_care_plan_resource(
        self,
        patient_reference: str,
        encounter_reference: str,
        diagnosis_codes: list[dict[str, Any]],
        treatment_goals: list[str],
        activities: list[CareActivity],
    ) -> dict[str, Any]:
        """Build FHIR R4 CarePlan resource."""
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        period_start = now.isoformat() + "Z"

        # Calculate end date from max duration
        max_duration = max(
            (a.duration_days for a in activities if a.duration_days),
            default=7,
        )
        period_end = (now + timedelta(days=max_duration)).isoformat() + "Z"

        # Build activity detail array
        activity_details = []
        for activity in activities:
            activity_details.append(
                {
                    "detail": {
                        "code": {
                            "coding": [
                                {
                                    "code": activity.code,
                                    "display": activity.display,
                                }
                            ]
                        },
                        "status": "not-started",
                        "scheduledString": activity.frequency,
                    }
                }
            )

        # Build goal array
        goal_array = []
        for idx, goal_text in enumerate(treatment_goals):
            goal_array.append(
                {
                    "reference": f"#goal-{idx}",
                    "display": goal_text,
                }
            )

        care_plan = {
            "resourceType": "CarePlan",
            "status": "active",
            "intent": "plan",
            "subject": {"reference": patient_reference},
            "encounter": {"reference": encounter_reference},
            "period": {
                "start": period_start,
                "end": period_end,
            },
            "activity": activity_details,
        }

        if goal_array:
            care_plan["goal"] = goal_array

        # Add diagnosis as addresses
        if diagnosis_codes:
            addresses = []
            for diagnosis in diagnosis_codes:
                addresses.append(
                    {
                        "reference": f"Condition/{diagnosis.get('code', '')}",
                        "display": diagnosis.get("display", ""),
                    }
                )
            care_plan["addresses"] = addresses

        return care_plan
