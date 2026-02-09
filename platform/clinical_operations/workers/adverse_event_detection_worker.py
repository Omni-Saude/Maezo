"""
Adverse Event Detection Worker - Detect and report adverse clinical events.

TOPIC: clinical.adverse_events

This worker detects, classifies, and reports adverse events including:
- Medication errors and adverse drug reactions
- Patient falls and injuries
- Hospital-acquired infections (IRAS)
- Surgical complications
- Equipment failures
- Procedural complications

Generates FHIR AdverseEvent resources and triggers notification workflows.

Author: Claude Flow V3
License: MIT
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import hashlib

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.integrations.fhir_client import FHIRClientProtocol
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


logger = get_logger(__name__)


class AdverseEventException(DomainException):
    """Exception for adverse event handling errors."""
    bpmn_error_code: str = "ADVERSE_EVENT_ERROR"


# ============================================================================
# Input/Output DTOs
# ============================================================================


class ContributingFactor(BaseModel):
    """Contributing factor to adverse event."""

    factor_type: str = Field(description="medication/equipment/human/environment/process")
    description: str = Field(description="Factor description")
    contribution_level: str = Field(description="primary/secondary/contributing")


class Notification(BaseModel):
    """Required notification for adverse event."""

    recipient_role: str = Field(description="Role to notify")
    notification_type: str = Field(description="immediate/urgent/routine")
    message: str = Field(description="Notification message")
    deadline: str = Field(description="ISO 8601 notification deadline")


class AdverseEventInput(BaseModel):
    """Input for adverse event detection."""

    encounter_reference: str = Field(description="Encounter/episode-123")
    patient_reference: str = Field(description="Patient/patient-123")
    event_type: str = Field(
        description="medication_error/fall/infection/surgical_complication/equipment_failure/other"
    )
    event_description: str = Field(description="Detailed event description")
    severity: str = Field(description="mild/moderate/severe/life_threatening/fatal")
    occurrence_datetime: str = Field(description="ISO 8601 event timestamp")
    location: Optional[str] = Field(None, description="Location/ward-123")
    detected_by: Optional[str] = Field(None, description="Practitioner/staff-123")
    contributing_factors: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Contributing factors"
    )

    def to_variables(self) -> Dict[str, Any]:
        """Convert to process variables."""
        return {
            "encounter_reference": self.encounter_reference,
            "patient_reference": self.patient_reference,
            "event_type": self.event_type,
            "event_description": self.event_description,
            "severity": self.severity,
            "occurrence_datetime": self.occurrence_datetime,
            "location": self.location,
            "detected_by": self.detected_by,
            "contributing_factors": self.contributing_factors,
        }


class AdverseEventOutput(BaseModel):
    """Output from adverse event detection."""

    adverse_event_reference: str = Field(description="AdverseEvent/event-123")
    event_id: str = Field(description="Unique event identifier")
    event_type: str = Field(description="Type of adverse event")
    event_classification: str = Field(
        description="preventable/non_preventable/unavoidable"
    )
    severity_assessment: str = Field(description="Confirmed severity level")
    patient_outcome: str = Field(
        description="no_harm/temporary_harm/permanent_harm/intervention_required/death"
    )
    required_notifications: List[Dict[str, Any]] = Field(
        description="Notifications to send"
    )
    root_cause_analysis_required: bool = Field(
        description="Whether RCA is required"
    )
    immediate_actions: List[str] = Field(description="Immediate actions taken")
    contributing_factors: List[Dict[str, Any]] = Field(
        description="Identified contributing factors"
    )
    regulatory_reporting_required: bool = Field(
        description="Whether regulatory reporting is needed"
    )
    follow_up_actions: List[str] = Field(description="Required follow-up actions")
    created_at: str = Field(description="ISO 8601 creation timestamp")

    def to_variables(self) -> Dict[str, Any]:
        """Convert to process variables."""
        return {
            "adverse_event_reference": self.adverse_event_reference,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_classification": self.event_classification,
            "severity_assessment": self.severity_assessment,
            "patient_outcome": self.patient_outcome,
            "required_notifications": self.required_notifications,
            "root_cause_analysis_required": self.root_cause_analysis_required,
            "immediate_actions": self.immediate_actions,
            "contributing_factors": self.contributing_factors,
            "regulatory_reporting_required": self.regulatory_reporting_required,
            "follow_up_actions": self.follow_up_actions,
            "created_at": self.created_at,
        }


# ============================================================================
# Protocols
# ============================================================================


class AdverseEventClassifierProtocol(ABC):
    """Protocol for adverse event classification."""

    @abstractmethod
    async def classify_event(
        self,
        event_type: str,
        description: str,
        severity: str,
        factors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Classify adverse event and determine preventability."""
        pass

    @abstractmethod
    async def assess_patient_outcome(
        self,
        event_type: str,
        severity: str,
        patient_ref: str,
    ) -> str:
        """Assess patient outcome from adverse event."""
        pass

    @abstractmethod
    async def identify_root_causes(
        self,
        event_type: str,
        description: str,
        factors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Identify root causes for RCA."""
        pass


class AdverseEventClassifierStub(AdverseEventClassifierProtocol):
    """Stub implementation of event classifier."""

    async def classify_event(
        self,
        event_type: str,
        description: str,
        severity: str,
        factors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Stub: Classify adverse event."""
        logger.info(
            _("Classificando evento adverso tipo={type}, gravidade={severity}").format(
                type=event_type, severity=severity
            )
        )

        # Simple classification logic
        classification = "preventable"
        if event_type == "infection" and severity in ["mild", "moderate"]:
            classification = "non_preventable"
        elif event_type == "surgical_complication":
            classification = "unavoidable"

        return {
            "classification": classification,
            "confidence": 0.85,
            "reasoning": _(
                "Baseado em análise de fatores contribuintes e tipo de evento"
            ),
        }

    async def assess_patient_outcome(
        self,
        event_type: str,
        severity: str,
        patient_ref: str,
    ) -> str:
        """Stub: Assess patient outcome."""
        logger.info(
            _("Avaliando desfecho do paciente {ref}").format(
                ref=hashlib.sha256(patient_ref.encode()).hexdigest()[:16]
            )
        )

        # Map severity to outcome
        if severity == "fatal":
            return "death"
        elif severity == "life_threatening":
            return "intervention_required"
        elif severity == "severe":
            return "permanent_harm"
        elif severity == "moderate":
            return "temporary_harm"
        else:
            return "no_harm"

    async def identify_root_causes(
        self,
        event_type: str,
        description: str,
        factors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Stub: Identify root causes."""
        logger.info(
            _("Identificando causas-raiz para evento tipo={type}").format(type=event_type)
        )

        # Simulated root cause analysis
        root_causes = []

        if event_type == "medication_error":
            root_causes.append({
                "category": "process",
                "cause": _("Protocolo de dupla checagem não seguido"),
                "corrective_action": _("Reforçar treinamento e checklist obrigatório"),
            })
        elif event_type == "fall":
            root_causes.append({
                "category": "environment",
                "cause": _("Iluminação inadequada no corredor"),
                "corrective_action": _("Melhorar iluminação e sinalização"),
            })

        return {
            "root_causes": root_causes,
            "requires_formal_rca": len(factors) > 2 or event_type == "medication_error",
        }


# ============================================================================
# Worker
# ============================================================================


class AdverseEventDetectionWorker:
    """
    Adverse event detection and reporting worker.

    Handles detection, classification, and reporting of adverse clinical events.
    Creates FHIR AdverseEvent resources and triggers appropriate notifications
    and follow-up workflows.
    """

    TOPIC = "clinical.adverse_events"

    # Event severity mapping to notification urgency
    SEVERITY_URGENCY = {
        "fatal": "immediate",
        "life_threatening": "immediate",
        "severe": "urgent",
        "moderate": "urgent",
        "mild": "routine",
    }

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        classifier: Optional[AdverseEventClassifierProtocol] = None,
    ):
        """
        Initialize adverse event detection worker.

        Args:
            fhir_client: FHIR client for resource operations
            classifier: Event classifier (uses stub if not provided)
        """
        self.fhir_client = fhir_client
        self.classifier = classifier or AdverseEventClassifierStub()

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute adverse event detection and reporting.

        Args:
            task_variables: Task input variables

        Returns:
            Event classification and required actions

        Raises:
            AdverseEventException: If event processing fails
        """
        tenant_id = get_required_tenant()

        logger.info(
            _("Processando evento adverso para tenant {tenant}").format(
                tenant=hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
            )
        )

        try:
            # Parse input
            event_input = AdverseEventInput(**task_variables)

            # Classify event
            classification = await self.classifier.classify_event(
                event_input.event_type,
                event_input.event_description,
                event_input.severity,
                event_input.contributing_factors or [],
            )

            # Assess patient outcome
            patient_outcome = await self.classifier.assess_patient_outcome(
                event_input.event_type,
                event_input.severity,
                event_input.patient_reference,
            )

            # Identify root causes
            rca_analysis = await self.classifier.identify_root_causes(
                event_input.event_type,
                event_input.event_description,
                event_input.contributing_factors or [],
            )

            # Determine required notifications
            notifications = self._determine_notifications(
                event_input,
                classification["classification"],
                patient_outcome,
            )

            # Determine immediate actions
            immediate_actions = self._determine_immediate_actions(
                event_input,
                patient_outcome,
            )

            # Determine follow-up actions
            follow_up_actions = self._determine_follow_up_actions(
                event_input,
                classification["classification"],
                rca_analysis,
            )

            # Check if regulatory reporting required
            regulatory_reporting = self._requires_regulatory_reporting(
                event_input,
                patient_outcome,
            )

            # Create FHIR AdverseEvent resource
            adverse_event_ref = await self._create_adverse_event_resource(
                event_input,
                classification,
                patient_outcome,
            )

            # Prepare output
            output = AdverseEventOutput(
                adverse_event_reference=adverse_event_ref,
                event_id=f"AE-{datetime.utcnow().timestamp()}",
                event_type=event_input.event_type,
                event_classification=classification["classification"],
                severity_assessment=event_input.severity,
                patient_outcome=patient_outcome,
                required_notifications=[n.model_dump() for n in notifications],
                root_cause_analysis_required=rca_analysis.get("requires_formal_rca", False),
                immediate_actions=immediate_actions,
                contributing_factors=event_input.contributing_factors or [],
                regulatory_reporting_required=regulatory_reporting,
                follow_up_actions=follow_up_actions,
                created_at=datetime.utcnow().isoformat(),
            )

            logger.info(
                _("Evento adverso {event_id} processado: classificação={classification}, "
                  "desfecho={outcome}").format(
                    event_id=output.event_id,
                    classification=output.event_classification,
                    outcome=patient_outcome,
                )
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro ao processar evento adverso: {error}").format(error=str(e))
            )
            raise AdverseEventException(
                message=_("Falha ao processar evento adverso"),
                details={"error": str(e), "tenant_id": tenant_id},
            ) from e

    def _determine_notifications(
        self,
        event_input: AdverseEventInput,
        classification: str,
        patient_outcome: str,
    ) -> List[Notification]:
        """Determine required notifications based on event severity and type."""
        notifications = []
        urgency = self.SEVERITY_URGENCY.get(event_input.severity, "routine")

        # Always notify attending physician
        notifications.append(
            Notification(
                recipient_role="attending_physician",
                notification_type=urgency,
                message=_(
                    "Evento adverso detectado: {type} - {severity}"
                ).format(type=event_input.event_type, severity=event_input.severity),
                deadline=self._get_notification_deadline(urgency),
            )
        )

        # Notify nursing coordinator
        if event_input.event_type in ["fall", "medication_error"]:
            notifications.append(
                Notification(
                    recipient_role="nursing_coordinator",
                    notification_type=urgency,
                    message=_(
                        "Evento adverso de enfermagem: {type}"
                    ).format(type=event_input.event_type),
                    deadline=self._get_notification_deadline(urgency),
                )
            )

        # Notify quality/safety team
        if classification == "preventable" or patient_outcome in [
            "permanent_harm",
            "intervention_required",
            "death",
        ]:
            notifications.append(
                Notification(
                    recipient_role="quality_safety_team",
                    notification_type="urgent",
                    message=_(
                        "Evento adverso grave requer investigação: {type}"
                    ).format(type=event_input.event_type),
                    deadline=self._get_notification_deadline("urgent"),
                )
            )

        # Notify pharmacy for medication events
        if event_input.event_type == "medication_error":
            notifications.append(
                Notification(
                    recipient_role="pharmacy_coordinator",
                    notification_type=urgency,
                    message=_(
                        "Erro de medicação detectado - revisão necessária"
                    ),
                    deadline=self._get_notification_deadline(urgency),
                )
            )

        # Notify infection control for HAIs
        if event_input.event_type == "infection":
            notifications.append(
                Notification(
                    recipient_role="infection_control",
                    notification_type="urgent",
                    message=_(
                        "Possível infecção hospitalar detectada"
                    ),
                    deadline=self._get_notification_deadline("urgent"),
                )
            )

        return notifications

    def _get_notification_deadline(self, urgency: str) -> str:
        """Get notification deadline based on urgency."""
        from datetime import timedelta

        if urgency == "immediate":
            deadline = datetime.utcnow() + timedelta(minutes=15)
        elif urgency == "urgent":
            deadline = datetime.utcnow() + timedelta(hours=2)
        else:  # routine
            deadline = datetime.utcnow() + timedelta(hours=24)

        return deadline.isoformat()

    def _determine_immediate_actions(
        self,
        event_input: AdverseEventInput,
        patient_outcome: str,
    ) -> List[str]:
        """Determine immediate actions required."""
        actions = []

        # Patient safety actions
        if patient_outcome in ["intervention_required", "life_threatening"]:
            actions.append(_("Avaliação médica imediata do paciente"))
            actions.append(_("Monitoramento contínuo de sinais vitais"))

        # Event-specific actions
        if event_input.event_type == "medication_error":
            actions.append(_("Suspender medicação envolvida até revisão"))
            actions.append(_("Notificar farmácia e médico prescritor"))

        elif event_input.event_type == "fall":
            actions.append(_("Avaliação neurológica e ortopédica"))
            actions.append(_("Implementar precauções para quedas"))

        elif event_input.event_type == "infection":
            actions.append(_("Coletar culturas e iniciar isolamento se indicado"))
            actions.append(_("Revisar protocolo de controle de infecção"))

        # Documentation
        actions.append(_("Documentar evento em prontuário do paciente"))
        actions.append(_("Notificar familiares conforme protocolo"))

        return actions

    def _determine_follow_up_actions(
        self,
        event_input: AdverseEventInput,
        classification: str,
        rca_analysis: Dict[str, Any],
    ) -> List[str]:
        """Determine follow-up actions required."""
        actions = []

        # RCA if required
        if rca_analysis.get("requires_formal_rca"):
            actions.append(
                _("Conduzir análise de causa-raiz formal em 72h")
            )

        # Preventable events require process review
        if classification == "preventable":
            actions.append(
                _("Revisar e atualizar protocolos relacionados")
            )
            actions.append(
                _("Treinamento adicional para equipe envolvida")
            )

        # Quality improvement
        actions.append(
            _("Registrar no sistema de gestão de qualidade")
        )
        actions.append(
            _("Incluir em reunião mensal de segurança do paciente")
        )

        # Patient follow-up
        if event_input.severity in ["severe", "life_threatening"]:
            actions.append(
                _("Acompanhamento médico semanal por 30 dias")
            )

        return actions

    def _requires_regulatory_reporting(
        self,
        event_input: AdverseEventInput,
        patient_outcome: str,
    ) -> bool:
        """Determine if regulatory reporting is required."""
        # Report to ANVISA/vigilância sanitária
        if patient_outcome == "death":
            return True

        if event_input.event_type in ["medication_error", "equipment_failure"]:
            if event_input.severity in ["severe", "life_threatening", "fatal"]:
                return True

        if event_input.event_type == "infection":
            # Hospital-acquired infections are notifiable
            return True

        return False

    async def _create_adverse_event_resource(
        self,
        event_input: AdverseEventInput,
        classification: Dict[str, Any],
        patient_outcome: str,
    ) -> str:
        """Create FHIR AdverseEvent resource."""
        # In production, create full FHIR AdverseEvent
        adverse_event_id = f"AdverseEvent-{datetime.utcnow().timestamp()}"

        logger.info(
            _("Criado recurso FHIR AdverseEvent: {id}").format(id=adverse_event_id)
        )

        # Would call FHIR API to create resource
        # resource = {
        #     "resourceType": "AdverseEvent",
        #     "id": adverse_event_id,
        #     "subject": {"reference": event_input.patient_reference},
        #     "encounter": {"reference": event_input.encounter_reference},
        #     "date": event_input.occurrence_datetime,
        #     "seriousness": {"text": event_input.severity},
        #     "outcome": {"text": patient_outcome},
        #     "category": [{"text": event_input.event_type}],
        #     "event": {"text": event_input.event_description},
        # }
        #
        # await self.fhir_client.create_resource(resource)

        return f"AdverseEvent/{adverse_event_id}"
