"""Suggest TUSS codes based on procedures and CID-10 context.

CIB7 External Task Topic: coding.suggest_tuss_codes
BPMN Error Codes: CODING_ERROR
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.ans_client import ANSClientProtocol, RolValidationResult
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


# ── Constants & Validation ────────────────────────────────────────────

TUSS_PATTERN = re.compile(r"^\d{8}$")


# ── Data Transfer Objects ─────────────────────────────────────────────


class TUSSSuggestion(BaseModel):
    """A suggested TUSS code with confidence score.

    Archetype: FINANCIAL_CALCULATION"""

    code: str = Field(..., description="TUSS 8-digit code (e.g., 40101010)")
    name: str = Field(..., description="Procedure name in Portuguese")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score 0-1"
    )


class SuggestTussInput(BaseModel):
    """Input variables for TUSS suggestion."""

    extracted_procedures: list[dict[str, Any]] = Field(default_factory=list)
    suggested_cid10_codes: list[dict[str, Any]] = Field(default_factory=list)
    encounter_class: str = Field(default="ambulatorio")
    tenant_id: str = Field(default="")


class SuggestTussOutput(BaseModel):
    """Output variables for TUSS suggestion."""

    suggested_tuss_codes: list[dict[str, Any]]
    tuss_count: int

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "suggested_tuss_codes": self.suggested_tuss_codes,
            "tuss_count": self.tuss_count,
        }


# ── Protocol ──────────────────────────────────────────────────────────


class TUSSSuggestionEngine(ABC):
    """Protocol for TUSS suggestion engines."""

    @abstractmethod
    def suggest(
        self,
        procedures: list[dict[str, Any]],
        cid10_codes: list[dict[str, Any]],
    ) -> list[TUSSSuggestion]:
        """Suggest TUSS codes based on procedures and CID-10 context.

        Args:
            procedures: Extracted procedure data from encounter
            cid10_codes: Suggested CID-10 codes with descriptions

        Returns:
            List of TUSS suggestions sorted by confidence descending
        """
        ...


# ── Stub Implementation ──────────────────────────────────────────────

# Keyword-to-TUSS mapping for common procedures
_KEYWORD_TUSS_MAP: dict[str, list[TUSSSuggestion]] = {
    "consulta": [
        TUSSSuggestion(
            code="40101010",
            name="Consulta médica em consultório",
            confidence=0.85,
        ),
    ],
    "eletrocardiograma": [
        TUSSSuggestion(
            code="40101030",
            name="Eletrocardiograma convencional",
            confidence=0.90,
        ),
    ],
    "ecg": [
        TUSSSuggestion(
            code="40101030",
            name="Eletrocardiograma convencional",
            confidence=0.88,
        ),
    ],
    "hemograma": [
        TUSSSuggestion(
            code="40304361",
            name="Hemograma completo",
            confidence=0.92,
        ),
    ],
    "raio-x": [
        TUSSSuggestion(
            code="40801020",
            name="Radiografia de tórax",
            confidence=0.80,
        ),
    ],
    "radiografia": [
        TUSSSuggestion(
            code="40801020",
            name="Radiografia de tórax",
            confidence=0.78,
        ),
    ],
    "tomografia": [
        TUSSSuggestion(
            code="41001010",
            name="Tomografia computadorizada de crânio",
            confidence=0.82,
        ),
    ],
    "ressonância": [
        TUSSSuggestion(
            code="41101014",
            name="Ressonância magnética de crânio",
            confidence=0.83,
        ),
    ],
    "ressonancia": [
        TUSSSuggestion(
            code="41101014",
            name="Ressonância magnética de crânio",
            confidence=0.83,
        ),
    ],
    "ultrassonografia": [
        TUSSSuggestion(
            code="40901017",
            name="Ultrassonografia de abdome total",
            confidence=0.80,
        ),
    ],
    "ultrassom": [
        TUSSSuggestion(
            code="40901017",
            name="Ultrassonografia de abdome total",
            confidence=0.78,
        ),
    ],
    "endoscopia": [
        TUSSSuggestion(
            code="40202011",
            name="Endoscopia digestiva alta",
            confidence=0.88,
        ),
    ],
    "colonoscopia": [
        TUSSSuggestion(
            code="40202046",
            name="Colonoscopia",
            confidence=0.90,
        ),
    ],
    "internação": [
        TUSSSuggestion(
            code="31001010",
            name="Internação hospitalar em apartamento",
            confidence=0.75,
        ),
    ],
    "internacao": [
        TUSSSuggestion(
            code="31001010",
            name="Internação hospitalar em apartamento",
            confidence=0.75,
        ),
    ],
    "cirurgia": [
        TUSSSuggestion(
            code="30101012",
            name="Procedimento cirúrgico não especificado",
            confidence=0.65,
        ),
    ],
    "apendicectomia": [
        TUSSSuggestion(
            code="31003036",
            name="Apendicectomia",
            confidence=0.93,
        ),
    ],
    "glicemia": [
        TUSSSuggestion(
            code="40301010",
            name="Dosagem de glicose",
            confidence=0.88,
        ),
    ],
}

# CID-10 to TUSS correlation mapping (common clinical pathways)
_CID10_TUSS_CORRELATION: dict[str, list[TUSSSuggestion]] = {
    "J18": [
        TUSSSuggestion(
            code="40801020", name="Radiografia de tórax", confidence=0.85
        ),
        TUSSSuggestion(
            code="40304361", name="Hemograma completo", confidence=0.80
        ),
    ],
    "E11": [
        TUSSSuggestion(
            code="40301010", name="Dosagem de glicose", confidence=0.90
        ),
        TUSSSuggestion(
            code="40302040", name="Hemoglobina glicada", confidence=0.85
        ),
    ],
    "I21": [
        TUSSSuggestion(
            code="40101030",
            name="Eletrocardiograma convencional",
            confidence=0.92,
        ),
        TUSSSuggestion(
            code="40304361", name="Hemograma completo", confidence=0.75
        ),
    ],
    "K35": [
        TUSSSuggestion(
            code="31003036", name="Apendicectomia", confidence=0.90
        ),
        TUSSSuggestion(
            code="40901017",
            name="Ultrassonografia de abdome total",
            confidence=0.82,
        ),
    ],
    "I10": [
        TUSSSuggestion(
            code="40101030",
            name="Eletrocardiograma convencional",
            confidence=0.80,
        ),
    ],
    "I50": [
        TUSSSuggestion(
            code="40101030",
            name="Eletrocardiograma convencional",
            confidence=0.88,
        ),
        TUSSSuggestion(
            code="40801020", name="Radiografia de tórax", confidence=0.82
        ),
    ],
}


class StubTUSSSuggestionEngine(TUSSSuggestionEngine):
    """Keyword-based TUSS suggestion engine for development/testing.

    Uses keyword matching on procedure descriptions and CID-10
    correlation tables to suggest relevant TUSS codes.
    """

    def suggest(
        self,
        procedures: list[dict[str, Any]],
        cid10_codes: list[dict[str, Any]],
    ) -> list[TUSSSuggestion]:
        """Suggest TUSS codes using keyword and CID-10 correlation."""
        suggestions: dict[str, TUSSSuggestion] = {}

        # 1. Match from extracted procedure descriptions
        for proc in procedures:
            display = proc.get("display", "").lower()
            code = proc.get("code", "")

            # If already a valid TUSS code, include directly
            if TUSS_PATTERN.match(code):
                suggestions[code] = TUSSSuggestion(
                    code=code,
                    name=proc.get("display", _("Procedimento extraído")),
                    confidence=0.95,
                )
                continue

            # Keyword-based matching
            for keyword, tuss_list in _KEYWORD_TUSS_MAP.items():
                if keyword in display:
                    for tuss in tuss_list:
                        if tuss.code not in suggestions:
                            suggestions[tuss.code] = tuss

        # 2. CID-10 correlation: suggest related TUSS codes
        for cid10 in cid10_codes:
            code = cid10.get("code", "")
            # Match on CID-10 chapter (first 3 chars)
            prefix = code[:3] if len(code) >= 3 else code
            correlated = _CID10_TUSS_CORRELATION.get(prefix, [])
            for tuss in correlated:
                if tuss.code not in suggestions:
                    suggestions[tuss.code] = tuss

        result = sorted(
            suggestions.values(), key=lambda s: s.confidence, reverse=True
        )
        return result


# ── Worker ────────────────────────────────────────────────────────────


class SuggestTussWorker:
    """Suggests TUSS procedure codes based on clinical context.

    Uses a pluggable TUSSSuggestionEngine for suggestion logic and
    validates suggested codes against the ANS Rol via ANSClient.
    """

    TOPIC = "revenue_cycle.coding.suggest_tuss"

    def __init__(
        self,
        ans_client: ANSClientProtocol,
        suggestion_engine: TUSSSuggestionEngine | None = None,
    ) -> None:
        self._ans = ans_client
        self._engine = suggestion_engine or StubTUSSSuggestionEngine()
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    @require_tenant
    @track_task_execution(metric_name="coding_suggest_tuss")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Suggest TUSS codes from procedures and CID-10 context.

        Task Variables (input):
            extracted_procedures: list[dict] - Procedures from encounter
            suggested_cid10_codes: list[dict] - CID-10 suggestions
            encounter_class: str - Encounter classification
            tenant_id: str - Tenant identifier (set via context)

        Returns:
            suggested_tuss_codes: list[dict] - {code, name, confidence}
            tuss_count: int - Total suggested codes
        """
        ctx = get_required_tenant()
        extracted_procedures: list[dict[str, Any]] = task_variables.get(
            "extracted_procedures", []
        )
        suggested_cid10_codes: list[dict[str, Any]] = task_variables.get(
            "suggested_cid10_codes", []
        )
        encounter_class: str = task_variables.get("encounter_class", "ambulatorio")

        if not extracted_procedures and not suggested_cid10_codes:
            raise CodingException(
                _("Dados insuficientes para sugestão de TUSS: "
                  "procedimentos extraídos e códigos CID-10 estão vazios"),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "suggesting_tuss",
            procedures_count=len(extracted_procedures),
            cid10_count=len(suggested_cid10_codes),
            encounter_class=encounter_class,
            tenant_id=ctx.tenant_id,
        )

        # ── Run suggestion engine ────────────────────────────────────

        raw_suggestions = self._engine.suggest(
            extracted_procedures, suggested_cid10_codes
        )

        # ── Validate TUSS format ─────────────────────────────────────

        format_valid: list[TUSSSuggestion] = []
        for suggestion in raw_suggestions:
            if TUSS_PATTERN.match(suggestion.code):
                format_valid.append(suggestion)
            else:
                self._logger.warning(
                    "invalid_tuss_format",
                    code=suggestion.code,
                    tenant_id=ctx.tenant_id,
                )

        # ── Validate against ANS Rol ─────────────────────────────────

        validated: list[dict[str, Any]] = []
        for suggestion in format_valid:
            try:
                result: RolValidationResult = await self._ans.validate_procedure(
                    suggestion.code
                )
                if result.is_valid:
                    validated.append(
                        {
                            "code": suggestion.code,
                            "name": (
                                result.procedure.name
                                if result.procedure
                                else suggestion.name
                            ),
                            "confidence": round(suggestion.confidence, 3),
                            "is_covered": result.is_covered,
                            "coverage_type": result.coverage_type or "",
                        }
                    )
                else:
                    self._logger.warning(
                        "tuss_not_in_rol",
                        code=suggestion.code,
                        message=result.message,
                        tenant_id=ctx.tenant_id,
                    )
            except Exception:
                # On ANS validation failure, include suggestion as unvalidated
                self._logger.warning(
                    "tuss_validation_error",
                    code=suggestion.code,
                    tenant_id=ctx.tenant_id,
                )
                validated.append(
                    {
                        "code": suggestion.code,
                        "name": suggestion.name,
                        "confidence": round(suggestion.confidence * 0.8, 3),
                        "is_covered": False,
                        "coverage_type": "",
                    }
                )

        output = SuggestTussOutput(
            suggested_tuss_codes=validated,
            tuss_count=len(validated),
        )

        self._logger.info(
            "tuss_suggestions_complete",
            tuss_count=output.tuss_count,
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
    suggestion_engine: TUSSSuggestionEngine | None = None,
) -> SuggestTussWorker:
    """Create and return a configured SuggestTussWorker instance."""
    return SuggestTussWorker(suggestion_engine=suggestion_engine)

