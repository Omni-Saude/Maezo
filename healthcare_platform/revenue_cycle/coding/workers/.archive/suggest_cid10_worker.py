"""Suggest CID-10 codes from clinical text using NLP patterns.

CIB7 External Task Topic: coding.suggest_cid10_codes
BPMN Error Codes: CODING_ERROR
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


# ── Data Transfer Objects ─────────────────────────────────────────────

CID10_PATTERN = re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$")


class CID10Suggestion(BaseModel):
    """A suggested CID-10 code with confidence score."""

    code: str = Field(..., description="CID-10 code (e.g., J18.9)")
    description: str = Field(..., description="Diagnosis description in Portuguese")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score 0-1"
    )


class SuggestCid10Input(BaseModel):
    """Input variables for CID-10 suggestion."""

    clinical_notes: str = Field(..., min_length=1)
    extracted_diagnoses: list[dict[str, Any]] = Field(default_factory=list)
    encounter_class: str = Field(default="ambulatorio")
    tenant_id: str = Field(default="")


class SuggestCid10Output(BaseModel):
    """Output variables for CID-10 suggestion."""

    suggested_cid10_codes: list[dict[str, Any]]
    primary_cid10: str
    cid10_count: int

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "suggested_cid10_codes": self.suggested_cid10_codes,
            "primary_cid10": self.primary_cid10,
            "cid10_count": self.cid10_count,
        }


# ── Protocol ──────────────────────────────────────────────────────────


class CID10SuggestionEngine(ABC):
    """Protocol for CID-10 suggestion engines."""

    @abstractmethod
    def suggest(
        self,
        notes: str,
        context: dict[str, Any],
    ) -> list[CID10Suggestion]:
        """Suggest CID-10 codes from clinical text.

        Args:
            notes: Clinical notes text
            context: Additional context (extracted_diagnoses, encounter_class)

        Returns:
            List of CID-10 suggestions sorted by confidence descending
        """
        ...


# ── Stub Implementation ──────────────────────────────────────────────


# Keyword-to-CID10 mapping for pattern-based suggestion
_KEYWORD_CID10_MAP: dict[str, list[CID10Suggestion]] = {
    "pneumonia": [
        CID10Suggestion(
            code="J18.9",
            description="Pneumonia não especificada",
            confidence=0.85,
        ),
        CID10Suggestion(
            code="J18.0",
            description="Broncopneumonia não especificada",
            confidence=0.65,
        ),
    ],
    "diabetes": [
        CID10Suggestion(
            code="E11.9",
            description="Diabetes mellitus tipo 2 sem complicações",
            confidence=0.88,
        ),
        CID10Suggestion(
            code="E10.9",
            description="Diabetes mellitus tipo 1 sem complicações",
            confidence=0.45,
        ),
    ],
    "hipertensão": [
        CID10Suggestion(
            code="I10",
            description="Hipertensão essencial (primária)",
            confidence=0.90,
        ),
    ],
    "hipertensao": [
        CID10Suggestion(
            code="I10",
            description="Hipertensão essencial (primária)",
            confidence=0.90,
        ),
    ],
    "infarto": [
        CID10Suggestion(
            code="I21.9",
            description="Infarto agudo do miocárdio não especificado",
            confidence=0.87,
        ),
    ],
    "fratura": [
        CID10Suggestion(
            code="S72.0",
            description="Fratura do colo do fêmur",
            confidence=0.70,
        ),
        CID10Suggestion(
            code="S52.5",
            description="Fratura da extremidade distal do rádio",
            confidence=0.55,
        ),
    ],
    "apendicite": [
        CID10Suggestion(
            code="K35.8",
            description="Apendicite aguda, outras e não especificadas",
            confidence=0.92,
        ),
    ],
    "dor lombar": [
        CID10Suggestion(
            code="M54.5",
            description="Dor lombar baixa",
            confidence=0.80,
        ),
    ],
    "lombalgia": [
        CID10Suggestion(
            code="M54.5",
            description="Dor lombar baixa",
            confidence=0.82,
        ),
    ],
    "cefaleia": [
        CID10Suggestion(
            code="R51",
            description="Cefaleia",
            confidence=0.75,
        ),
    ],
    "diarreia": [
        CID10Suggestion(
            code="A09",
            description="Diarreia e gastroenterite de origem infecciosa presumível",
            confidence=0.78,
        ),
    ],
    "covid": [
        CID10Suggestion(
            code="U07.1",
            description="COVID-19, vírus identificado",
            confidence=0.92,
        ),
    ],
    "asma": [
        CID10Suggestion(
            code="J45.9",
            description="Asma não especificada",
            confidence=0.85,
        ),
    ],
    "insuficiência cardíaca": [
        CID10Suggestion(
            code="I50.9",
            description="Insuficiência cardíaca não especificada",
            confidence=0.88,
        ),
    ],
    "insuficiencia cardiaca": [
        CID10Suggestion(
            code="I50.9",
            description="Insuficiência cardíaca não especificada",
            confidence=0.88,
        ),
    ],
    "acidente vascular": [
        CID10Suggestion(
            code="I64",
            description="Acidente vascular cerebral não especificado",
            confidence=0.86,
        ),
    ],
    "avc": [
        CID10Suggestion(
            code="I64",
            description="Acidente vascular cerebral não especificado",
            confidence=0.86,
        ),
    ],
}


class StubCID10SuggestionEngine(CID10SuggestionEngine):
    """Keyword-based CID-10 suggestion engine for development/testing.

    Uses a keyword-to-CID10 mapping table with statistical confidence
    scoring based on keyword frequency and position in text.
    """

    def suggest(
        self,
        notes: str,
        context: dict[str, Any],
    ) -> list[CID10Suggestion]:
        """Suggest CID-10 codes using keyword matching."""
        notes_lower = notes.lower()
        suggestions: dict[str, CID10Suggestion] = {}

        # 1. Include already-extracted diagnoses with high confidence
        extracted = context.get("extracted_diagnoses", [])
        for diag in extracted:
            code = diag.get("code", "")
            if code and CID10_PATTERN.match(code):
                suggestions[code] = CID10Suggestion(
                    code=code,
                    description=diag.get("display", _("Diagnóstico extraído do prontuário")),
                    confidence=0.95,
                )

        # 2. Keyword-based matching
        for keyword, cid10_list in _KEYWORD_CID10_MAP.items():
            if keyword in notes_lower:
                # Boost confidence if keyword appears multiple times
                occurrences = notes_lower.count(keyword)
                boost = min(0.05 * (occurrences - 1), 0.10)

                for suggestion in cid10_list:
                    if suggestion.code not in suggestions:
                        adjusted_confidence = min(
                            suggestion.confidence + boost, 1.0
                        )
                        suggestions[suggestion.code] = CID10Suggestion(
                            code=suggestion.code,
                            description=suggestion.description,
                            confidence=adjusted_confidence,
                        )

        result = sorted(
            suggestions.values(), key=lambda s: s.confidence, reverse=True
        )
        return result


# ── Worker ────────────────────────────────────────────────────────────


class SuggestCid10Worker:
    """Suggests CID-10 codes from clinical notes using NLP patterns.

    Uses a pluggable CID10SuggestionEngine for the actual suggestion
    logic. The default stub uses keyword matching; production
    implementations can integrate NLP/ML models.
    """

    TOPIC = "coding.suggest_cid10"

    def __init__(
        self, suggestion_engine: CID10SuggestionEngine | None = None
    ) -> None:
        self._engine = suggestion_engine or StubCID10SuggestionEngine()
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    @require_tenant
    @track_task_execution(metric_name="coding_suggest_cid10")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Suggest CID-10 codes from clinical text.

        Task Variables (input):
            clinical_notes: str - Combined clinical notes text
            extracted_diagnoses: list[dict] - Previously extracted diagnoses
            encounter_class: str - Encounter classification
            tenant_id: str - Tenant identifier (set via context)

        Returns:
            suggested_cid10_codes: list[dict] - {code, description, confidence}
            primary_cid10: str - Highest-confidence CID-10 code
            cid10_count: int - Total suggested codes
        """
        ctx = get_required_tenant()
        clinical_notes: str = task_variables.get("clinical_notes", "")
        extracted_diagnoses: list[dict[str, Any]] = task_variables.get(
            "extracted_diagnoses", []
        )
        encounter_class: str = task_variables.get("encounter_class", "ambulatorio")

        if not clinical_notes and not extracted_diagnoses:
            raise CodingException(
                _("Dados clínicos insuficientes para sugestão de CID-10: "
                  "notas clínicas e diagnósticos extraídos estão vazios"),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "suggesting_cid10",
            notes_length=len(clinical_notes),
            extracted_count=len(extracted_diagnoses),
            encounter_class=encounter_class,
            tenant_id=ctx.tenant_id,
        )

        # ── Run suggestion engine ────────────────────────────────────

        context = {
            "extracted_diagnoses": extracted_diagnoses,
            "encounter_class": encounter_class,
        }

        suggestions = self._engine.suggest(clinical_notes, context)

        # ── Validate CID-10 format ───────────────────────────────────

        valid_suggestions: list[CID10Suggestion] = []
        for suggestion in suggestions:
            if CID10_PATTERN.match(suggestion.code):
                valid_suggestions.append(suggestion)
            else:
                self._logger.warning(
                    "invalid_cid10_format",
                    code=suggestion.code,
                    tenant_id=ctx.tenant_id,
                )

        # ── Build output ─────────────────────────────────────────────

        primary_cid10 = valid_suggestions[0].code if valid_suggestions else ""

        output = SuggestCid10Output(
            suggested_cid10_codes=[
                {
                    "code": s.code,
                    "description": s.description,
                    "confidence": round(s.confidence, 3),
                }
                for s in valid_suggestions
            ],
            primary_cid10=primary_cid10,
            cid10_count=len(valid_suggestions),
        )

        self._logger.info(
            "cid10_suggestions_complete",
            cid10_count=output.cid10_count,
            primary_cid10=output.primary_cid10,
            tenant_id=ctx.tenant_id,
        )

        return output.to_variables()


    def _evaluate_coding_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate coding_audit DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='coding_audit',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_worker(
    suggestion_engine: CID10SuggestionEngine | None = None,
) -> SuggestCid10Worker:
    """Create and return a configured SuggestCid10Worker instance."""
    return SuggestCid10Worker(suggestion_engine=suggestion_engine)

