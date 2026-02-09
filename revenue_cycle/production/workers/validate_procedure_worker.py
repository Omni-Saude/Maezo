"""Validate procedure codes against ANS Rol de Procedimentos.

CIB7 External Task Topic: production.validate_procedure
BPMN Error Codes: INVALID_PROCEDURE_CODE, CODING_ERROR
"""
from __future__ import annotations

from typing import Any

from platform.shared.domain.exceptions import CodingException, InvalidProcedureCode
from platform.shared.i18n import _
from platform.shared.integrations.ans_client import ANSClientProtocol, RolValidationResult
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


class ValidateProcedureWorker:
    """Validates TUSS/CBHPM procedure codes via ANS Rol API.

    Checks each procedure code for:
    - Existence in current ANS Rol
    - Active status (not terminated)
    - Coverage type compatibility
    """

    TOPIC = "production.validate_procedure"

    def __init__(self, ans_client: ANSClientProtocol) -> None:
        self._ans = ans_client
        self._logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(metric_name="production_validate_procedure")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Validate procedure codes against ANS Rol.

        Task Variables (input):
            procedure_codes: list[str] - TUSS/CBHPM codes to validate
            coverage_type: str - Expected coverage type (ambulatorial, hospitalar)

        Returns:
            validated_procedures: list[dict] - Validation results per code
            all_valid: bool - Whether all codes passed validation
            invalid_codes: list[str] - Codes that failed validation
        """
        ctx = get_required_tenant()
        procedure_codes: list[str] = task_variables.get("procedure_codes", [])
        coverage_type: str = task_variables.get("coverage_type", "")

        if not procedure_codes:
            raise CodingException(
                _("Invalid input: {field} - {reason}").format(
                    field="procedure_codes", reason="empty list"
                ),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "validating_procedures",
            codes_count=len(procedure_codes),
            coverage_type=coverage_type,
            tenant_id=ctx.tenant_id,
        )

        validated: list[dict[str, Any]] = []
        invalid_codes: list[str] = []

        for code in procedure_codes:
            result: RolValidationResult = await self._ans.validate_procedure(code)

            entry = {
                "code": code,
                "is_valid": result.is_valid,
                "is_covered": result.is_covered,
                "coverage_type": result.coverage_type,
                "name": result.procedure.name if result.procedure else "",
                "message": result.message,
            }
            validated.append(entry)

            if not result.is_valid:
                invalid_codes.append(code)
                self._logger.warning(
                    "procedure_invalid",
                    code=code,
                    message=result.message,
                    tenant_id=ctx.tenant_id,
                )
            elif coverage_type and result.coverage_type != coverage_type:
                self._logger.warning(
                    "procedure_coverage_mismatch",
                    code=code,
                    expected=coverage_type,
                    actual=result.coverage_type,
                    tenant_id=ctx.tenant_id,
                )

        all_valid = len(invalid_codes) == 0

        if not all_valid:
            self._logger.error(
                "procedure_validation_failed",
                invalid_count=len(invalid_codes),
                invalid_codes=invalid_codes,
                tenant_id=ctx.tenant_id,
            )
            raise InvalidProcedureCode(
                _("Procedure code not found in TUSS table: {code}").format(
                    code=", ".join(invalid_codes)
                ),
                details={"invalid_codes": invalid_codes},
            )

        self._logger.info(
            "procedures_validated",
            valid_count=len(validated),
            tenant_id=ctx.tenant_id,
        )

        return {
            "validated_procedures": validated,
            "all_valid": all_valid,
            "invalid_codes": invalid_codes,
        }
