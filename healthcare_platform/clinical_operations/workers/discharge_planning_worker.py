"""
Discharge Planning Worker - TOPIC: clinical.discharge_planning

Handles discharge planning and coordination for patient encounters.
Ensures all discharge criteria are met before patient discharge.

LGPD Compliance: SHA-256 hashes for patient identifiers
Standards: FHIR R4, CID-10, TUSS
Localization: Portuguese (_)
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
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__)


class ClinicalException(DomainException):
    """Clinical domain exception"""

    bpmn_error_code: str = "CLINICAL_ERROR"


class DischargePlanningException(ClinicalException):
    """Discharge planning specific exception"""

    bpmn_error_code: str = "DISCHARGE_PLANNING_ERROR"


# ============================================================================
# Input/Output DTOs
# ============================================================================


class DischargePlanningInput(BaseModel):
    """Input for discharge planning"""

    encounter_reference: str = Field(..., description="FHIR Encounter reference")
    patient_reference: str = Field(..., description="FHIR Patient reference")
    discharge_criteria: list[str] = Field(
        default_factory=list, description="Required discharge criteria"
    )
    pending_items: list[str] = Field(
        default_factory=list, description="Known pending items"
    )
    target_discharge_date: str | None = Field(
        None, description="Target discharge date (ISO 8601)"
    )
    discharge_destination: str | None = Field(
        None, description="Discharge destination (home/rehab/ltc/transfer)"
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables"""
        return {
            "encounter_reference": self.encounter_reference,
            "patient_reference": self.patient_reference,
            "discharge_criteria": self.discharge_criteria,
            "pending_items": self.pending_items,
            "target_discharge_date": self.target_discharge_date,
            "discharge_destination": self.discharge_destination,
        }


class DischargeChecklistItem(BaseModel):
    """Discharge checklist item"""

    item_name: str = Field(..., description="Checklist item name")
    status: str = Field(..., description="Status: complete/pending/not_applicable")
    completed_at: str | None = Field(None, description="Completion timestamp")
    completed_by: str | None = Field(None, description="Practitioner reference")
    notes: str | None = Field(None, description="Additional notes")


class FollowUpPlan(BaseModel):
    """Follow-up plan details"""

    appointment_scheduled: bool = Field(..., description="Follow-up appointment scheduled")
    appointment_date: str | None = Field(None, description="Appointment date (ISO 8601)")
    appointment_practitioner: str | None = Field(None, description="Practitioner reference")
    specialty: str | None = Field(None, description="Specialty (CBO)")
    instructions: list[str] = Field(
        default_factory=list, description="Follow-up instructions"
    )


class DischargePlanningOutput(BaseModel):
    """Output from discharge planning"""

    discharge_readiness: str = Field(
        ..., description="Readiness status: ready/not_ready/conditional"
    )
    discharge_readiness_score: float = Field(
        ..., ge=0.0, le=1.0, description="Readiness score (0-1)"
    )
    pending_checklist: list[DischargeChecklistItem] = Field(
        default_factory=list, description="Discharge checklist items"
    )
    discharge_summary: str = Field(..., description="Discharge summary text")
    follow_up_plan: FollowUpPlan = Field(..., description="Follow-up plan")
    barriers_to_discharge: list[str] = Field(
        default_factory=list, description="Identified barriers"
    )
    estimated_discharge_date: str | None = Field(
        None, description="Estimated discharge date (ISO 8601)"
    )
    patient_education_completed: bool = Field(
        ..., description="Patient education completed"
    )
    medications_reconciled: bool = Field(..., description="Medications reconciled")
    transport_arranged: bool = Field(..., description="Transport arranged if needed")
    patient_id_hash: str = Field(..., description="SHA-256 hash of patient ID (LGPD)")

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables"""
        return {
            "discharge_readiness": self.discharge_readiness,
            "discharge_readiness_score": self.discharge_readiness_score,
            "pending_checklist": [item.model_dump() for item in self.pending_checklist],
            "discharge_summary": self.discharge_summary,
            "follow_up_plan": self.follow_up_plan.model_dump(),
            "barriers_to_discharge": self.barriers_to_discharge,
            "estimated_discharge_date": self.estimated_discharge_date,
            "patient_education_completed": self.patient_education_completed,
            "medications_reconciled": self.medications_reconciled,
            "transport_arranged": self.transport_arranged,
            "patient_id_hash": self.patient_id_hash,
        }


# ============================================================================
# Protocol & Implementation
# ============================================================================


class DischargePlanningWorkerProtocol(ABC):
    """Protocol for discharge planning worker"""

    TOPIC = "clinical.discharge_planning"

    @abstractmethod
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute discharge planning"""
        pass


class DischargePlanningWorker(DischargePlanningWorkerProtocol):
    """Production discharge planning worker"""

    TOPIC = "clinical.discharge_planning"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        dmn_service: FederatedDMNService | None = None,
        tasy_api_client: TasyApiClientProtocol | None = None,
    ):
        self.fhir_client = fhir_client
        self._dmn = dmn_service or get_dmn_service()
        self._tasy_api_client = tasy_api_client

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute discharge planning and coordination.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with discharge planning results

        Raises:
            DischargePlanningException: If planning fails
        """
        tenant_id = get_required_tenant()
        logger.info(
            _("Iniciando planejamento de alta"),
            extra={
                "tenant_id": tenant_id,
                "encounter": task_variables.get("encounter_reference"),
            },
        )

        # Parse input
        input_dto = DischargePlanningInput(**task_variables)

        # Hash patient ID for LGPD compliance
        patient_id_hash = hashlib.sha256(
            input_dto.patient_reference.encode()
        ).hexdigest()

        try:
            # Fetch encounter and patient data
            encounter = await self._fetch_encounter(input_dto.encounter_reference)
            patient = await self._fetch_patient(input_dto.patient_reference)

            # Integrate TASY readmission risk scoring (optional)
            readmission_risk = None
            if self._tasy_api_client:
                try:
                    # Extract encounter ID from reference (e.g., "Encounter/123" -> "123")
                    encounter_id = input_dto.encounter_reference.split("/")[-1]
                    readmission_risk = await self._tasy_api_client.get_risk_of_readmission_score(
                        encounter_id
                    )
                    logger.info(
                        _("TASY readmission risk retrieved"),
                        extra={
                            "tenant_id": tenant_id,
                            "encounter_id": encounter_id,
                            "readmission_risk": readmission_risk,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        _("Falha ao obter risco de readmissão TASY"),
                        extra={
                            "tenant_id": tenant_id,
                            "encounter_reference": input_dto.encounter_reference,
                            "error": str(e),
                        },
                    )

            # Build discharge checklist
            checklist = await self._build_discharge_checklist(
                encounter, patient, input_dto.discharge_criteria
            )

            # Add high readmission risk to checklist if needed
            if readmission_risk and readmission_risk.get("score", 0) > 0.5:
                checklist.append(
                    DischargeChecklistItem(
                        item_name="high_readmission_risk_intervention",
                        status="pending",
                        notes=_(
                            "Paciente com alto risco de readmissão (TASY score: {score}). "
                            "Requer intervenções adicionais."
                        ).format(score=readmission_risk.get("score")),
                    )
                )

            # Assess discharge readiness
            readiness, readiness_score = self._assess_discharge_readiness(checklist)

            # Check medications reconciliation
            medications_reconciled = await self._check_medications_reconciliation(
                input_dto.encounter_reference
            )

            # Check patient education
            patient_education_completed = await self._check_patient_education(
                input_dto.encounter_reference
            )

            # Check transport arrangements
            transport_arranged = await self._check_transport_arrangements(
                input_dto.encounter_reference, input_dto.discharge_destination
            )

            # Build follow-up plan
            follow_up_plan = await self._build_follow_up_plan(encounter, patient)

            # Identify barriers
            barriers = self._identify_barriers_to_discharge(
                checklist, medications_reconciled, patient_education_completed
            )

            # Generate discharge summary
            discharge_summary = self._generate_discharge_summary(
                encounter, patient, checklist
            )

            # Estimate discharge date
            estimated_discharge_date = self._estimate_discharge_date(
                readiness, input_dto.target_discharge_date
            )

            # Build output
            output = DischargePlanningOutput(
                discharge_readiness=readiness,
                discharge_readiness_score=readiness_score,
                pending_checklist=checklist,
                discharge_summary=discharge_summary,
                follow_up_plan=follow_up_plan,
                barriers_to_discharge=barriers,
                estimated_discharge_date=estimated_discharge_date,
                patient_education_completed=patient_education_completed,
                medications_reconciled=medications_reconciled,
                transport_arranged=transport_arranged,
                patient_id_hash=patient_id_hash,
            )

            # Convert to variables and add TASY readmission risk if available
            output_vars = output.to_variables()
            if readmission_risk:
                output_vars["readmission_risk"] = readmission_risk

            logger.info(
                _("Planejamento de alta concluído com sucesso"),
                extra={
                    "tenant_id": tenant_id,
                    "discharge_readiness": readiness,
                    "readiness_score": readiness_score,
                    "readmission_risk_present": readmission_risk is not None,
                },
            )

            return output_vars

        except Exception as e:
            logger.error(
                _("Erro no planejamento de alta"),
                extra={"tenant_id": tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise DischargePlanningException(
                message=_("Falha no planejamento de alta: {error}").format(error=str(e)),
                details={"encounter": input_dto.encounter_reference},
            ) from e

    async def _fetch_encounter(self, encounter_reference: str) -> dict[str, Any]:
        """Fetch encounter from FHIR"""
        return await self.fhir_client.read(encounter_reference)

    async def _fetch_patient(self, patient_reference: str) -> dict[str, Any]:
        """Fetch patient from FHIR"""
        return await self.fhir_client.read(patient_reference)

    async def _build_discharge_checklist(
        self,
        encounter: dict[str, Any],
        patient: dict[str, Any],
        criteria: list[str],
    ) -> list[DischargeChecklistItem]:
        """Build discharge checklist"""
        checklist = []

        # Standard checklist items
        standard_items = [
            "medications_reconciled",
            "follow_up_scheduled",
            "patient_education",
            "transport_arranged",
            "discharge_instructions",
            "medical_equipment",
            "home_health_services",
        ]

        # Add custom criteria
        all_items = list(set(standard_items + criteria))

        for item_name in all_items:
            # Check status (simplified - would query FHIR resources)
            status = await self._check_checklist_item_status(encounter, item_name)
            checklist.append(
                DischargeChecklistItem(
                    item_name=item_name,
                    status=status,
                    completed_at=(
                        datetime.utcnow().isoformat() if status == "complete" else None
                    ),
                )
            )

        return checklist

    async def _check_checklist_item_status(
        self, encounter: dict[str, Any], item_name: str
    ) -> str:
        """Check status of checklist item"""
        # Simplified - would query FHIR CarePlan, Task resources
        # For now, return mock status
        return "pending"

    def _assess_discharge_readiness(
        self, checklist: list[DischargeChecklistItem]
    ) -> tuple[str, float]:
        """Assess discharge readiness"""
        total_items = len(checklist)
        if total_items == 0:
            return "not_ready", 0.0

        completed_items = sum(1 for item in checklist if item.status == "complete")
        readiness_score = completed_items / total_items

        if readiness_score >= 0.9:
            readiness = "ready"
        elif readiness_score >= 0.7:
            readiness = "conditional"
        else:
            readiness = "not_ready"

        return readiness, readiness_score

    async def _check_medications_reconciliation(
        self, encounter_reference: str
    ) -> bool:
        """Check if medications have been reconciled"""
        # Would query FHIR MedicationStatement resources
        return False

    async def _check_patient_education(self, encounter_reference: str) -> bool:
        """Check if patient education is completed"""
        # Would query FHIR Procedure or DocumentReference resources
        return False

    async def _check_transport_arrangements(
        self, encounter_reference: str, discharge_destination: str | None
    ) -> bool:
        """Check if transport is arranged"""
        if discharge_destination in ["home", None]:
            return True  # Not required for home discharge
        # Would query FHIR Task resources
        return False

    async def _build_follow_up_plan(
        self, encounter: dict[str, Any], patient: dict[str, Any]
    ) -> FollowUpPlan:
        """Build follow-up plan"""
        # Would query FHIR Appointment resources
        return FollowUpPlan(
            appointment_scheduled=False,
            instructions=[
                _("Agendar consulta de retorno em 7-14 dias"),
                _("Monitorar sinais vitais"),
                _("Seguir prescrição médica"),
            ],
        )

    def _identify_barriers_to_discharge(
        self,
        checklist: list[DischargeChecklistItem],
        medications_reconciled: bool,
        patient_education_completed: bool,
    ) -> list[str]:
        """Identify barriers to discharge"""
        barriers = []

        if not medications_reconciled:
            barriers.append(_("Reconciliação de medicamentos pendente"))

        if not patient_education_completed:
            barriers.append(_("Educação do paciente incompleta"))

        for item in checklist:
            if item.status == "pending":
                barriers.append(
                    _("Item de checklist pendente: {item}").format(item=item.item_name)
                )

        return barriers

    def _generate_discharge_summary(
        self,
        encounter: dict[str, Any],
        patient: dict[str, Any],
        checklist: list[DischargeChecklistItem],
    ) -> str:
        """Generate discharge summary"""
        summary_parts = [
            _("Resumo de Alta Hospitalar"),
            "",
            _("Paciente em processo de planejamento de alta."),
            _("Checklist de alta em andamento."),
        ]
        return "\n".join(summary_parts)

    def _estimate_discharge_date(
        self, readiness: str, target_date: str | None
    ) -> str | None:
        """Estimate discharge date"""
        if readiness == "ready" and target_date:
            return target_date
        # Would use ML model or business rules
        return None


class DischargePlanningWorkerStub(DischargePlanningWorkerProtocol):
    """Stub implementation for testing"""

    TOPIC = "clinical.discharge_planning"

    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Stub execution"""
        input_dto = DischargePlanningInput(**task_variables)
        patient_id_hash = hashlib.sha256(
            input_dto.patient_reference.encode()
        ).hexdigest()

        output = DischargePlanningOutput(
            discharge_readiness="conditional",
            discharge_readiness_score=0.75,
            pending_checklist=[
                DischargeChecklistItem(
                    item_name="medications_reconciled",
                    status="complete",
                    completed_at=datetime.utcnow().isoformat(),
                ),
                DischargeChecklistItem(
                    item_name="follow_up_scheduled", status="pending"
                ),
            ],
            discharge_summary=_("Resumo de alta - stub"),
            follow_up_plan=FollowUpPlan(
                appointment_scheduled=False,
                instructions=[_("Agendar retorno em 7 dias")],
            ),
            barriers_to_discharge=[_("Agendamento de retorno pendente")],
            estimated_discharge_date=None,
            patient_education_completed=True,
            medications_reconciled=True,
            transport_arranged=True,
            patient_id_hash=patient_id_hash,
        )

        return output.to_variables()
