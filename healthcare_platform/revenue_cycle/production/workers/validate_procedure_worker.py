"""Validate procedure codes against ANS Rol de Procedimentos.

CIB7 External Task Topic: production.validate_procedure
BPMN Error Codes: INVALID_PROCEDURE_CODE, CODING_ERROR
"""
from __future__ import annotations

from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import CodingException, InvalidProcedureCode
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.ans_client import ANSClientProtocol, RolValidationResult
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution


class ValidateProcedureWorker:
    """Validates TUSS/CBHPM procedure codes via ANS Rol API.

    Checks each procedure code for:
    - Existence in current ANS Rol
    - Active status (not terminated)
    - Coverage type compatibility

    Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = "production.validate_procedure"

    def __init__(
        self,
        ans_client: ANSClientProtocol,
        tasy_api_client: TasyApiClientProtocol | None = None,
    ) -> None:
        self._ans = ans_client
        self._tasy_api: TasyApiClientProtocol | None = tasy_api_client
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    async def _validate_via_tasy(
        self, code: str, coverage_type: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """Validate procedure via TASY procedure master.

        Falls back to None if TASY is unavailable - caller will use ANS.

        Args:
            code: Procedure code to validate
            coverage_type: Expected coverage type
            tenant_id: Current tenant ID for logging

        Returns:
            Validation result dict or None if TASY unavailable
        """
        try:
            # Get procedure details from TASY
            details = await self._tasy_api.get_tuss_procedure_details(code)

            # Get compatible procedures for enhanced validation
            compatible = await self._tasy_api.get_compatible_procedures(code)

            is_valid = bool(details)
            is_covered = details.get("is_active", True) and not details.get("is_terminated", False)
            tasy_coverage_type = details.get("coverage_type", "")

            self._logger.info(
                "tasy_procedure_validated",
                code=code,
                is_valid=is_valid,
                is_covered=is_covered,
                compatible_count=len(compatible),
                tenant_id=tenant_id,
            )

            return {
                "code": code,
                "is_valid": is_valid,
                "is_covered": is_covered,
                "coverage_type": tasy_coverage_type,
                "name": details.get("name", ""),
                "message": _("Validado via TASY") if is_valid else _("Código não encontrado no TASY"),
            }

        except Exception as exc:
            # Fall back to ANS validation
            self._logger.info(
                "tasy_validation_unavailable",
                code=code,
                error=str(exc),
                tenant_id=tenant_id,
                message="Falling back to ANS validation",
            )
            return None

    def _evaluate_pricing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate pricing DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='pricing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

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
            # Try TASY validation first if available
            if self._tasy_api:
                tasy_result = await self._validate_via_tasy(code, coverage_type, ctx.tenant_id)
                if tasy_result:
                    validated.append(tasy_result)
                    if not tasy_result["is_valid"]:
                        invalid_codes.append(code)
                    continue

            # Fall back to ANS validation
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
