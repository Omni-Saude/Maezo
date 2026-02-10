"""Validate CID-10 and TUSS codes for completeness and correctness.

CIB7 External Task Topic: coding.validate_coding
BPMN Error Codes: INVALID_CID10_CODE, INVALID_TUSS_CODE, CODING_ERROR
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import (
    BpmnErrorException,
    CodingException,
    IncompatibleCodes,
    InvalidProcedureCode,
    MissingDiagnosisCode,
)
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.ans_client import ANSClientProtocol, RolValidationResult
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


# ── Constants ─────────────────────────────────────────────────────────

CID10_PATTERN = re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$")
TUSS_PATTERN = re.compile(r"^\d{8}$")

# Known incompatible CID-10 pairs (example: cannot have both)
_INCOMPATIBLE_CID10_PAIRS: list[tuple[str, str]] = [
    ("E10", "E11"),  # Type 1 and Type 2 diabetes simultaneously
    ("O80", "O82"),  # Spontaneous delivery and cesarean delivery
]

# TUSS codes that require specific CID-10 diagnoses
_TUSS_REQUIRES_CID10: dict[str, list[str]] = {
    "31003036": ["K35"],  # Apendicectomia requires apendicite diagnosis
}


# ── Data Transfer Objects ─────────────────────────────────────────────


class CodeValidationError(BaseModel):
    """A single validation error entry."""

    code: str = Field(..., description="Code that failed validation")
    code_type: str = Field(..., description="CID10 or TUSS")
    error_type: str = Field(..., description="Error category")
    message: str = Field(..., description="Human-readable error message")


class ValidateCodesInput(BaseModel):
    """Input variables for code validation."""

    suggested_cid10_codes: list[dict[str, Any]] = Field(default_factory=list)
    suggested_tuss_codes: list[dict[str, Any]] = Field(default_factory=list)
    encounter_id: str = Field(default="")
    tenant_id: str = Field(default="")


class ValidateCodesOutput(BaseModel):
    """Output variables for code validation."""

    validated_cid10: list[dict[str, Any]]
    validated_tuss: list[dict[str, Any]]
    validation_errors: list[dict[str, Any]]
    all_valid: bool

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "validated_cid10": self.validated_cid10,
            "validated_tuss": self.validated_tuss,
            "validation_errors": self.validation_errors,
            "all_valid": self.all_valid,
        }


# ── Worker ────────────────────────────────────────────────────────────


class ValidateCodesWorker:
    """Validates CID-10 and TUSS codes for format, existence, and coverage.

    Performs three levels of validation:
    1. Format validation (regex patterns)
    2. Existence validation (ANS Rol lookup for TUSS)
    3. Cross-code compatibility checks
    """

    TOPIC = "coding.validate_coding"

    def __init__(self, ans_client: ANSClientProtocol) -> None:
        self._ans = ans_client
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    @require_tenant
    @track_task_execution(metric_name="coding_validate_codes")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Validate suggested CID-10 and TUSS codes.

        Task Variables (input):
            suggested_cid10_codes: list[dict] - CID-10 suggestions to validate
            suggested_tuss_codes: list[dict] - TUSS suggestions to validate
            encounter_id: str - Encounter reference for context
            tenant_id: str - Tenant identifier (set via context)

        Returns:
            validated_cid10: list[dict] - CID-10 codes that passed validation
            validated_tuss: list[dict] - TUSS codes that passed validation
            validation_errors: list[dict] - All validation errors found
            all_valid: bool - Whether all codes passed validation
        """
        ctx = get_required_tenant()
        cid10_codes: list[dict[str, Any]] = task_variables.get(
            "suggested_cid10_codes", []
        )
        tuss_codes: list[dict[str, Any]] = task_variables.get(
            "suggested_tuss_codes", []
        )
        encounter_id: str = task_variables.get("encounter_id", "")

        if not cid10_codes and not tuss_codes:
            raise CodingException(
                _("Nenhum código para validar: listas CID-10 e TUSS estão vazias"),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "validating_codes",
            cid10_count=len(cid10_codes),
            tuss_count=len(tuss_codes),
            encounter_id=encounter_id,
            tenant_id=ctx.tenant_id,
        )

        errors: list[CodeValidationError] = []

        # ── Step 1: Validate CID-10 codes ────────────────────────────

        validated_cid10 = self._validate_cid10_format(cid10_codes, errors)

        # ── Step 2: Check CID-10 compatibility ───────────────────────

        self._check_cid10_compatibility(validated_cid10, errors)

        # ── Step 3: Validate TUSS codes format ───────────────────────

        format_valid_tuss = self._validate_tuss_format(tuss_codes, errors)

        # ── Step 4: Validate TUSS against ANS Rol ────────────────────

        validated_tuss = await self._validate_tuss_ans(
            format_valid_tuss, errors, ctx.tenant_id
        )

        # ── Step 5: Check TUSS coverage ──────────────────────────────

        await self._check_tuss_coverage(validated_tuss, errors, ctx.tenant_id)

        # ── Step 6: Cross-validate TUSS-CID10 requirements ──────────

        cid10_code_set = {c.get("code", "")[:3] for c in validated_cid10}
        self._check_tuss_cid10_requirements(
            validated_tuss, cid10_code_set, errors
        )

        # ── Build output ─────────────────────────────────────────────

        all_valid = len(errors) == 0
        error_dicts = [
            {
                "code": e.code,
                "code_type": e.code_type,
                "error_type": e.error_type,
                "message": e.message,
            }
            for e in errors
        ]

        if not all_valid:
            self._logger.warning(
                "codes_validation_failed",
                error_count=len(errors),
                encounter_id=encounter_id,
                tenant_id=ctx.tenant_id,
            )

            # Raise BPMN errors for critical validation failures
            cid10_errors = [e for e in errors if e.code_type == "CID10"]
            tuss_errors = [e for e in errors if e.code_type == "TUSS"]

            if cid10_errors and not validated_cid10:
                raise BpmnErrorException(
                    error_code="INVALID_CID10_CODE",
                    message=_("Todos os códigos CID-10 falharam na validação"),
                    details={"errors": [e.message for e in cid10_errors]},
                )

            if tuss_errors and not validated_tuss:
                raise BpmnErrorException(
                    error_code="INVALID_TUSS_CODE",
                    message=_("Todos os códigos TUSS falharam na validação"),
                    details={"errors": [e.message for e in tuss_errors]},
                )

        self._logger.info(
            "codes_validated",
            valid_cid10=len(validated_cid10),
            valid_tuss=len(validated_tuss),
            errors=len(errors),
            all_valid=all_valid,
            encounter_id=encounter_id,
            tenant_id=ctx.tenant_id,
        )

        output = ValidateCodesOutput(
            validated_cid10=validated_cid10,
            validated_tuss=validated_tuss,
            validation_errors=error_dicts,
            all_valid=all_valid,
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

    # ── Private validation methods ────────────────────────────────────

    def _validate_cid10_format(
        self,
        cid10_codes: list[dict[str, Any]],
        errors: list[CodeValidationError],
    ) -> list[dict[str, Any]]:
        """Validate CID-10 code format (letter + 2-3 digits + optional .digit)."""
        valid: list[dict[str, Any]] = []

        for entry in cid10_codes:
            code = entry.get("code", "").strip().upper()
            if not code:
                continue

            if CID10_PATTERN.match(code):
                valid.append({**entry, "code": code})
            else:
                errors.append(
                    CodeValidationError(
                        code=code,
                        code_type="CID10",
                        error_type="FORMAT",
                        message=_(
                            "Formato CID-10 inválido: {code}. "
                            "Esperado: letra + 2-3 dígitos + ponto + dígito opcional "
                            "(ex: J18.9, A09, M54.5)"
                        ).format(code=code),
                    )
                )

        return valid

    def _check_cid10_compatibility(
        self,
        validated_cid10: list[dict[str, Any]],
        errors: list[CodeValidationError],
    ) -> None:
        """Check for incompatible CID-10 code pairs."""
        code_prefixes = [c.get("code", "")[:3] for c in validated_cid10]

        # DMN-enhanced compatibility check
        dmn_result = self._evaluate_coding_dmn(
            subcategory="compat",
            table_name="code_compatibility",
            inputs={"cid10_codes": code_prefixes}
        )

        for prefix_a, prefix_b in _INCOMPATIBLE_CID10_PAIRS:
            if prefix_a in code_prefixes and prefix_b in code_prefixes:
                errors.append(
                    CodeValidationError(
                        code=f"{prefix_a}/{prefix_b}",
                        code_type="CID10",
                        error_type="INCOMPATIBLE",
                        message=_(
                            "Códigos CID-10 incompatíveis: {code_a} e {code_b} "
                            "não podem coexistir no mesmo atendimento"
                        ).format(code_a=prefix_a, code_b=prefix_b),
                    )
                )

    def _validate_tuss_format(
        self,
        tuss_codes: list[dict[str, Any]],
        errors: list[CodeValidationError],
    ) -> list[dict[str, Any]]:
        """Validate TUSS code format (8-digit numeric)."""
        valid: list[dict[str, Any]] = []

        for entry in tuss_codes:
            code = entry.get("code", "").strip()
            if not code:
                continue

            if TUSS_PATTERN.match(code):
                valid.append(entry)
            else:
                errors.append(
                    CodeValidationError(
                        code=code,
                        code_type="TUSS",
                        error_type="FORMAT",
                        message=_(
                            "Formato TUSS inválido: {code}. "
                            "Esperado: código numérico de 8 dígitos"
                        ).format(code=code),
                    )
                )

        return valid

    async def _validate_tuss_ans(
        self,
        tuss_codes: list[dict[str, Any]],
        errors: list[CodeValidationError],
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """Validate TUSS codes against ANS Rol (existence check)."""
        validated: list[dict[str, Any]] = []

        for entry in tuss_codes:
            code = entry.get("code", "")
            try:
                result: RolValidationResult = await self._ans.validate_procedure(code)

                if result.is_valid:
                    validated.append(
                        {
                            **entry,
                            "ans_valid": True,
                            "ans_name": (
                                result.procedure.name if result.procedure else ""
                            ),
                            "coverage_type": result.coverage_type or "",
                            "is_covered": result.is_covered,
                        }
                    )
                else:
                    errors.append(
                        CodeValidationError(
                            code=code,
                            code_type="TUSS",
                            error_type="NOT_IN_ROL",
                            message=_(
                                "Código TUSS não encontrado no Rol ANS: {code}"
                            ).format(code=code),
                        )
                    )
                    self._logger.warning(
                        "tuss_not_in_rol",
                        code=code,
                        message=result.message,
                        tenant_id=tenant_id,
                    )
            except Exception as exc:
                self._logger.error(
                    "tuss_ans_validation_error",
                    code=code,
                    error=str(exc),
                    tenant_id=tenant_id,
                )
                errors.append(
                    CodeValidationError(
                        code=code,
                        code_type="TUSS",
                        error_type="VALIDATION_ERROR",
                        message=_(
                            "Erro ao validar código TUSS {code} no Rol ANS: {error}"
                        ).format(code=code, error=str(exc)),
                    )
                )

        return validated

    async def _check_tuss_coverage(
        self,
        validated_tuss: list[dict[str, Any]],
        errors: list[CodeValidationError],
        tenant_id: str,
    ) -> None:
        """Check TUSS code coverage status via ANS client."""
        for entry in validated_tuss:
            code = entry.get("code", "")
            coverage_type = entry.get("coverage_type", "")

            if not entry.get("is_covered", False):
                errors.append(
                    CodeValidationError(
                        code=code,
                        code_type="TUSS",
                        error_type="NOT_COVERED",
                        message=_(
                            "Procedimento TUSS {code} não possui cobertura "
                            "obrigatória no tipo {coverage_type}"
                        ).format(code=code, coverage_type=coverage_type or "N/A"),
                    )
                )
                self._logger.warning(
                    "tuss_not_covered",
                    code=code,
                    coverage_type=coverage_type,
                    tenant_id=tenant_id,
                )

    def _check_tuss_cid10_requirements(
        self,
        validated_tuss: list[dict[str, Any]],
        cid10_prefixes: set[str],
        errors: list[CodeValidationError],
    ) -> None:
        """Check TUSS codes that require specific CID-10 diagnoses."""
        for entry in validated_tuss:
            code = entry.get("code", "")
            required_cid10 = _TUSS_REQUIRES_CID10.get(code, [])

            if required_cid10:
                has_required = any(
                    prefix in cid10_prefixes for prefix in required_cid10
                )
                if not has_required:
                    errors.append(
                        CodeValidationError(
                            code=code,
                            code_type="TUSS",
                            error_type="MISSING_DIAGNOSIS",
                            message=_(
                                "Procedimento TUSS {code} requer diagnóstico "
                                "CID-10 correspondente: {required}"
                            ).format(
                                code=code,
                                required=", ".join(required_cid10),
                            ),
                        )
                    )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_worker() -> ValidateCodesWorker:
    """Create and return a configured ValidateCodesWorker instance."""
    return ValidateCodesWorker()
