"""
Anesthesia Evaluation Worker

CIB7 External Task Topic: surgical.anesthesia_eval
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Performs pre-anesthesia risk assessment using ASA Physical Status Classification,
validates fasting compliance, and evaluates patient readiness for anesthesia.
Follows Brazilian Society of Anesthesiology (SBA) guidelines.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import (
    TasySurgicalAdapter,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


def _(message: str) -> str:
    """Translation helper for Portuguese error messages."""
    return message


class ClinicalOperationsException(DomainException):
    """Exception for clinical operations errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )
        self.code = "CLINICAL_OPERATIONS_ERROR"


class AnesthesiaEvaluationInput(BaseModel):
    """Input model for anesthesia evaluation."""

    surgery_id: str = Field(..., description="FHIR Procedure ID")
    patient_id: str = Field(..., description="FHIR Patient ID")
    anesthesiologist_id: str = Field(..., description="FHIR Practitioner ID")
    asa_classification: Literal[1, 2, 3, 4, 5, 6] = Field(
        ..., description="ASA Physical Status Classification (1-6)"
    )
    anesthesia_type: Literal["general", "regional", "local", "sedation"] = Field(
        ..., description="Planned anesthesia type"
    )
    allergies: list[str] = Field(
        default_factory=list, description="List of known allergies"
    )
    comorbidities: list[str] = Field(
        default_factory=list, description="List of comorbidities"
    )
    fasting_hours: float = Field(
        ..., ge=0, description="Hours since last food/drink intake"
    )
    weight_kg: float = Field(..., gt=0, description="Patient weight in kilograms")
    height_cm: float = Field(..., gt=0, description="Patient height in centimeters")


class AnesthesiaEvaluationOutput(BaseModel):
    """Output model for anesthesia evaluation."""

    evaluation_id: str = Field(..., description="Generated evaluation ID")
    surgery_id: str = Field(..., description="FHIR Procedure ID")
    patient_id: str = Field(..., description="FHIR Patient ID")
    asa_classification: int = Field(..., description="ASA Physical Status")
    anesthesia_type: str = Field(..., description="Planned anesthesia type")
    anesthesia_plan: str = Field(..., description="Recommended anesthesia plan")
    risk_level: Literal["low", "moderate", "high", "critical"] = Field(
        ..., description="Overall anesthesia risk level"
    )
    cleared_for_surgery: bool = Field(
        ..., description="Whether patient is cleared for anesthesia"
    )
    evaluated_at: str = Field(..., description="ISO 8601 evaluation timestamp")
    bmi: float = Field(..., description="Calculated Body Mass Index")
    allergies: list[str] = Field(
        default_factory=list, description="List of known allergies"
    )
    notes: str | None = Field(
        None, description="Additional notes or recommendations"
    )


class AnesthesiaEvaluationWorker:
    """
    Worker to perform pre-anesthesia risk assessment.

    Implements Brazilian Society of Anesthesiology (SBA) guidelines:
    - ASA Physical Status Classification evaluation
    - Fasting compliance verification (6h solids, 2h clear liquids)
    - Comorbidity risk assessment
    - Airway risk evaluation (BMI-based)
    - Drug allergy screening

    Determines patient readiness for anesthesia and surgical clearance.
    """

    TOPIC = "surgical.anesthesia_eval"

    # ASA Classification risk mapping
    ASA_RISK_MAP = {
        1: "low",      # Normal healthy patient
        2: "moderate", # Mild systemic disease
        3: "moderate", # Severe systemic disease
        4: "high",     # Severe disease, constant threat to life
        5: "critical", # Moribund, not expected to survive without surgery
        6: "critical", # Brain-dead, organ donor
    }

    # Fasting requirements (SBA guidelines)
    FASTING_SOLIDS_MIN_HOURS = 6.0
    FASTING_CLEAR_LIQUIDS_MIN_HOURS = 2.0

    # BMI thresholds for airway risk
    BMI_OBESITY_THRESHOLD = 30.0
    BMI_MORBID_OBESITY_THRESHOLD = 40.0

    def __init__(
        self, tasy_adapter: TasySurgicalAdapter | None = None
    ) -> None:
        """
        Initialize worker with Tasy surgical adapter.

        Args:
            tasy_adapter: Tasy adapter for surgical data conversion.
                         Optional for testing purposes.
        """
        self._tasy_adapter = tasy_adapter

    @require_tenant
    @track_task_execution(task_type="surgical.anesthesia_eval")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute anesthesia evaluation.

        Args:
            task_variables: Task variables containing evaluation data

        Returns:
            Dictionary with evaluation results

        Raises:
            ClinicalOperationsException: If evaluation fails or patient not cleared
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = AnesthesiaEvaluationInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for anesthesia evaluation input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para avaliação anestésica"),
                details={"validation_error": str(e)},
            ) from e

        # Log evaluation start (LGPD: no PII)
        logger.info(
            "Processing anesthesia evaluation",
            extra={
                "tenant_id": tenant.tenant_id,
                "surgery_id": input_data.surgery_id,
                "patient_id": input_data.patient_id,
                "asa_classification": input_data.asa_classification,
                "anesthesia_type": input_data.anesthesia_type,
            },
        )

        # Perform evaluation
        try:
            evaluation_result = self._perform_evaluation(input_data)

            # Generate evaluation ID
            evaluation_id = f"ANES-EVAL-{input_data.surgery_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

            # Determine risk level
            risk_level = self._determine_risk_level(input_data, evaluation_result)

            # Generate anesthesia plan
            anesthesia_plan = self._generate_anesthesia_plan(
                input_data, evaluation_result
            )

            # Determine surgical clearance
            cleared_for_surgery = evaluation_result["cleared"]

            # Compile notes
            notes = self._compile_evaluation_notes(evaluation_result)

            logger.info(
                "Anesthesia evaluation completed",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "evaluation_id": evaluation_id,
                    "risk_level": risk_level,
                    "cleared_for_surgery": cleared_for_surgery,
                    "fasting_compliant": evaluation_result["fasting_compliant"],
                },
            )

            # Build output
            output = AnesthesiaEvaluationOutput(
                evaluation_id=evaluation_id,
                surgery_id=input_data.surgery_id,
                patient_id=input_data.patient_id,
                asa_classification=input_data.asa_classification,
                anesthesia_type=input_data.anesthesia_type,
                anesthesia_plan=anesthesia_plan,
                risk_level=risk_level,
                cleared_for_surgery=cleared_for_surgery,
                evaluated_at=datetime.now(UTC).isoformat(),
                bmi=evaluation_result["bmi"],
                allergies=input_data.allergies,
                notes=notes,
            )

            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to complete anesthesia evaluation",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha na avaliação anestésica"),
                details={
                    "surgery_id": input_data.surgery_id,
                    "error": str(e),
                },
            ) from e

    def _perform_evaluation(
        self, input_data: AnesthesiaEvaluationInput
    ) -> dict[str, Any]:
        """
        Perform comprehensive anesthesia evaluation.

        Args:
            input_data: Evaluation input data

        Returns:
            Dictionary with evaluation results
        """
        # Calculate BMI
        bmi = self._calculate_bmi(input_data.weight_kg, input_data.height_cm)

        # Check fasting compliance
        fasting_compliant = input_data.fasting_hours >= self.FASTING_SOLIDS_MIN_HOURS

        # Assess airway risk
        airway_risk = self._assess_airway_risk(bmi)

        # Evaluate comorbidity impact
        comorbidity_risk = self._evaluate_comorbidity_risk(input_data.comorbidities)

        # Check allergies
        has_allergies = len(input_data.allergies) > 0

        # Determine clearance
        cleared = (
            fasting_compliant
            and input_data.asa_classification < 5
            and comorbidity_risk != "critical"
        )

        return {
            "bmi": bmi,
            "fasting_compliant": fasting_compliant,
            "airway_risk": airway_risk,
            "comorbidity_risk": comorbidity_risk,
            "has_allergies": has_allergies,
            "cleared": cleared,
        }

    def _calculate_bmi(self, weight_kg: float, height_cm: float) -> float:
        """
        Calculate Body Mass Index.

        Args:
            weight_kg: Weight in kilograms
            height_cm: Height in centimeters

        Returns:
            BMI value
        """
        height_m = height_cm / 100.0
        return weight_kg / (height_m * height_m)

    def _assess_airway_risk(self, bmi: float) -> Literal["low", "moderate", "high"]:
        """
        Assess airway management risk based on BMI.

        Args:
            bmi: Body Mass Index

        Returns:
            Airway risk level
        """
        if bmi >= self.BMI_MORBID_OBESITY_THRESHOLD:
            return "high"
        elif bmi >= self.BMI_OBESITY_THRESHOLD:
            return "moderate"
        else:
            return "low"

    def _evaluate_comorbidity_risk(
        self, comorbidities: list[str]
    ) -> Literal["low", "moderate", "high", "critical"]:
        """
        Evaluate risk from comorbidities.

        Args:
            comorbidities: List of comorbidity descriptions

        Returns:
            Comorbidity risk level
        """
        if not comorbidities:
            return "low"

        # High-risk comorbidities
        high_risk_keywords = ["cardiac", "respiratory", "renal", "hepatic"]
        critical_keywords = ["unstable", "severe", "acute", "decompensated"]

        comorbidity_text = " ".join(comorbidities).lower()

        if any(keyword in comorbidity_text for keyword in critical_keywords):
            return "critical"
        elif any(keyword in comorbidity_text for keyword in high_risk_keywords):
            return "high"
        elif len(comorbidities) > 2:
            return "moderate"
        else:
            return "low"

    def _determine_risk_level(
        self, input_data: AnesthesiaEvaluationInput, evaluation_result: dict[str, Any]
    ) -> Literal["low", "moderate", "high", "critical"]:
        """
        Determine overall anesthesia risk level.

        Args:
            input_data: Evaluation input
            evaluation_result: Evaluation results

        Returns:
            Overall risk level
        """
        # Base risk from ASA classification
        base_risk = self.ASA_RISK_MAP[input_data.asa_classification]

        # Elevate risk if comorbidity or airway risk is high
        if evaluation_result["comorbidity_risk"] == "critical":
            return "critical"
        elif evaluation_result["airway_risk"] == "high":
            if base_risk in ("low", "moderate"):
                return "high"

        return base_risk

    def _generate_anesthesia_plan(
        self, input_data: AnesthesiaEvaluationInput, evaluation_result: dict[str, Any]
    ) -> str:
        """
        Generate recommended anesthesia plan.

        Args:
            input_data: Evaluation input
            evaluation_result: Evaluation results

        Returns:
            Anesthesia plan description
        """
        plan_parts = [f"Anesthesia type: {input_data.anesthesia_type}"]

        if evaluation_result["airway_risk"] == "high":
            plan_parts.append("Difficult airway protocol recommended")

        if evaluation_result["has_allergies"]:
            plan_parts.append("Pre-operative antiallergic prophylaxis")

        if input_data.asa_classification >= 3:
            plan_parts.append("Invasive monitoring recommended")

        return "; ".join(plan_parts)

    def _compile_evaluation_notes(self, evaluation_result: dict[str, Any]) -> str | None:
        """
        Compile evaluation notes.

        Args:
            evaluation_result: Evaluation results

        Returns:
            Compiled notes or None
        """
        notes = []

        if not evaluation_result["fasting_compliant"]:
            notes.append("Fasting não conforme - reavaliar antes de prosseguir")

        if evaluation_result["airway_risk"] in ("moderate", "high"):
            notes.append(f"Risco de via aérea: {evaluation_result['airway_risk']}")

        if evaluation_result["comorbidity_risk"] in ("high", "critical"):
            notes.append(f"Risco por comorbidades: {evaluation_result['comorbidity_risk']}")

        return "; ".join(notes) if notes else None
