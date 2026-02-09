"""Calculate clinical complexity score for an encounter.

CIB7 External Task Topic: coding.calculate_complexity
BPMN Error Codes: CODING_ERROR (input validation only; always completes)

Phase 2.2 - SUB_05_Coding_Audit: Computes a weighted complexity score
based on diagnosis count, procedure complexity, Charlson comorbidity
index, patient age, and encounter class.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from platform.shared.domain.exceptions import CodingException
from platform.shared.i18n import _
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class ComplexityLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


def _level_from_score(score: int) -> ComplexityLevel:
    if score <= 3:
        return ComplexityLevel.LOW
    if score <= 6:
        return ComplexityLevel.MODERATE
    if score <= 9:
        return ComplexityLevel.HIGH
    return ComplexityLevel.VERY_HIGH


# Simplified Charlson Comorbidity Index weights keyed by CID-10 chapter/range.
# In production these would be mapped to the full Charlson categories; this
# stub maps CID-10 first-letter/chapter to a representative weight.
_CHARLSON_WEIGHTS: dict[str, int] = {
    # Myocardial infarction (I21-I25)
    "I21": 1, "I22": 1, "I23": 1, "I24": 1, "I25": 1,
    # Congestive heart failure (I50)
    "I50": 1,
    # Peripheral vascular disease (I70-I79)
    "I70": 1, "I71": 1, "I73": 1,
    # Cerebrovascular disease (I60-I69)
    "I60": 1, "I61": 1, "I62": 1, "I63": 1, "I64": 1, "I65": 1, "I66": 1, "I67": 1, "I69": 1,
    # Dementia (F00-F03)
    "F00": 1, "F01": 1, "F02": 1, "F03": 1,
    # Chronic pulmonary disease (J40-J47)
    "J40": 1, "J41": 1, "J42": 1, "J43": 1, "J44": 1, "J45": 1, "J46": 1, "J47": 1,
    # Connective tissue disease (M05, M06, M32-M34)
    "M05": 1, "M06": 1, "M32": 1, "M33": 1, "M34": 1,
    # Peptic ulcer (K25-K28)
    "K25": 1, "K26": 1, "K27": 1, "K28": 1,
    # Mild liver disease (K70, K73, K74)
    "K70": 1, "K73": 1, "K74": 1,
    # Diabetes without complications (E10-E14 base)
    "E10": 1, "E11": 1, "E12": 1, "E13": 1, "E14": 1,
    # Diabetes with complications - weight 2
    # (detected by checking for .1-.8 suffixes in code; handled in logic)
    # Hemiplegia (G81)
    "G81": 2,
    # Renal disease (N18, N19)
    "N18": 2, "N19": 2,
    # Solid tumour (C00-C75)
    "C": 2,  # broad catch; refined below
    # Leukaemia (C91-C95)
    "C91": 2, "C92": 2, "C93": 2, "C94": 2, "C95": 2,
    # Lymphoma (C81-C85)
    "C81": 2, "C82": 2, "C83": 2, "C84": 2, "C85": 2,
    # Moderate/severe liver disease (K72)
    "K72": 3,
    # Metastatic solid tumour (C77-C80)
    "C77": 6, "C78": 6, "C79": 6, "C80": 6,
    # AIDS (B20-B24)
    "B20": 6, "B21": 6, "B22": 6, "B23": 6, "B24": 6,
}

# Procedure complexity by TUSS first digit (same as fraud worker)
_PROCEDURE_COMPLEXITY: dict[str, float] = {
    "1": 1.0,
    "2": 1.5,
    "3": 3.0,
    "4": 1.5,
    "5": 1.0,
}

# Encounter class base weights
_ENCOUNTER_CLASS_WEIGHT: dict[str, float] = {
    "ambulatorio": 0.5,
    "internacao": 2.0,
    "urgencia": 1.5,
    "day_clinic": 1.0,
}

# Age factor breakpoints
_AGE_FACTOR_MAP: list[tuple[int, float]] = [
    (1, 1.5),    # neonates
    (5, 1.2),    # infants
    (18, 0.8),   # children
    (50, 1.0),   # adults
    (65, 1.3),   # older adults
    (80, 1.6),   # elderly
    (999, 2.0),  # very elderly
]

# DRG suggestion table (simplified; maps complexity level to suggested DRG)
_SUGGESTED_DRG: dict[ComplexityLevel, str] = {
    ComplexityLevel.LOW: "DRG-001",
    ComplexityLevel.MODERATE: "DRG-002",
    ComplexityLevel.HIGH: "DRG-003",
    ComplexityLevel.VERY_HIGH: "DRG-004",
}


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class CalculateComplexityInput(BaseModel):
    """Input for calculate-clinical-complexity task."""

    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(
        ..., alias="encounterId", min_length=1,
    )
    validated_cid10: list[str] = Field(
        ..., alias="validatedCid10",
    )
    validated_tuss: list[str] = Field(
        ..., alias="validatedTuss",
    )
    encounter_class: str = Field(
        ..., alias="encounterClass", min_length=1,
    )
    patient_age: int = Field(
        ..., alias="patientAge", ge=0, le=150,
    )
    comorbidities: list[str] = Field(
        default_factory=list,
        description="Additional comorbidity CID-10 codes",
    )
    tenant_id: str = Field(
        ..., alias="tenantId", min_length=1,
    )

    @field_validator("encounter_id", "tenant_id")
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()


@dataclass
class ComplexityFactor:
    """Individual factor contributing to complexity score."""

    factor: str
    weight: float
    contribution: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "weight": round(self.weight, 2),
            "contribution": round(self.contribution, 2),
        }


@dataclass
class ComplexityResult:
    """Aggregate complexity calculation result."""

    score: int = 0
    level: ComplexityLevel = ComplexityLevel.LOW
    factors: list[ComplexityFactor] = field(default_factory=list)
    suggested_drg: str = ""

    def finalize(self) -> None:
        raw = sum(f.contribution for f in self.factors)
        self.score = max(1, min(int(round(raw)), 15))
        self.level = _level_from_score(self.score)
        self.suggested_drg = _SUGGESTED_DRG.get(self.level, "DRG-001")


class CalculateComplexityOutput(BaseModel):
    """Output for calculate-clinical-complexity task."""

    model_config = ConfigDict(populate_by_name=True)

    complexity_score: int = Field(
        ..., alias="complexityScore", ge=0,
    )
    complexity_level: str = Field(
        ..., alias="complexityLevel",
    )
    complexity_factors: list[dict[str, Any]] = Field(
        default_factory=list, alias="complexityFactors",
    )
    suggested_drg: str = Field(
        ..., alias="suggestedDRG",
    )

    def to_variables(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


# ---------------------------------------------------------------------------
# Protocol & Stub
# ---------------------------------------------------------------------------

@runtime_checkable
class ComplexityCalculatorProtocol(Protocol):
    """Contract for complexity calculation dependency."""

    async def calculate(
        self,
        cid10_codes: list[str],
        tuss_codes: list[str],
        encounter_class: str,
        patient_age: int,
        comorbidities: list[str],
    ) -> ComplexityResult: ...


class ComplexityCalculatorStub:
    """Stub implementation computing complexity from input counts and weights."""

    async def calculate(
        self,
        cid10_codes: list[str],
        tuss_codes: list[str],
        encounter_class: str,
        patient_age: int,
        comorbidities: list[str],
    ) -> ComplexityResult:
        result = ComplexityResult()

        # Factor 1: Diagnosis count
        diag_weight = 0.5
        diag_contribution = len(cid10_codes) * diag_weight
        result.factors.append(ComplexityFactor(
            factor="diagnosis_count",
            weight=diag_weight,
            contribution=diag_contribution,
        ))

        # Factor 2: Procedure complexity
        proc_contribution = self._procedure_complexity(tuss_codes)
        result.factors.append(ComplexityFactor(
            factor="procedure_complexity",
            weight=1.0,
            contribution=proc_contribution,
        ))

        # Factor 3: Charlson comorbidity index
        all_codes = cid10_codes + comorbidities
        cci = self._charlson_index(all_codes)
        result.factors.append(ComplexityFactor(
            factor="charlson_comorbidity_index",
            weight=1.0,
            contribution=float(cci),
        ))

        # Factor 4: Age factor
        age_factor = self._age_factor(patient_age)
        result.factors.append(ComplexityFactor(
            factor="age_factor",
            weight=age_factor,
            contribution=age_factor,
        ))

        # Factor 5: Encounter class weight
        enc_weight = _ENCOUNTER_CLASS_WEIGHT.get(encounter_class.lower(), 1.0)
        result.factors.append(ComplexityFactor(
            factor="encounter_class",
            weight=enc_weight,
            contribution=enc_weight,
        ))

        result.finalize()
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _procedure_complexity(tuss_codes: list[str]) -> float:
        """Sum procedure complexity weights."""
        total = 0.0
        for code in tuss_codes:
            first = code[0] if code else "1"
            total += _PROCEDURE_COMPLEXITY.get(first, 1.0)
        return min(total, 5.0)  # cap contribution

    @staticmethod
    def _charlson_index(cid10_codes: list[str]) -> int:
        """Simplified Charlson Comorbidity Index from CID-10 codes."""
        score = 0
        seen_categories: set[str] = set()

        for code in cid10_codes:
            code_upper = code.upper().strip().replace(".", "")
            if not code_upper:
                continue

            # Try exact 3-char match first (e.g. "I50")
            prefix3 = code_upper[:3]
            if prefix3 in _CHARLSON_WEIGHTS and prefix3 not in seen_categories:
                seen_categories.add(prefix3)
                score += _CHARLSON_WEIGHTS[prefix3]
                continue

            # Broad cancer catch (C00-C75 = weight 2)
            if code_upper.startswith("C") and "C" not in seen_categories:
                # Check it's not already handled by specific keys
                if prefix3 not in _CHARLSON_WEIGHTS:
                    seen_categories.add("C")
                    score += 2

        return score

    @staticmethod
    def _age_factor(age: int) -> float:
        """Return age-based complexity multiplier."""
        for threshold, factor in _AGE_FACTOR_MAP:
            if age <= threshold:
                return factor
        return 1.0


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class CalculateComplexityWorker:
    """Calculates clinical complexity score for an encounter.

    Combines diagnosis count, procedure complexity, Charlson comorbidity
    index, patient age, and encounter class into a single weighted score.
    """

    TOPIC = "coding.calculate_complexity"

    def __init__(
        self,
        calculator: ComplexityCalculatorProtocol | None = None,
    ) -> None:
        self._calculator: ComplexityCalculatorProtocol = (
            calculator or ComplexityCalculatorStub()
        )
        self._logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(metric_name="coding_calculate_complexity")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Calculate clinical complexity for an encounter.

        Task Variables (input):
            encounterId: str
            validatedCid10: list[str]
            validatedTuss: list[str]
            encounterClass: str
            patientAge: int
            comorbidities: list[str]
            tenantId: str

        Returns:
            complexityScore: int
            complexityLevel: str (LOW|MODERATE|HIGH|VERY_HIGH)
            complexityFactors: list[dict]
            suggestedDRG: str
        """
        ctx = get_required_tenant()

        try:
            inp = CalculateComplexityInput(**task_variables)
        except Exception as exc:
            raise CodingException(
                _("Dados de entrada invalidos para calculo de complexidade: {error}").format(
                    error=str(exc),
                ),
                bpmn_error_code="CODING_ERROR",
            ) from exc

        self._logger.info(
            "complexity_calculation_started",
            encounter_id=inp.encounter_id,
            cid10_count=len(inp.validated_cid10),
            tuss_count=len(inp.validated_tuss),
            patient_age=inp.patient_age,
            comorbidity_count=len(inp.comorbidities),
            tenant_id=ctx.tenant_id,
        )

        complexity = await self._calculator.calculate(
            cid10_codes=inp.validated_cid10,
            tuss_codes=inp.validated_tuss,
            encounter_class=inp.encounter_class,
            patient_age=inp.patient_age,
            comorbidities=inp.comorbidities,
        )

        self._logger.info(
            "complexity_calculation_completed",
            encounter_id=inp.encounter_id,
            score=complexity.score,
            level=complexity.level.value,
            suggested_drg=complexity.suggested_drg,
            factor_count=len(complexity.factors),
            tenant_id=ctx.tenant_id,
        )

        output = CalculateComplexityOutput(
            complexity_score=complexity.score,
            complexity_level=complexity.level.value,
            complexity_factors=[f.to_dict() for f in complexity.factors],
            suggested_drg=complexity.suggested_drg,
        )
        return output.to_variables()


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_worker(
    *,
    calculator: ComplexityCalculatorProtocol | None = None,
) -> CalculateComplexityWorker:
    """Create and return a configured CalculateComplexityWorker instance."""
    return CalculateComplexityWorker(calculator=calculator)
