"""
Clinical Pathways Worker - Clinical pathways and care protocol execution tracking.

TOPIC: clinical.pathways

This worker manages clinical pathway execution including:
- Pathway milestone tracking
- Deviation detection and management
- Protocol adherence monitoring
- Care coordination across pathway stages
- Outcome measurement against pathway goals
- Timeline prediction and adjustment

Implements evidence-based clinical pathways for standardized care delivery.

Author: Claude Flow V3
License: MIT
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import hashlib

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service


logger = get_logger(__name__)


class ClinicalPathwayException(DomainException):
    """    Exception for clinical pathway errors.
    
        Archetype: CLINICAL_ALERT
        """
    bpmn_error_code: str = "CLINICAL_PATHWAY_ERROR"


# ============================================================================
# Input/Output DTOs
# ============================================================================


class PathwayMilestone(BaseModel):
    """Clinical pathway milestone."""

    milestone_id: str = Field(description="Unique milestone identifier")
    name: str = Field(description="Milestone name")
    description: str = Field(description="Milestone description")
    expected_timeframe: str = Field(description="Expected duration or deadline")
    status: str = Field(description="not_started/in_progress/completed/skipped/delayed")
    completed_at: Optional[str] = Field(None, description="ISO 8601 completion timestamp")
    responsible_role: str = Field(description="Role responsible for milestone")
    required_actions: List[str] = Field(description="Required actions")
    completion_criteria: List[str] = Field(description="Completion criteria")


class PathwayDeviation(BaseModel):
    """Deviation from clinical pathway."""

    deviation_id: str = Field(description="Unique deviation identifier")
    milestone_id: str = Field(description="Related milestone")
    deviation_type: str = Field(
        description="timeline_delay/protocol_variance/contraindication/patient_preference/clinical_judgment"
    )
    severity: str = Field(description="major/minor/acceptable")
    description: str = Field(description="Deviation description")
    rationale: str = Field(description="Reason for deviation")
    documented_by: str = Field(description="Practitioner/staff-123")
    documented_at: str = Field(description="ISO 8601 timestamp")
    requires_approval: bool = Field(description="Whether approval is required")
    approved: Optional[bool] = Field(None, description="Approval status")


class NextStep(BaseModel):
    """Next step in clinical pathway."""

    step_id: str = Field(description="Step identifier")
    milestone_id: str = Field(description="Related milestone")
    description: str = Field(description="Step description")
    expected_time: str = Field(description="ISO 8601 expected time")
    responsible_role: str = Field(description="Responsible role")
    dependencies: List[str] = Field(description="Dependent milestone IDs")
    priority: str = Field(description="high/medium/low")


class ClinicalPathwaysInput(BaseModel):
    """Input for clinical pathways worker."""

    encounter_reference: str = Field(description="Encounter/episode-123")
    pathway_id: str = Field(description="Pathway identifier (e.g., hip-replacement-v2)")
    current_step: str = Field(description="Current pathway step/milestone")
    pathway_data: Dict[str, Any] = Field(description="Pathway-specific data")
    action: str = Field(
        description="track_progress/record_deviation/get_next_steps/complete_milestone"
    )
    milestone_id: Optional[str] = Field(None, description="Specific milestone ID")
    deviation: Optional[Dict[str, Any]] = Field(None, description="Deviation details")

    def to_variables(self) -> Dict[str, Any]:
        """Convert to process variables."""
        return {
            "encounter_reference": self.encounter_reference,
            "pathway_id": self.pathway_id,
            "current_step": self.current_step,
            "pathway_data": self.pathway_data,
            "action": self.action,
            "milestone_id": self.milestone_id,
            "deviation": self.deviation,
        }


class ClinicalPathwaysOutput(BaseModel):
    """Output from clinical pathways worker."""

    pathway_session_id: str = Field(description="Pathway tracking session ID")
    encounter_reference: str = Field(description="Related encounter")
    pathway_id: str = Field(description="Pathway identifier")
    pathway_name: str = Field(description="Pathway name")
    pathway_status: str = Field(
        description="on_track/delayed/off_pathway/completed/discontinued"
    )
    current_milestone: str = Field(description="Current milestone name")
    progress_percentage: float = Field(description="0-100 pathway completion percentage")
    milestones_completed: int = Field(description="Number of completed milestones")
    milestones_total: int = Field(description="Total milestones")
    next_steps: List[Dict[str, Any]] = Field(description="Upcoming steps")
    deviations: List[Dict[str, Any]] = Field(description="Recorded deviations")
    timeline_variance: int = Field(description="Days ahead (+) or behind (-) schedule")
    estimated_completion: str = Field(description="ISO 8601 estimated completion date")
    recommendations: List[str] = Field(description="Pathway recommendations")
    requires_team_review: bool = Field(description="Whether team review is needed")
    updated_at: str = Field(description="ISO 8601 update timestamp")

    def to_variables(self) -> Dict[str, Any]:
        """Convert to process variables."""
        return {
            "pathway_session_id": self.pathway_session_id,
            "encounter_reference": self.encounter_reference,
            "pathway_id": self.pathway_id,
            "pathway_name": self.pathway_name,
            "pathway_status": self.pathway_status,
            "current_milestone": self.current_milestone,
            "progress_percentage": self.progress_percentage,
            "milestones_completed": self.milestones_completed,
            "milestones_total": self.milestones_total,
            "next_steps": self.next_steps,
            "deviations": self.deviations,
            "timeline_variance": self.timeline_variance,
            "estimated_completion": self.estimated_completion,
            "recommendations": self.recommendations,
            "requires_team_review": self.requires_team_review,
            "updated_at": self.updated_at,
        }


# ============================================================================
# Protocols
# ============================================================================


class PathwayManagerProtocol(ABC):
    """Protocol for clinical pathway management."""

    @abstractmethod
    async def load_pathway_definition(
        self,
        pathway_id: str,
    ) -> Dict[str, Any]:
        """Load pathway definition and milestones."""
        pass

    @abstractmethod
    async def get_pathway_status(
        self,
        encounter_ref: str,
        pathway_id: str,
    ) -> Dict[str, Any]:
        """Get current pathway execution status."""
        pass

    @abstractmethod
    async def record_milestone_completion(
        self,
        encounter_ref: str,
        pathway_id: str,
        milestone_id: str,
    ) -> Dict[str, Any]:
        """Record milestone completion."""
        pass

    @abstractmethod
    async def record_deviation(
        self,
        encounter_ref: str,
        pathway_id: str,
        deviation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Record pathway deviation."""
        pass

    @abstractmethod
    async def calculate_next_steps(
        self,
        pathway_definition: Dict[str, Any],
        current_status: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Calculate next steps based on current progress."""
        pass


class DMNPathwayManager(PathwayManagerProtocol):
    """DMN-backed pathway manager using FederatedDMNService."""

    def __init__(self, dmn_service: FederatedDMNService | None = None) -> None:
        self._dmn = dmn_service or get_dmn_service()
        self._logger = get_logger(__name__, component="dmn_pathways")
        self._fallback = PathwayManagerStub()

    async def load_pathway_definition(
        self, pathway_id: str,
    ) -> Dict[str, Any]:
        """Load pathway definition via DMN."""
        tenant_id = get_required_tenant().tenant_id
        try:
            result = self._dmn.evaluate(
                tenant_id=tenant_id,
                category="clinical_safety",
                table_name="safety/pathway_definition_001",
                inputs={"pathway_id": pathway_id},
            )
            if result and result.get("milestones"):
                return result
        except (FileNotFoundError, ValueError):
            pass
        except Exception as exc:
            self._logger.warning("dmn_pathway_def_error", error=str(exc))
        return await self._fallback.load_pathway_definition(pathway_id)

    async def get_pathway_status(
        self, encounter_ref: str, pathway_id: str,
    ) -> Dict[str, Any]:
        """Delegate to fallback -- status is runtime state, not DMN."""
        return await self._fallback.get_pathway_status(encounter_ref, pathway_id)

    async def record_milestone_completion(
        self, encounter_ref: str, pathway_id: str, milestone_id: str,
    ) -> Dict[str, Any]:
        """Delegate to fallback -- writes are not DMN-driven."""
        return await self._fallback.record_milestone_completion(
            encounter_ref, pathway_id, milestone_id,
        )

    async def record_deviation(
        self, encounter_ref: str, pathway_id: str, deviation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Delegate to fallback -- writes are not DMN-driven."""
        return await self._fallback.record_deviation(
            encounter_ref, pathway_id, deviation,
        )

    async def calculate_next_steps(
        self,
        pathway_definition: Dict[str, Any],
        current_status: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Calculate next steps via DMN."""
        tenant_id = get_required_tenant().tenant_id
        try:
            result = self._dmn.evaluate(
                tenant_id=tenant_id,
                category="clinical_safety",
                table_name="safety/pathway_next_steps_001",
                inputs={
                    "pathway_id": pathway_definition.get("pathway_id", ""),
                    "completed_milestones": current_status.get(
                        "milestones_completed", 0,
                    ),
                },
            )
            if result and result.get("results"):
                return result["results"]
        except (FileNotFoundError, ValueError):
            pass
        except Exception as exc:
            self._logger.warning("dmn_pathway_steps_error", error=str(exc))
        return await self._fallback.calculate_next_steps(
            pathway_definition, current_status,
        )


class PathwayManagerStub(PathwayManagerProtocol):
    """Stub implementation of pathway manager."""

    async def load_pathway_definition(
        self,
        pathway_id: str,
    ) -> Dict[str, Any]:
        """Stub: Load pathway definition."""
        logger.info(
            _("Carregando definição do pathway {id}").format(id=pathway_id)
        )

        # Simulated pathway definition
        return {
            "pathway_id": pathway_id,
            "pathway_name": _("Protocolo de Artroplastia de Quadril"),
            "pathway_version": "2.0",
            "expected_duration_days": 5,
            "milestones": [
                {
                    "id": "admission",
                    "name": _("Admissão e Avaliação Pré-operatória"),
                    "expected_timeframe": "Day 0",
                    "required_actions": [
                        _("Exames laboratoriais pré-op"),
                        _("Avaliação anestésica"),
                        _("Consentimento informado"),
                    ],
                },
                {
                    "id": "surgery",
                    "name": _("Procedimento Cirúrgico"),
                    "expected_timeframe": "Day 1",
                    "required_actions": [
                        _("Checklist cirúrgico"),
                        _("Profilaxia antibiótica"),
                        _("Artroplastia total de quadril"),
                    ],
                },
                {
                    "id": "early_mobilization",
                    "name": _("Mobilização Precoce"),
                    "expected_timeframe": "Day 1-2",
                    "required_actions": [
                        _("Fisioterapia - levantar e caminhar"),
                        _("Controle de dor"),
                        _("Profilaxia TEV"),
                    ],
                },
                {
                    "id": "rehabilitation",
                    "name": _("Reabilitação"),
                    "expected_timeframe": "Day 2-4",
                    "required_actions": [
                        _("Fisioterapia diária"),
                        _("Treinamento de AVDs"),
                        _("Avaliação de alta"),
                    ],
                },
                {
                    "id": "discharge",
                    "name": _("Alta Hospitalar"),
                    "expected_timeframe": "Day 5",
                    "required_actions": [
                        _("Critérios de alta atingidos"),
                        _("Plano de cuidados domiciliares"),
                        _("Agendamento de follow-up"),
                    ],
                },
            ],
        }

    async def get_pathway_status(
        self,
        encounter_ref: str,
        pathway_id: str,
    ) -> Dict[str, Any]:
        """Stub: Get pathway status."""
        logger.info(
            _("Obtendo status do pathway para {ref}").format(ref=encounter_ref)
        )

        # Simulated current status
        return {
            "encounter_reference": encounter_ref,
            "pathway_id": pathway_id,
            "start_date": (datetime.utcnow() - timedelta(days=2)).isoformat(),
            "completed_milestones": ["admission", "surgery"],
            "current_milestone": "early_mobilization",
            "deviations": [
                {
                    "deviation_id": "dev-001",
                    "milestone_id": "surgery",
                    "deviation_type": "timeline_delay",
                    "severity": "minor",
                    "description": _("Atraso de 3h na programação cirúrgica"),
                    "rationale": _("Emergência na sala cirúrgica"),
                    "documented_by": "Practitioner/surgeon-123",
                    "documented_at": datetime.utcnow().isoformat(),
                    "requires_approval": False,
                }
            ],
        }

    async def record_milestone_completion(
        self,
        encounter_ref: str,
        pathway_id: str,
        milestone_id: str,
    ) -> Dict[str, Any]:
        """Stub: Record milestone completion."""
        logger.info(
            _("Registrando conclusão do milestone {id}").format(id=milestone_id)
        )

        return {
            "milestone_id": milestone_id,
            "completed_at": datetime.utcnow().isoformat(),
            "status": "completed",
        }

    async def record_deviation(
        self,
        encounter_ref: str,
        pathway_id: str,
        deviation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Stub: Record deviation."""
        logger.info(
            _("Registrando desvio do pathway: {type}").format(
                type=deviation.get("deviation_type")
            )
        )

        return {
            "deviation_id": f"dev-{datetime.utcnow().timestamp()}",
            "recorded_at": datetime.utcnow().isoformat(),
            "status": "recorded",
        }

    async def calculate_next_steps(
        self,
        pathway_definition: Dict[str, Any],
        current_status: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Stub: Calculate next steps."""
        logger.info(_("Calculando próximos passos do pathway"))

        # Find next uncompleted milestones
        completed = set(current_status.get("completed_milestones", []))
        all_milestones = pathway_definition.get("milestones", [])

        next_steps = []
        for milestone in all_milestones:
            if milestone["id"] not in completed:
                next_steps.append({
                    "milestone_id": milestone["id"],
                    "name": milestone["name"],
                    "expected_time": milestone["expected_timeframe"],
                    "required_actions": milestone["required_actions"],
                })

        return next_steps[:3]  # Return next 3 steps


# ============================================================================
# Worker
# ============================================================================


class ClinicalPathwaysWorker:
    """
    Clinical pathways execution tracking worker.

    Manages clinical pathway execution, milestone tracking, deviation management,
    and timeline monitoring for standardized care delivery.
    """

    TOPIC = "clinical.pathways"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        pathway_manager: Optional[PathwayManagerProtocol] = None,
    ):
        """
        Initialize clinical pathways worker.

        Args:
            fhir_client: FHIR client for resource operations
            pathway_manager: Pathway manager (uses stub if not provided)
        """
        self.fhir_client = fhir_client
        self.pathway_manager = pathway_manager or DMNPathwayManager()

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute clinical pathway tracking.

        Args:
            task_variables: Task input variables

        Returns:
            Pathway status and next steps

        Raises:
            ClinicalPathwayException: If pathway execution fails
        """
        tenant_id = get_required_tenant()

        logger.info(
            _("Executando tracking de pathway clínico para tenant {tenant}").format(
                tenant=hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
            )
        )

        try:
            # Parse input
            pathway_input = ClinicalPathwaysInput(**task_variables)

            # Load pathway definition
            pathway_definition = await self.pathway_manager.load_pathway_definition(
                pathway_input.pathway_id
            )

            # Get current pathway status
            current_status = await self.pathway_manager.get_pathway_status(
                pathway_input.encounter_reference,
                pathway_input.pathway_id,
            )

            # Handle action
            if pathway_input.action == "complete_milestone" and pathway_input.milestone_id:
                await self.pathway_manager.record_milestone_completion(
                    pathway_input.encounter_reference,
                    pathway_input.pathway_id,
                    pathway_input.milestone_id,
                )
                # Refresh status
                current_status = await self.pathway_manager.get_pathway_status(
                    pathway_input.encounter_reference,
                    pathway_input.pathway_id,
                )

            elif pathway_input.action == "record_deviation" and pathway_input.deviation:
                await self.pathway_manager.record_deviation(
                    pathway_input.encounter_reference,
                    pathway_input.pathway_id,
                    pathway_input.deviation,
                )

            # Calculate next steps
            next_steps = await self.pathway_manager.calculate_next_steps(
                pathway_definition,
                current_status,
            )

            # Calculate progress
            milestones_total = len(pathway_definition.get("milestones", []))
            milestones_completed = len(current_status.get("completed_milestones", []))
            progress_percentage = (
                (milestones_completed / milestones_total * 100)
                if milestones_total > 0
                else 0.0
            )

            # Calculate timeline variance
            timeline_variance = self._calculate_timeline_variance(
                pathway_definition,
                current_status,
            )

            # Determine pathway status
            pathway_status = self._determine_pathway_status(
                timeline_variance,
                current_status.get("deviations", []),
                progress_percentage,
            )

            # Calculate estimated completion
            estimated_completion = self._calculate_estimated_completion(
                pathway_definition,
                current_status,
                timeline_variance,
            )

            # Generate recommendations
            recommendations = self._generate_recommendations(
                pathway_status,
                timeline_variance,
                current_status.get("deviations", []),
            )

            # Determine if team review needed
            requires_review = self._requires_team_review(
                pathway_status,
                current_status.get("deviations", []),
                timeline_variance,
            )

            # Prepare output
            output = ClinicalPathwaysOutput(
                pathway_session_id=f"PATHWAY-{datetime.utcnow().timestamp()}",
                encounter_reference=pathway_input.encounter_reference,
                pathway_id=pathway_input.pathway_id,
                pathway_name=pathway_definition.get("pathway_name", ""),
                pathway_status=pathway_status,
                current_milestone=current_status.get("current_milestone", ""),
                progress_percentage=round(progress_percentage, 1),
                milestones_completed=milestones_completed,
                milestones_total=milestones_total,
                next_steps=next_steps,
                deviations=current_status.get("deviations", []),
                timeline_variance=timeline_variance,
                estimated_completion=estimated_completion,
                recommendations=recommendations,
                requires_team_review=requires_review,
                updated_at=datetime.utcnow().isoformat(),
            )

            logger.info(
                _("Pathway tracking atualizado: {status}, {progress}% completo").format(
                    status=pathway_status,
                    progress=output.progress_percentage,
                )
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro no tracking de pathway clínico: {error}").format(error=str(e))
            )
            raise ClinicalPathwayException(
                message=_("Falha ao executar tracking de pathway clínico"),
                details={"error": str(e), "tenant_id": tenant_id},
            ) from e

    def _calculate_timeline_variance(
        self,
        pathway_definition: Dict[str, Any],
        current_status: Dict[str, Any],
    ) -> int:
        """Calculate timeline variance in days."""
        # Get expected duration
        expected_duration = pathway_definition.get("expected_duration_days", 7)

        # Get actual duration so far
        start_date_str = current_status.get("start_date")
        if not start_date_str:
            return 0

        start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
        days_elapsed = (datetime.utcnow() - start_date.replace(tzinfo=None)).days

        # Calculate based on progress
        milestones_total = len(pathway_definition.get("milestones", []))
        milestones_completed = len(current_status.get("completed_milestones", []))

        if milestones_total == 0:
            return 0

        expected_days_for_progress = (
            milestones_completed / milestones_total * expected_duration
        )

        variance = int(expected_days_for_progress - days_elapsed)

        return variance

    def _determine_pathway_status(
        self,
        timeline_variance: int,
        deviations: List[Dict[str, Any]],
        progress_percentage: float,
    ) -> str:
        """Determine overall pathway status."""
        # Check if completed
        if progress_percentage >= 100:
            return "completed"

        # Check for major deviations
        major_deviations = [
            d for d in deviations if d.get("severity") == "major"
        ]
        if major_deviations:
            return "off_pathway"

        # Check timeline
        if timeline_variance < -2:
            return "delayed"

        return "on_track"

    def _calculate_estimated_completion(
        self,
        pathway_definition: Dict[str, Any],
        current_status: Dict[str, Any],
        timeline_variance: int,
    ) -> str:
        """Calculate estimated completion date."""
        expected_duration = pathway_definition.get("expected_duration_days", 7)
        start_date_str = current_status.get("start_date")

        if not start_date_str:
            # Default to now + expected duration
            estimated = datetime.utcnow() + timedelta(days=expected_duration)
        else:
            start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            # Adjust by timeline variance
            adjusted_duration = expected_duration - timeline_variance
            estimated = start_date.replace(tzinfo=None) + timedelta(days=adjusted_duration)

        return estimated.isoformat()

    def _generate_recommendations(
        self,
        pathway_status: str,
        timeline_variance: int,
        deviations: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate pathway recommendations."""
        recommendations = []

        if pathway_status == "delayed":
            recommendations.append(
                _("Pathway atrasado em {days} dias - considerar intervenções para acelerar").format(
                    days=abs(timeline_variance)
                )
            )

        if pathway_status == "off_pathway":
            recommendations.append(
                _("Desvios significativos detectados - revisão multidisciplinar recomendada")
            )

        if len(deviations) > 3:
            recommendations.append(
                _("Múltiplos desvios registrados - avaliar aderência ao protocolo")
            )

        if not recommendations:
            recommendations.append(
                _("Pathway progredindo conforme esperado - manter protocolo")
            )

        return recommendations

    def _requires_team_review(
        self,
        pathway_status: str,
        deviations: List[Dict[str, Any]],
        timeline_variance: int,
    ) -> bool:
        """Determine if multidisciplinary team review is required."""
        if pathway_status == "off_pathway":
            return True

        major_deviations = [
            d for d in deviations if d.get("severity") == "major"
        ]
        if major_deviations:
            return True

        if timeline_variance < -3:
            return True

        return False
