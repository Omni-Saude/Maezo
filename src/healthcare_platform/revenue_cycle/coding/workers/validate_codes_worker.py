"""Validate CID-10 and TUSS codes (thin DMN-federated worker).

CIB7 External Task Topic: coding.validate_coding
BPMN Error Codes: INVALID_CID10_CODE, INVALID_TUSS_CODE, CODING_ERROR

All business logic delegated to companion DMN tables.
Companion DMN tables:
- code_validation/cid10_format
- code_validation/cid10_incompatibility
- code_validation/tuss_format
- code_validation/tuss_coverage
- code_validation/tuss_cid10_requirements
"""
from __future__ import annotations
import re
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


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
        return {
            "validated_cid10": self.validated_cid10,
            "validated_tuss": self.validated_tuss,
            "validation_errors": self.validation_errors,
            "all_valid": self.all_valid,
        }


class ValidateCodesWorker(BaseExternalTaskWorker):
    """Thin DMN-federated worker for code validation.

    Delegates all business logic to companion DMN tables in code_validation/.
    """

    TOPIC = "revenue_cycle.coding.validate_coding"

    def __init__(self, dmn_service: FederatedDMNService | None = None, ans_client: Any = None, **kwargs: Any) -> None:
        super().__init__(dmn_service=dmn_service)
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = dmn_service or FederatedDMNService()


    async def execute(self, task_or_variables: Any) -> dict[str, Any]:

        """Execute worker with dict or mock_task (v1 compatibility)."""

        # V1 compatibility: handle mock_task objects

        if hasattr(task_or_variables, 'get_variable'):

            variables = self._extract_variables_from_mock_task(task_or_variables)

            try:

                result = await self._execute_impl(variables)

                await task_or_variables.complete(result)

                return result

            except BpmnErrorException as e:

                await task_or_variables.bpmn_error(e.error_code, str(e))

                raise

        else:

            # Standard pattern: dict input

            return await self._execute_impl(task_or_variables)


    def _extract_variables_from_mock_task(self, mock_task: Any) -> dict[str, Any]:

        """Extract variables from v1 mock_task object."""

        # Extract with both camelCase and snake_case

        def get_val(key, alt_key=None):

            val = mock_task.get_variable(key)

            if val is None and alt_key:

                val = mock_task.get_variable(alt_key)

            return val


        variables = {}

        

        # Common mappings

        if (val := get_val('encounter_id', 'encounterId')) is not None:

            variables['encounterId'] = val

        if (val := get_val('tenant_id', 'tenantId')) is not None:

            variables['tenantId'] = val

        if (val := get_val('patient_id', 'patientId')) is not None:

            variables['patientId'] = val


        # Code lists

        for key_pair in [('cid10_codes', 'validatedCid10'), ('tuss_codes', 'validatedTuss'), 

                         ('suggested_cid10_codes', 'suggestedCid10Codes'), 

                         ('suggested_tuss_codes', 'suggestedTussCodes')]:

            if (val := get_val(key_pair[0], key_pair[1])) is not None:

                variables[key_pair[1]] = val


        # Other fields

        for field in ['clinicalNotes', 'proceduresText', 'codedBy', 'patientAge', 

                      'comorbidities', 'encounterClass', 'auditStatus', 'fraudRiskLevel']:

            snake = re.sub(r'([a-z])([A-Z])', r'_', field).lower()

            if (val := get_val(snake, field)) is not None:

                variables[field] = val


        # Extract rules from coding_rules_result

        if (coding_result := get_val('coding_rules_result', 'codingRulesResult')) is not None:

            if isinstance(coding_result, dict):

                variables['rulesApplied'] = coding_result.get('rules', [])

            variables['codingRulesResult'] = coding_result


        return variables


    async def _execute_impl(self, task_variables: dict[str, Any]) -> dict[str, Any]:

        """Core execution logic."""        """Validate CID-10 and TUSS codes via DMN rules.

        Task Variables (input):
            suggested_cid10_codes: list[dict]
            suggested_tuss_codes: list[dict]
            encounter_id: str
            tenant_id: str

        Returns:
            validated_cid10: list[dict]
            validated_tuss: list[dict]
            validation_errors: list[dict]
            all_valid: bool
        """
        ctx = get_required_tenant()
        inp = ValidateCodesInput(**task_variables)

        if not inp.suggested_cid10_codes and not inp.suggested_tuss_codes:
            raise CodingException(
                _("Nenhum código para validar"),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "validating_codes",
            cid10_count=len(inp.suggested_cid10_codes),
            tuss_count=len(inp.suggested_tuss_codes),
            tenant_id=ctx.tenant_id,
        )

        errors: list[dict[str, Any]] = []

        # Step 1: Validate CID-10 format
        cid10_format_result = self._evaluate_dmn(
            "code_validation", "cid10_format",
            {"suggested_cid10_codes": inp.suggested_cid10_codes}
        )
        validated_cid10 = cid10_format_result.get("validated_cid10", [])
        errors.extend(cid10_format_result.get("errors", []))

        # Step 2: Check CID-10 incompatibility
        compat_result = self._evaluate_dmn(
            "code_validation", "cid10_incompatibility",
            {"validated_cid10": validated_cid10}
        )
        errors.extend(compat_result.get("errors", []))

        # Step 3: Validate TUSS format
        tuss_format_result = self._evaluate_dmn(
            "code_validation", "tuss_format",
            {"suggested_tuss_codes": inp.suggested_tuss_codes}
        )
        format_valid_tuss = tuss_format_result.get("format_valid_tuss", [])
        errors.extend(tuss_format_result.get("errors", []))

        # Step 4: Check TUSS coverage
        coverage_result = self._evaluate_dmn(
            "code_validation", "tuss_coverage",
            {"format_valid_tuss": format_valid_tuss}
        )
        validated_tuss = coverage_result.get("validated_tuss", [])
        errors.extend(coverage_result.get("errors", []))

        # Step 5: Check TUSS-CID10 requirements
        cid10_codes = [c.get("code", "")[:3] for c in validated_cid10]
        requirements_result = self._evaluate_dmn(
            "code_validation", "tuss_cid10_requirements",
            {"validated_tuss": validated_tuss, "cid10_codes": cid10_codes}
        )
        errors.extend(requirements_result.get("errors", []))

        all_valid = len(errors) == 0

        if not all_valid:
            self._logger.warning(
                "codes_validation_failed",
                error_count=len(errors),
                tenant_id=ctx.tenant_id,
            )

            # Raise BPMN errors for critical failures
            if errors and not validated_cid10:
                raise BpmnErrorException(
                    error_code="INVALID_CID10_CODE",
                    message=_("Todos os códigos CID-10 falharam na validação"),
                )

            if errors and not validated_tuss:
                raise BpmnErrorException(
                    error_code="INVALID_TUSS_CODE",
                    message=_("Todos os códigos TUSS falharam na validação"),
                )

        output = ValidateCodesOutput(
            validated_cid10=validated_cid10,
            validated_tuss=validated_tuss,
            validation_errors=errors,
            all_valid=all_valid,
        )

        self._logger.info(
            "codes_validated",
            valid_cid10=len(validated_cid10),
            valid_tuss=len(validated_tuss),
            all_valid=all_valid,
            tenant_id=ctx.tenant_id,
        )

        return output.to_variables()

    def _evaluate_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate coding_audit DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=get_required_tenant().tenant_id,
                category='coding_audit',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}


    async def process_task(self, job: Any = None, variables: dict[str, Any] | None = None) -> Any:
        """V1 backward-compatible entry point for tests."""
        from dataclasses import dataclass, field
        from typing import Dict, Optional

        @dataclass
        class _Result:
            success: bool
            variables: Dict[str, Any] = field(default_factory=dict)
            error_code: Optional[str] = None
            error_message: Optional[str] = None

        if variables is None:
            variables = {}

        try:
            result = await self.execute(variables)
            return _Result(success=True, variables=result)
        except BpmnErrorException as e:
            return _Result(success=False, error_code=e.error_code, error_message=str(e), variables=e.details or {})
        except Exception as e:
            error_code = getattr(e, 'bpmn_error_code', getattr(e, 'error_code', None))
            return _Result(success=False, error_code=error_code, error_message=str(e))

def register_worker(dmn_service: FederatedDMNService | None = None) -> ValidateCodesWorker:
    """Create and return a configured ValidateCodesWorker instance."""
    return ValidateCodesWorker(dmn_service=dmn_service)
