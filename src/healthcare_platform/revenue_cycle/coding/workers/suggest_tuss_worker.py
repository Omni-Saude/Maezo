"""Suggest TUSS codes based on procedures and CID-10 context (thin DMN-federated worker).

CIB7 External Task Topic: coding.suggest_tuss
BPMN Error Codes: CODING_ERROR

All business logic delegated to companion DMN tables.
Companion DMN tables:
- tuss_suggestion/cid10_correlation
- tuss_suggestion/format_validation
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
        return {
            "suggested_tuss_codes": self.suggested_tuss_codes,
            "tuss_count": self.tuss_count,
        }


class SuggestTussWorker(BaseExternalTaskWorker):
    """Thin DMN-federated worker for TUSS code suggestion.

    Delegates all business logic to companion DMN tables in tuss_suggestion/.
    """

    TOPIC = "revenue_cycle.coding.suggest_tuss"

    def __init__(self, dmn_service: FederatedDMNService | None = None, procedure_mapper: Any = None, **kwargs: Any) -> None:
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

        """Core execution logic."""        """Suggest TUSS codes from procedures and CID-10 context via DMN.

        Task Variables (input):
            extracted_procedures: list[dict]
            suggested_cid10_codes: list[dict]
            encounter_class: str
            tenant_id: str

        Returns:
            suggested_tuss_codes: list[dict]
            tuss_count: int
        """
        ctx = get_required_tenant()
        inp = SuggestTussInput(**task_variables)

        if not inp.extracted_procedures and not inp.suggested_cid10_codes:
            raise CodingException(
                _("Dados insuficientes para sugestão de TUSS"),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "suggesting_tuss",
            procedures_count=len(inp.extracted_procedures),
            cid10_count=len(inp.suggested_cid10_codes),
            tenant_id=ctx.tenant_id,
        )

        # Call companion DMN for CID-10 correlation
        correlation_result = self._evaluate_dmn(
            "tuss_suggestion", "cid10_correlation",
            {
                "extracted_procedures": inp.extracted_procedures,
                "suggested_cid10_codes": inp.suggested_cid10_codes,
                "encounter_class": inp.encounter_class,
            }
        )

        raw_suggestions = correlation_result.get("raw_suggestions", [])

        # Call companion DMN for format validation
        validation_result = self._evaluate_dmn(
            "tuss_suggestion", "format_validation",
            {"raw_suggestions": raw_suggestions}
        )

        validated = validation_result.get("validated_tuss", [])

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
        except Exception as e:
            error_code = getattr(e, 'bpmn_error_code', getattr(e, 'error_code', None))
            return _Result(success=False, error_code=error_code, error_message=str(e))

def register_worker(dmn_service: FederatedDMNService | None = None) -> SuggestTussWorker:
    """Create and return a configured SuggestTussWorker instance."""
    return SuggestTussWorker(dmn_service=dmn_service)
