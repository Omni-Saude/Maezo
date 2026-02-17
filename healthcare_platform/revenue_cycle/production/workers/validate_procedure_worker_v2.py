"""Validate procedure codes against ANS Rol de Procedimentos (Refactored).

TOPIC: production.validate_procedure
ARCHETYPE: ADMIN_ADJUDICATION
DMN: pricing/validation/procedure_code_adjudication

Refactored: replaced TASY/ANS validation chain with DMN call.

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


class ValidateProcedureWorker(BaseExternalTaskWorker):
    """Validates TUSS/CBHPM procedure codes using DMN rules.

    DMN handles: code existence, active status, coverage compatibility.
    Worker handles: input parsing, per-code DMN calls, result assembly.
    """

    TOPIC = "production.validate_procedure"
    DMN_DECISION_KEY = "procedure_code_adjudication"
    DMN_CATEGORY = "pricing"

    def execute(self, context: TaskContext) -> TaskResult:
        """Validate procedure codes against ANS Rol via DMN."""
        try:
            variables = context.variables
            procedure_codes = variables.get("procedure_codes", [])
            coverage_type = variables.get("coverage_type", "")

            if not procedure_codes:
                return TaskResult.bpmn_error(
                    error_code="CODING_ERROR",
                    error_message="No procedure codes to validate",
                )

            self.logger.info(
                f"Validating {len(procedure_codes)} procedure codes",
                extra={"tenant_id": context.tenant_id, "coverage_type": coverage_type},
            )

            validated = []
            invalid_codes = []

            for code in procedure_codes:
                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_DECISION_KEY,
                    variables={
                        "procedureCode": code,
                        "coverageType": coverage_type,
                    },
                    category=self.DMN_CATEGORY,
                )

                resultado = dmn_result.get("resultado", "PROSSEGUIR")
                acao = dmn_result.get("acao", "")
                risco = dmn_result.get("risco", "BAIXO")

                entry = {
                    "code": code,
                    "is_valid": resultado == "PROSSEGUIR",
                    "is_covered": resultado != "BLOQUEAR",
                    "coverage_type": dmn_result.get("coverageType", coverage_type),
                    "name": dmn_result.get("procedureName", ""),
                    "message": acao,
                }
                validated.append(entry)

                if resultado == "BLOQUEAR":
                    invalid_codes.append(code)

            if invalid_codes:
                return TaskResult.bpmn_error(
                    error_code="INVALID_PROCEDURE_CODE",
                    error_message=f"Invalid codes: {', '.join(invalid_codes)}",
                    variables={
                        "validated_procedures": validated,
                        "invalid_codes": invalid_codes,
                    },
                )

            return TaskResult.success({
                "validated_procedures": validated,
                "all_valid": True,
                "invalid_codes": [],
            })

        except Exception as e:
            self.logger.error(f"Procedure validation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="CODING_ERROR",
                error_message=str(e),
            )
