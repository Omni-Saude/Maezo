"""Validate procedure compatibility rules (Refactored).

TOPIC: production.validate_compatibility
ARCHETYPE: ADMIN_ADJUDICATION
DMN: pricing/compatibility/procedure_compatibility_adjudication

Refactored: replaced incompatible pairs/frequency/gender/age rules with DMN call.

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides
"""

from __future__ import annotations

from typing import Any, Dict

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class ValidateCompatibilityWorker(BaseExternalTaskWorker):
    """Validates procedure compatibility using DMN rules.

    DMN handles: incompatible pairs, frequency limits, gender/age restrictions.
    Worker handles: input extraction, per-procedure DMN calls, result assembly.
    """

    TOPIC = "revenue_cycle.production.validate_compatibility"
    DMN_DECISION_KEY = "procedure_compatibility_adjudication"
    DMN_CATEGORY = "pricing"

    def execute(self, context: TaskContext) -> TaskResult:
        """Validate procedure compatibility."""
        try:
            variables = context.variables
            procedures = variables.get("priced_procedures", [])
            patient_gender = variables.get("patient_gender", "")
            patient_age = variables.get("patient_age_years")

            if not procedures:
                return TaskResult.bpmn_error(
                    error_code="CODING_ERROR",
                    error_message="No procedures to validate",
                )

            codes = [p.get("code", "") for p in procedures]
            code_counts = {}
            for code in codes:
                code_counts[code] = code_counts.get(code, 0) + 1

            self.logger.info(
                f"Validating compatibility: {len(procedures)} procedures",
                extra={"tenant_id": context.tenant_id},
            )

            warnings = []

            # Evaluate DMN for the full procedure set
            dmn_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DECISION_KEY,
                variables={
                    "procedureCodes": ",".join(codes),
                    "procedureCount": len(codes),
                    "patientGender": patient_gender or "",
                    "patientAgeYears": patient_age if patient_age is not None else -1,
                    "duplicateCodes": ",".join(c for c, n in code_counts.items() if n > 1),
                },
                category=self.DMN_CATEGORY,
            )

            resultado = dmn_result.get("resultado", "PROSSEGUIR")
            acao = dmn_result.get("acao", "")
            risco = dmn_result.get("risco", "BAIXO")

            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(
                    error_code="INCOMPATIBLE_CODES",
                    error_message=acao or "Incompatible procedures detected",
                    variables={"risk": risco, "codes": codes},
                )

            if resultado == "REVISAR":
                warnings.append(f"Review required: {acao}")

            # Add duplicate warnings
            for code, count in code_counts.items():
                if count > 1:
                    warnings.append(f"Procedure {code} appears {count} times - verify intentional")

            return TaskResult.success({
                "compatible_procedures": procedures,
                "compatibility_warnings": warnings,
                "all_compatible": True,
            })

        except Exception as e:
            self.logger.error(f"Compatibility validation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="CODING_ERROR",
                error_message=str(e),
            )
