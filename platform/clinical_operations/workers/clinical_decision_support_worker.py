"""
Clinical Decision Support Worker - Evidence-based clinical decision support.

TOPIC: clinical.decision_support

This worker provides clinical decision support including:
- Drug interaction checking
- Allergy alerts
- Evidence-based treatment recommendations
- Clinical guideline suggestions
- Diagnostic support
- Laboratory result interpretation
- Risk stratification

Integrates with clinical knowledge bases and evidence repositories.

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


class ClinicalDecisionSupportException(DomainException):
    """Exception for clinical decision support errors."""
    bpmn_error_code: str = "CLINICAL_DECISION_SUPPORT_ERROR"


# ============================================================================
# Input/Output DTOs
# ============================================================================


class ClinicalAlert(BaseModel):
    """Clinical alert from decision support."""

    alert_id: str = Field(description="Unique alert identifier")
    alert_type: str = Field(
        description="drug_interaction/allergy/contraindication/critical_value/best_practice"
    )
    severity: str = Field(description="critical/high/medium/low/info")
    title: str = Field(description="Alert title")
    message: str = Field(description="Detailed alert message")
    affected_items: List[str] = Field(description="Affected medications, labs, etc.")
    recommendation: str = Field(description="Recommended action")
    evidence_level: str = Field(description="A/B/C/D/Expert_opinion")
    dismissible: bool = Field(description="Whether alert can be dismissed")
    requires_override: bool = Field(description="Whether override documentation required")


class ClinicalRecommendation(BaseModel):
    """Clinical recommendation from decision support."""

    recommendation_id: str = Field(description="Unique recommendation identifier")
    category: str = Field(
        description="diagnosis/treatment/monitoring/prevention/referral"
    )
    title: str = Field(description="Recommendation title")
    description: str = Field(description="Detailed recommendation")
    confidence_score: float = Field(description="0-1 confidence score")
    evidence_references: List[str] = Field(description="Supporting evidence URLs/DOIs")
    guideline_source: Optional[str] = Field(None, description="Guideline source")
    applicability_criteria: List[str] = Field(
        description="When recommendation applies"
    )


class ClinicalContext(BaseModel):
    """Clinical context for decision support."""

    diagnosis_codes: Optional[List[str]] = Field(
        default_factory=list,
        description="CID-10 diagnosis codes"
    )
    medications: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Current medications"
    )
    allergies: Optional[List[str]] = Field(
        default_factory=list,
        description="Known allergies"
    )
    lab_results: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Recent lab results"
    )
    vital_signs: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Recent vital signs"
    )
    procedures: Optional[List[str]] = Field(
        default_factory=list,
        description="Recent procedures"
    )
    age_years: Optional[int] = Field(None, description="Patient age")
    pregnancy_status: Optional[bool] = Field(None, description="Pregnancy status")
    renal_function: Optional[str] = Field(None, description="normal/mild/moderate/severe")
    hepatic_function: Optional[str] = Field(None, description="normal/mild/moderate/severe")


class ClinicalDecisionSupportInput(BaseModel):
    """Input for clinical decision support."""

    encounter_reference: str = Field(description="Encounter/episode-123")
    patient_reference: str = Field(description="Patient/patient-123")
    clinical_context: ClinicalContext = Field(description="Clinical context")
    decision_type: str = Field(
        description="drug_safety/diagnostic/treatment/risk_assessment/all"
    )
    trigger_event: Optional[str] = Field(
        None,
        description="new_medication/new_diagnosis/lab_result/order_entry"
    )

    def to_variables(self) -> Dict[str, Any]:
        """Convert to process variables."""
        return {
            "encounter_reference": self.encounter_reference,
            "patient_reference": self.patient_reference,
            "clinical_context": self.clinical_context.model_dump(),
            "decision_type": self.decision_type,
            "trigger_event": self.trigger_event,
        }


class ClinicalDecisionSupportOutput(BaseModel):
    """Output from clinical decision support."""

    support_session_id: str = Field(description="Unique session identifier")
    encounter_reference: str = Field(description="Related encounter")
    decision_type: str = Field(description="Type of decision support")
    alerts: List[Dict[str, Any]] = Field(description="Clinical alerts")
    recommendations: List[Dict[str, Any]] = Field(description="Clinical recommendations")
    critical_alerts_count: int = Field(description="Number of critical alerts")
    evidence_references: List[str] = Field(description="All evidence references")
    confidence_scores: Dict[str, float] = Field(
        description="Confidence scores by category"
    )
    requires_physician_review: bool = Field(
        description="Whether physician review is required"
    )
    generated_at: str = Field(description="ISO 8601 timestamp")

    def to_variables(self) -> Dict[str, Any]:
        """Convert to process variables."""
        return {
            "support_session_id": self.support_session_id,
            "encounter_reference": self.encounter_reference,
            "decision_type": self.decision_type,
            "alerts": self.alerts,
            "recommendations": self.recommendations,
            "critical_alerts_count": self.critical_alerts_count,
            "evidence_references": self.evidence_references,
            "confidence_scores": self.confidence_scores,
            "requires_physician_review": self.requires_physician_review,
            "generated_at": self.generated_at,
        }


# ============================================================================
# Protocols
# ============================================================================


class DecisionSupportEngineProtocol(ABC):
    """Protocol for clinical decision support engine."""

    @abstractmethod
    async def check_drug_interactions(
        self,
        medications: List[Dict[str, Any]],
        patient_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Check for drug-drug interactions."""
        pass

    @abstractmethod
    async def check_allergies(
        self,
        medications: List[Dict[str, Any]],
        allergies: List[str],
    ) -> List[Dict[str, Any]]:
        """Check for allergy contraindications."""
        pass

    @abstractmethod
    async def check_contraindications(
        self,
        medications: List[Dict[str, Any]],
        patient_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Check for contraindications."""
        pass

    @abstractmethod
    async def generate_treatment_recommendations(
        self,
        diagnoses: List[str],
        patient_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Generate evidence-based treatment recommendations."""
        pass

    @abstractmethod
    async def assess_diagnostic_support(
        self,
        symptoms: List[str],
        lab_results: List[Dict[str, Any]],
        patient_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Provide diagnostic decision support."""
        pass


class DecisionSupportEngineStub(DecisionSupportEngineProtocol):
    """Stub implementation of decision support engine."""

    async def check_drug_interactions(
        self,
        medications: List[Dict[str, Any]],
        patient_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Stub: Check drug interactions."""
        logger.info(
            _("Verificando interações medicamentosas para {count} medicamentos").format(
                count=len(medications)
            )
        )

        alerts = []

        # Simulate interaction check
        if len(medications) >= 2:
            alerts.append({
                "type": "drug_interaction",
                "severity": "high",
                "title": _("Interação medicamentosa detectada"),
                "message": _(
                    "Interação entre {drug1} e {drug2}: risco de prolongamento QT"
                ).format(
                    drug1=medications[0].get("code", "medicamento 1"),
                    drug2=medications[1].get("code", "medicamento 2"),
                ),
                "affected_items": [
                    medications[0].get("code"),
                    medications[1].get("code"),
                ],
                "recommendation": _(
                    "Monitorar ECG e considerar medicação alternativa"
                ),
                "evidence_level": "A",
            })

        # Check renal function for dose adjustment
        if patient_context.renal_function in ["moderate", "severe"]:
            alerts.append({
                "type": "best_practice",
                "severity": "medium",
                "title": _("Ajuste de dose para função renal"),
                "message": _(
                    "Função renal {status} - considerar ajuste de dose"
                ).format(status=patient_context.renal_function),
                "affected_items": [m.get("code") for m in medications],
                "recommendation": _("Revisar doses conforme clearance de creatinina"),
                "evidence_level": "A",
            })

        return alerts

    async def check_allergies(
        self,
        medications: List[Dict[str, Any]],
        allergies: List[str],
    ) -> List[Dict[str, Any]]:
        """Stub: Check allergies."""
        logger.info(
            _("Verificando alergias: {count} medicamentos, {allergy_count} alergias").format(
                count=len(medications),
                allergy_count=len(allergies),
            )
        )

        alerts = []

        # Simulate allergy check
        for med in medications:
            med_code = med.get("code", "")
            if "penicilina" in allergies and "amoxicilina" in med_code.lower():
                alerts.append({
                    "type": "allergy",
                    "severity": "critical",
                    "title": _("ALERTA DE ALERGIA"),
                    "message": _(
                        "Paciente alérgico a penicilina - prescrição de {drug}"
                    ).format(drug=med_code),
                    "affected_items": [med_code],
                    "recommendation": _("SUSPENDER medicação e prescrever alternativa"),
                    "evidence_level": "A",
                })

        return alerts

    async def check_contraindications(
        self,
        medications: List[Dict[str, Any]],
        patient_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Stub: Check contraindications."""
        logger.info(_("Verificando contraindicações"))

        alerts = []

        # Pregnancy contraindications
        if patient_context.pregnancy_status:
            alerts.append({
                "type": "contraindication",
                "severity": "critical",
                "title": _("Contraindicação em gestação"),
                "message": _(
                    "Medicamento contraindicado em gestação - risco categoria D/X"
                ),
                "affected_items": [m.get("code") for m in medications],
                "recommendation": _("Substituir por alternativa segura na gestação"),
                "evidence_level": "A",
            })

        return alerts

    async def generate_treatment_recommendations(
        self,
        diagnoses: List[str],
        patient_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Stub: Generate treatment recommendations."""
        logger.info(
            _("Gerando recomendações de tratamento para {count} diagnósticos").format(
                count=len(diagnoses)
            )
        )

        recommendations = []

        # Simulate guideline-based recommendations
        for diagnosis in diagnoses:
            if "I10" in diagnosis:  # Hypertension
                recommendations.append({
                    "category": "treatment",
                    "title": _("Tratamento de hipertensão arterial"),
                    "description": _(
                        "Iniciar terapia anti-hipertensiva conforme diretrizes brasileiras"
                    ),
                    "confidence_score": 0.92,
                    "evidence_references": [
                        "https://doi.org/10.1590/abc.2021.0123",
                    ],
                    "guideline_source": "Diretriz Brasileira de Hipertensão 2020",
                    "applicability_criteria": [
                        _("PA ≥ 140/90 mmHg"),
                        _("Sem contraindicações"),
                    ],
                })

        return recommendations

    async def assess_diagnostic_support(
        self,
        symptoms: List[str],
        lab_results: List[Dict[str, Any]],
        patient_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Stub: Provide diagnostic support."""
        logger.info(_("Avaliando suporte diagnóstico"))

        recommendations = []

        # Simulate diagnostic suggestions
        recommendations.append({
            "category": "diagnosis",
            "title": _("Considerar diagnóstico diferencial"),
            "description": _(
                "Sintomas compatíveis com múltiplas condições - investigação adicional"
            ),
            "confidence_score": 0.75,
            "evidence_references": [],
            "applicability_criteria": [
                _("Sintomas presentes por > 7 dias"),
            ],
        })

        return recommendations


# ============================================================================
# Worker
# ============================================================================


class ClinicalDecisionSupportWorker:
    """
    Clinical decision support worker.

    Provides evidence-based clinical decision support including drug safety
    checking, treatment recommendations, diagnostic support, and risk assessment.
    """

    TOPIC = "clinical.decision_support"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        decision_engine: Optional[DecisionSupportEngineProtocol] = None,
    ):
        """
        Initialize clinical decision support worker.

        Args:
            fhir_client: FHIR client for resource access
            decision_engine: Decision support engine (uses stub if not provided)
        """
        self.fhir_client = fhir_client
        self.decision_engine = decision_engine or DecisionSupportEngineStub()

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute clinical decision support.

        Args:
            task_variables: Task input variables

        Returns:
            Clinical alerts and recommendations

        Raises:
            ClinicalDecisionSupportException: If decision support fails
        """
        tenant_id = get_required_tenant()

        logger.info(
            _("Executando suporte à decisão clínica para tenant {tenant}").format(
                tenant=hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
            )
        )

        try:
            # Parse input
            cds_input = ClinicalDecisionSupportInput(**task_variables)

            # Collect all alerts and recommendations
            all_alerts = []
            all_recommendations = []
            evidence_refs = []

            # Drug safety checks
            if cds_input.decision_type in ["drug_safety", "all"]:
                drug_alerts = await self._check_drug_safety(
                    cds_input.clinical_context
                )
                all_alerts.extend(drug_alerts)

            # Treatment recommendations
            if cds_input.decision_type in ["treatment", "all"]:
                treatment_recs = await self._generate_treatment_recommendations(
                    cds_input.clinical_context
                )
                all_recommendations.extend(treatment_recs)

            # Diagnostic support
            if cds_input.decision_type in ["diagnostic", "all"]:
                diagnostic_recs = await self._provide_diagnostic_support(
                    cds_input.clinical_context
                )
                all_recommendations.extend(diagnostic_recs)

            # Risk assessment
            if cds_input.decision_type in ["risk_assessment", "all"]:
                risk_alerts = await self._assess_clinical_risks(
                    cds_input.clinical_context
                )
                all_alerts.extend(risk_alerts)

            # Count critical alerts
            critical_count = sum(
                1 for alert in all_alerts if alert.get("severity") == "critical"
            )

            # Collect evidence references
            for rec in all_recommendations:
                evidence_refs.extend(rec.get("evidence_references", []))

            # Calculate confidence scores by category
            confidence_scores = self._calculate_confidence_scores(all_recommendations)

            # Determine if physician review required
            requires_review = critical_count > 0 or any(
                alert.get("requires_override", False) for alert in all_alerts
            )

            # Prepare output
            output = ClinicalDecisionSupportOutput(
                support_session_id=f"CDS-{datetime.utcnow().timestamp()}",
                encounter_reference=cds_input.encounter_reference,
                decision_type=cds_input.decision_type,
                alerts=all_alerts,
                recommendations=all_recommendations,
                critical_alerts_count=critical_count,
                evidence_references=list(set(evidence_refs)),
                confidence_scores=confidence_scores,
                requires_physician_review=requires_review,
                generated_at=datetime.utcnow().isoformat(),
            )

            logger.info(
                _("Suporte à decisão gerado: {alerts} alertas, {recs} recomendações").format(
                    alerts=len(all_alerts),
                    recs=len(all_recommendations),
                )
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro no suporte à decisão clínica: {error}").format(error=str(e))
            )
            raise ClinicalDecisionSupportException(
                message=_("Falha ao executar suporte à decisão clínica"),
                details={"error": str(e), "tenant_id": tenant_id},
            ) from e

    async def _check_drug_safety(
        self,
        clinical_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Check drug safety (interactions, allergies, contraindications)."""
        alerts = []

        medications = clinical_context.medications or []

        # Check drug-drug interactions
        if len(medications) > 1:
            interaction_alerts = await self.decision_engine.check_drug_interactions(
                medications,
                clinical_context,
            )
            alerts.extend(interaction_alerts)

        # Check allergies
        if clinical_context.allergies:
            allergy_alerts = await self.decision_engine.check_allergies(
                medications,
                clinical_context.allergies,
            )
            alerts.extend(allergy_alerts)

        # Check contraindications
        contraindication_alerts = await self.decision_engine.check_contraindications(
            medications,
            clinical_context,
        )
        alerts.extend(contraindication_alerts)

        return alerts

    async def _generate_treatment_recommendations(
        self,
        clinical_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Generate evidence-based treatment recommendations."""
        recommendations = []

        if clinical_context.diagnosis_codes:
            treatment_recs = await self.decision_engine.generate_treatment_recommendations(
                clinical_context.diagnosis_codes,
                clinical_context,
            )
            recommendations.extend(treatment_recs)

        return recommendations

    async def _provide_diagnostic_support(
        self,
        clinical_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Provide diagnostic decision support."""
        recommendations = []

        # In production, extract symptoms from clinical notes
        symptoms = []

        diagnostic_recs = await self.decision_engine.assess_diagnostic_support(
            symptoms,
            clinical_context.lab_results or [],
            clinical_context,
        )
        recommendations.extend(diagnostic_recs)

        return recommendations

    async def _assess_clinical_risks(
        self,
        clinical_context: ClinicalContext,
    ) -> List[Dict[str, Any]]:
        """Assess clinical risks (VTE, falls, pressure ulcers, etc.)."""
        alerts = []

        # Example: VTE risk assessment
        if clinical_context.age_years and clinical_context.age_years > 65:
            alerts.append({
                "type": "best_practice",
                "severity": "medium",
                "title": _("Avaliação de risco de TEV"),
                "message": _(
                    "Paciente com idade > 65 anos - considerar profilaxia para TEV"
                ),
                "affected_items": [],
                "recommendation": _(
                    "Aplicar escore de Padua/Wells e considerar profilaxia farmacológica"
                ),
                "evidence_level": "A",
            })

        return alerts

    def _calculate_confidence_scores(
        self,
        recommendations: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Calculate average confidence scores by category."""
        scores_by_category = {}

        for rec in recommendations:
            category = rec.get("category", "other")
            score = rec.get("confidence_score", 0.0)

            if category not in scores_by_category:
                scores_by_category[category] = []

            scores_by_category[category].append(score)

        # Average scores
        return {
            category: sum(scores) / len(scores)
            for category, scores in scores_by_category.items()
        }
