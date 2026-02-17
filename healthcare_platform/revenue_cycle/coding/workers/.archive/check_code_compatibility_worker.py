"""Check CID-10 / TUSS code compatibility.

CIB7 External Task Topic: check-code-compatibility
BPMN Error Codes: INCOMPATIBLE_CODES, CODING_ERROR

Phase 2.2 - Coding & Audit: verifies that diagnosis codes (CID-10) are
clinically compatible with the requested procedure codes (TUSS).  A
compatibility matrix maps CID-10 chapter prefixes to allowed TUSS ranges.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import (
    CodingException,
    IncompatibleCodes,
)
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


# ── Data Transfer Objects ─────────────────────────────────────────────


class CheckCodeCompatibilityInput(BaseModel):
    """Variables consumed from the BPMN process."""

    validated_cid10: list[str] = Field(
        ...,
        alias="validatedCid10",
        min_length=1,
        description="CID-10 diagnosis codes already validated upstream.",
    )
    validated_tuss: list[str] = Field(
        ...,
        alias="validatedTuss",
        min_length=1,
        description="TUSS procedure codes already validated upstream.",
    )
    encounter_id: str = Field(..., alias="encounterId")
    tenant_id: str = Field(..., alias="tenantId")


class IncompatibilityDetail(BaseModel):
    """Single incompatibility between a CID-10 and a TUSS code."""

    cid10: str
    tuss: str
    reason: str


class CheckCodeCompatibilityOutput(BaseModel):
    """Variables returned to the BPMN process."""

    compatible: bool = True
    incompatibilities: list[IncompatibilityDetail] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "compatible": self.compatible,
            "incompatibilities": [i.model_dump() for i in self.incompatibilities],
            "warnings": self.warnings,
        }


# ── Value Objects ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class CompatibilityResult:
    """Result of a single compatibility check."""

    compatible: bool
    cid10: str = ""
    tuss: str = ""
    reason: str = ""
    severity: str = "ERROR"  # ERROR | WARNING


# ── Protocol ──────────────────────────────────────────────────────────


@runtime_checkable
class CompatibilityCheckerProtocol(Protocol):
    """Port: checks CID-10 <-> TUSS compatibility."""

    def check(
        self,
        cid10_codes: list[str],
        tuss_codes: list[str],
    ) -> list[CompatibilityResult]: ...


# ── Compatibility Matrix ──────────────────────────────────────────────

# CID-10 chapters are identified by the first letter (A-Z).
# TUSS codes are 8-digit numeric; the first 2 digits denote the group.
# This matrix captures known *incompatible* pairings (deny-list approach).

_INCOMPATIBLE_MATRIX: dict[str, set[str]] = {
    # Capítulo V - Transtornos mentais: incompatível com proc. cirúrgicos cardíacos
    "F": {"40", "41"},
    # Capítulo XI - Doenças do aparelho digestivo: incompatível com proc. oftalmológicos
    "K": {"30", "31"},
    # Capítulo VII - Doenças do olho: incompatível com proc. ortopédicos
    "H": {"40", "41", "42"},
    # Capítulo XV - Gravidez: incompatível com proc. pediátricos neonatais exclusivos
    "O": {"99"},
}

# Pairs that are valid but deserve a clinical justification warning.
_WARNING_PAIRS: dict[str, set[str]] = {
    # Diagnóstico psiquiátrico com procedimento neurológico: requer justificativa
    "F": {"20", "21"},
    # Doenças endócrinas com procedimentos cardíacos: verificar correlação
    "E": {"40", "41"},
}


# ── Stub Implementation ──────────────────────────────────────────────


class CompatibilityCheckerStub:
    """In-memory compatibility matrix lookup.

    Returns compatible for standard combinations and incompatible for
    entries in ``_INCOMPATIBLE_MATRIX``.  Intended to be replaced by a
    real service backed by the DMN rules engine (Phase 6).
    """

    def check(
        self,
        cid10_codes: list[str],
        tuss_codes: list[str],
    ) -> list[CompatibilityResult]:
        results: list[CompatibilityResult] = []

        for cid in cid10_codes:
            chapter = cid[0].upper() if cid else ""
            incompatible_prefixes = _INCOMPATIBLE_MATRIX.get(chapter, set())
            warning_prefixes = _WARNING_PAIRS.get(chapter, set())

            for tuss in tuss_codes:
                tuss_prefix = tuss[:2] if len(tuss) >= 2 else ""

                if tuss_prefix in incompatible_prefixes:
                    results.append(
                        CompatibilityResult(
                            compatible=False,
                            cid10=cid,
                            tuss=tuss,
                            reason=_(
                                "CID-10 capítulo {chapter} ({cid}) é incompatível "
                                "com grupo TUSS {prefix} ({tuss})"
                            ).format(
                                chapter=chapter,
                                cid=cid,
                                prefix=tuss_prefix,
                                tuss=tuss,
                            ),
                            severity="ERROR",
                        )
                    )
                elif tuss_prefix in warning_prefixes:
                    results.append(
                        CompatibilityResult(
                            compatible=True,
                            cid10=cid,
                            tuss=tuss,
                            reason=_(
                                "Combinação CID-10 {cid} com TUSS {tuss} requer "
                                "justificativa clínica adicional"
                            ).format(cid=cid, tuss=tuss),
                            severity="WARNING",
                        )
                    )

        return results


# ── Worker ────────────────────────────────────────────────────────────


class CheckCodeCompatibilityWorker:
    """Verifies CID-10 <-> TUSS compatibility for a coded encounter.

    Uses a compatibility matrix (deny-list) to detect clinically
    invalid combinations of diagnosis and procedure codes.
    """

    TOPIC = "coding.check_compatibility"

    def __init__(
        self,
        compatibility_checker: CompatibilityCheckerProtocol | None = None,
    ) -> None:
        self._checker = compatibility_checker or CompatibilityCheckerStub()
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    @require_tenant
    @track_task_execution(metric_name="coding_check_code_compatibility")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Check CID-10 / TUSS code compatibility.

        Task Variables (input):
            validatedCid10: list[str] - Validated CID-10 codes
            validatedTuss: list[str] - Validated TUSS codes
            encounterId: str - Encounter identifier
            tenantId: str - Tenant identifier

        Returns:
            compatible: bool - True if all combinations are compatible
            incompatibilities: list[dict] - List of {cid10, tuss, reason}
            warnings: list[str] - Non-blocking compatibility warnings

        Raises:
            IncompatibleCodes: when hard incompatibilities are found.
            CodingException: on invalid input.
        """
        ctx = get_required_tenant()

        # ── Parse & validate input ────────────────────────────────────
        validated_cid10: list[str] = task_variables.get("validatedCid10", [])
        validated_tuss: list[str] = task_variables.get("validatedTuss", [])
        encounter_id: str = task_variables.get("encounterId", "")
        tenant_id: str = task_variables.get("tenantId", "")

        if not validated_cid10:
            raise CodingException(
                _("Entrada inválida para verificação de compatibilidade: "
                  "lista de códigos CID-10 está vazia"),
                bpmn_error_code="CODING_ERROR",
            )
        if not validated_tuss:
            raise CodingException(
                _("Entrada inválida para verificação de compatibilidade: "
                  "lista de códigos TUSS está vazia"),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "compatibility_check_started",
            encounter_id=encounter_id,
            cid10_count=len(validated_cid10),
            tuss_count=len(validated_tuss),
            tenant_id=ctx.tenant_id,
        )

        # DMN-enhanced compatibility check
        dmn_result = self._evaluate_coding_dmn(
            subcategory="compat",
            table_name="code_compatibility_matrix",
            inputs={"cid10_codes": validated_cid10, "tuss_codes": validated_tuss}
        )

        # ── Run compatibility matrix ──────────────────────────────────
        results = self._checker.check(validated_cid10, validated_tuss)

        incompatibilities: list[IncompatibilityDetail] = []
        warnings: list[str] = []

        for r in results:
            if not r.compatible:
                incompatibilities.append(
                    IncompatibilityDetail(
                        cid10=r.cid10,
                        tuss=r.tuss,
                        reason=r.reason,
                    )
                )
            elif r.severity == "WARNING":
                warnings.append(r.reason)

        compatible = len(incompatibilities) == 0

        output = CheckCodeCompatibilityOutput(
            compatible=compatible,
            incompatibilities=incompatibilities,
            warnings=warnings,
        )

        # ── Handle incompatible codes ─────────────────────────────────
        if not compatible:
            self._logger.error(
                "incompatible_codes_found",
                encounter_id=encounter_id,
                incompatibility_count=len(incompatibilities),
                tenant_id=ctx.tenant_id,
            )
            raise IncompatibleCodes(
                _(
                    "Códigos incompatíveis detectados: {count} incompatibilidade(s) "
                    "encontrada(s) para o atendimento {enc}"
                ).format(count=len(incompatibilities), enc=encounter_id),
                details=output.to_variables(),
            )

        if warnings:
            self._logger.warning(
                "compatibility_warnings",
                encounter_id=encounter_id,
                warning_count=len(warnings),
                tenant_id=ctx.tenant_id,
            )

        self._logger.info(
            "compatibility_check_passed",
            encounter_id=encounter_id,
            warning_count=len(warnings),
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

def register_worker() -> CheckCodeCompatibilityWorker:
    """Create and return a configured CheckCodeCompatibilityWorker instance."""
    return CheckCodeCompatibilityWorker()

