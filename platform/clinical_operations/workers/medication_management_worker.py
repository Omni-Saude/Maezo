"""Manage medication orders and administration tracking.

CIB7 External Task Topic: clinical.medication
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


# ── Data Transfer Objects ─────────────────────────────────────────────


class MedicationInteraction(BaseModel):
    """Medication interaction warning."""

    drug1: str = Field(..., description="First medication")
    drug2: str = Field(..., description="Second medication")
    severity: str = Field(..., description="Interaction severity")
    description: str = Field(..., description="Interaction description")


class MedicationOrder(BaseModel):
    """Medication order details."""

    medication_code: str = Field(..., description="Medication code")
    medication_name: str = Field(..., description="Medication name")
    dosage: str = Field(..., description="Dosage amount and unit")
    route: str = Field(..., description="Administration route")
    frequency: str = Field(..., description="Administration frequency")
    duration_days: int | None = Field(None, description="Treatment duration")


class MedicationManagementInput(BaseModel):
    """Input variables for medication management."""

    encounter_reference: str = Field(..., description="FHIR Encounter reference")
    patient_reference: str = Field(..., description="FHIR Patient reference")
    medication_orders: list[dict[str, Any]] = Field(
        default_factory=list, description="Medication orders"
    )
    allergies: list[str] = Field(
        default_factory=list, description="Patient allergies"
    )
    tenant_id: str = Field(default="")


class MedicationManagementOutput(BaseModel):
    """Output variables for medication management."""

    validated_medications: list[dict[str, Any]]
    interaction_warnings: list[dict[str, Any]]
    administration_schedule: list[dict[str, Any]]

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "validated_medications": self.validated_medications,
            "interaction_warnings": self.interaction_warnings,
            "administration_schedule": self.administration_schedule,
        }


# ── Protocol ──────────────────────────────────────────────────────────


class DrugInteractionChecker(ABC):
    """Protocol for drug interaction checking engines."""

    @abstractmethod
    def check_interactions(
        self,
        medications: list[MedicationOrder],
    ) -> list[MedicationInteraction]:
        """Check for drug-drug interactions.

        Args:
            medications: List of medication orders to check

        Returns:
            List of interaction warnings
        """
        ...


class AllergyChecker(ABC):
    """Protocol for allergy checking engines."""

    @abstractmethod
    def check_allergies(
        self,
        medications: list[MedicationOrder],
        allergies: list[str],
    ) -> list[str]:
        """Check medications against patient allergies.

        Args:
            medications: List of medication orders
            allergies: Patient's known allergies

        Returns:
            List of allergy warning messages
        """
        ...


# ── Stub Implementation ──────────────────────────────────────────────

# Known drug-drug interactions database (simplified)
_KNOWN_INTERACTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("WARFARINA", "AAS"): (
        "MAJOR",
        "Risco aumentado de sangramento. Monitorar INR.",
    ),
    ("WARFARINA", "AMIODARONA"): (
        "MAJOR",
        "Amiodarona aumenta níveis de warfarina. Ajustar dose.",
    ),
    ("DIGOXINA", "AMIODARONA"): (
        "MAJOR",
        "Amiodarona aumenta níveis de digoxina. Reduzir dose.",
    ),
    ("ESTATINA", "CLARITROMICINA"): (
        "MAJOR",
        "Risco de rabdomiólise. Suspender estatina durante tratamento.",
    ),
    ("METFORMINA", "CONTRASTE"): (
        "MAJOR",
        "Risco de acidose láctica. Suspender metformina 48h antes.",
    ),
    ("CAPTOPRIL", "ESPIRONOLACTONA"): (
        "MODERATE",
        "Risco de hipercalemia. Monitorar potássio.",
    ),
    ("FLUOXETINA", "TRAMADOL"): (
        "MODERATE",
        "Risco de síndrome serotoninérgica. Monitorar sintomas.",
    ),
}

# Common medication allergies and cross-reactions
_ALLERGY_CROSS_REACTIONS: dict[str, list[str]] = {
    "PENICILINA": ["AMOXICILINA", "AMPICILINA", "CEFALOSPORINA"],
    "SULFA": ["SULFAMETOXAZOL", "CELECOXIBE", "FUROSEMIDA"],
    "AAS": ["IBUPROFENO", "NAPROXENO", "DICLOFENACO"],
    "DIPIRONA": ["PARACETAMOL"],
}


class StubDrugInteractionChecker(DrugInteractionChecker):
    """Rule-based drug interaction checker for development/testing."""

    def check_interactions(
        self,
        medications: list[MedicationOrder],
    ) -> list[MedicationInteraction]:
        """Check using known interactions database."""
        interactions: list[MedicationInteraction] = []

        # Compare each medication with every other
        for i, med1 in enumerate(medications):
            for med2 in medications[i + 1:]:
                # Normalize medication names for matching
                name1 = self._normalize_med_name(med1.medication_name)
                name2 = self._normalize_med_name(med2.medication_name)

                # Check both orderings
                key = (name1, name2)
                reverse_key = (name2, name1)

                if key in _KNOWN_INTERACTIONS:
                    severity, description = _KNOWN_INTERACTIONS[key]
                    interactions.append(
                        MedicationInteraction(
                            drug1=med1.medication_name,
                            drug2=med2.medication_name,
                            severity=severity,
                            description=description,
                        )
                    )
                elif reverse_key in _KNOWN_INTERACTIONS:
                    severity, description = _KNOWN_INTERACTIONS[reverse_key]
                    interactions.append(
                        MedicationInteraction(
                            drug1=med1.medication_name,
                            drug2=med2.medication_name,
                            severity=severity,
                            description=description,
                        )
                    )

        return interactions

    @staticmethod
    def _normalize_med_name(name: str) -> str:
        """Normalize medication name for matching."""
        return name.upper().strip()


class StubAllergyChecker(AllergyChecker):
    """Allergy cross-reaction checker for development/testing."""

    def check_allergies(
        self,
        medications: list[MedicationOrder],
        allergies: list[str],
    ) -> list[str]:
        """Check medications against allergies and cross-reactions."""
        warnings: list[str] = []

        for allergy in allergies:
            allergy_normalized = allergy.upper().strip()

            for medication in medications:
                med_normalized = medication.medication_name.upper().strip()

                # Direct match
                if allergy_normalized in med_normalized:
                    warnings.append(
                        _(
                            "ALERTA: {medication} pode causar reação alérgica "
                            "(alergia conhecida a {allergy})"
                        ).format(
                            medication=medication.medication_name,
                            allergy=allergy,
                        )
                    )
                    continue

                # Check cross-reactions
                for allergen, cross_reactions in _ALLERGY_CROSS_REACTIONS.items():
                    if allergen in allergy_normalized:
                        for cross_med in cross_reactions:
                            if cross_med in med_normalized:
                                warnings.append(
                                    _(
                                        "ALERTA: {medication} pode ter reação cruzada "
                                        "com alergia a {allergy}"
                                    ).format(
                                        medication=medication.medication_name,
                                        allergy=allergy,
                                    )
                                )

        return warnings


# ── Worker ────────────────────────────────────────────────────────────


class MedicationManagementWorker:
    """Manages medication orders and administration tracking.

    Validates medication orders, checks for drug interactions and
    allergies, and generates administration schedules.
    """

    TOPIC = "clinical.medication"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        interaction_checker: DrugInteractionChecker | None = None,
        allergy_checker: AllergyChecker | None = None,
    ) -> None:
        self._fhir = fhir_client
        self._interaction_checker = interaction_checker or StubDrugInteractionChecker()
        self._allergy_checker = allergy_checker or StubAllergyChecker()
        self._logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(metric_name="medication_management")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Validate medications and generate administration schedule.

        Task Variables (input):
            encounter_reference: str - FHIR Encounter reference
            patient_reference: str - FHIR Patient reference
            medication_orders: list[dict] - Medication orders
            allergies: list[str] - Patient allergies
            tenant_id: str - Tenant identifier (set via context)

        Returns:
            validated_medications: list[dict] - Validated medication orders
            interaction_warnings: list[dict] - Drug interaction warnings
            administration_schedule: list[dict] - Administration schedule
        """
        ctx = get_required_tenant()
        encounter_reference: str = task_variables.get("encounter_reference", "")
        patient_reference: str = task_variables.get("patient_reference", "")
        medication_orders_raw: list[dict[str, Any]] = task_variables.get(
            "medication_orders", []
        )
        allergies: list[str] = task_variables.get("allergies", [])

        if not encounter_reference or not patient_reference:
            raise ClinicalException(
                _("Referências de encontro e paciente são obrigatórias"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        if not medication_orders_raw:
            raise ClinicalException(
                _("Prescrições de medicamentos são obrigatórias"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        self._logger.info(
            "processing_medication_orders",
            encounter_reference=encounter_reference,
            patient_reference=patient_reference,
            medications_count=len(medication_orders_raw),
            allergies_count=len(allergies),
            tenant_id=ctx.tenant_id,
        )

        # ── Parse medication orders ──────────────────────────────────

        medications: list[MedicationOrder] = []
        for order_dict in medication_orders_raw:
            try:
                medications.append(MedicationOrder(**order_dict))
            except Exception as e:
                self._logger.warning(
                    "invalid_medication_order",
                    error=str(e),
                    order=order_dict,
                    tenant_id=ctx.tenant_id,
                )

        if not medications:
            raise ClinicalException(
                _("Nenhuma prescrição válida encontrada"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        # ── Check allergies ──────────────────────────────────────────

        allergy_warnings = self._allergy_checker.check_allergies(
            medications=medications,
            allergies=allergies,
        )

        if allergy_warnings:
            self._logger.warning(
                "allergy_warnings_detected",
                warnings_count=len(allergy_warnings),
                tenant_id=ctx.tenant_id,
            )

        # ── Check drug interactions ──────────────────────────────────

        interactions = self._interaction_checker.check_interactions(
            medications=medications
        )

        if interactions:
            self._logger.warning(
                "drug_interactions_detected",
                interactions_count=len(interactions),
                tenant_id=ctx.tenant_id,
            )

        # ── Generate administration schedule ─────────────────────────

        schedule = self._generate_administration_schedule(medications)

        # ── Prepare output ───────────────────────────────────────────

        validated_medications_list = [
            {
                "medication_code": m.medication_code,
                "medication_name": m.medication_name,
                "dosage": m.dosage,
                "route": m.route,
                "frequency": m.frequency,
                "duration_days": m.duration_days,
            }
            for m in medications
        ]

        interaction_warnings_list = [
            {
                "drug1": i.drug1,
                "drug2": i.drug2,
                "severity": i.severity,
                "description": i.description,
            }
            for i in interactions
        ]

        # Add allergy warnings to interactions
        for warning in allergy_warnings:
            interaction_warnings_list.append(
                {
                    "drug1": "ALLERGY",
                    "drug2": "",
                    "severity": "MAJOR",
                    "description": warning,
                }
            )

        output = MedicationManagementOutput(
            validated_medications=validated_medications_list,
            interaction_warnings=interaction_warnings_list,
            administration_schedule=schedule,
        )

        self._logger.info(
            "medication_management_complete",
            validated_count=len(medications),
            warnings_count=len(interaction_warnings_list),
            schedule_entries=len(schedule),
            tenant_id=ctx.tenant_id,
        )

        return output.to_variables()

    def _generate_administration_schedule(
        self,
        medications: list[MedicationOrder],
    ) -> list[dict[str, Any]]:
        """Generate administration schedule from medication orders."""
        schedule: list[dict[str, Any]] = []

        for medication in medications:
            # Parse frequency to determine schedule times
            times = self._frequency_to_times(medication.frequency)

            for time in times:
                schedule.append(
                    {
                        "medication_name": medication.medication_name,
                        "dosage": medication.dosage,
                        "route": medication.route,
                        "scheduled_time": time,
                        "status": "pending",
                    }
                )

        # Sort by scheduled time
        schedule.sort(key=lambda s: s["scheduled_time"])

        return schedule

    @staticmethod
    def _frequency_to_times(frequency: str) -> list[str]:
        """Convert frequency string to administration times."""
        frequency_lower = frequency.lower()

        # Common frequency patterns
        if "8/8" in frequency_lower or "8h" in frequency_lower:
            return ["08:00", "16:00", "00:00"]
        elif "6/6" in frequency_lower or "6h" in frequency_lower:
            return ["06:00", "12:00", "18:00", "00:00"]
        elif "12/12" in frequency_lower or "12h" in frequency_lower:
            return ["08:00", "20:00"]
        elif "24/24" in frequency_lower or "1x" in frequency_lower or "dia" in frequency_lower:
            return ["08:00"]
        elif "2x" in frequency_lower:
            return ["08:00", "20:00"]
        elif "3x" in frequency_lower:
            return ["08:00", "14:00", "20:00"]
        elif "4x" in frequency_lower:
            return ["06:00", "12:00", "18:00", "00:00"]
        else:
            # Default to once daily
            return ["08:00"]
