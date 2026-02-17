"""Suggest CID-10 codes from clinical text (thin DMN-federated worker).

CIB7 External Task Topic: coding.suggest_cid10
BPMN Error Codes: CODING_ERROR

Refactored v2: All business logic delegated to companion DMN tables.
Companion DMN tables:
- cid10_suggestion/confidence_boosting
- cid10_suggestion/format_validation
"""
from __future__ import annotations
import re
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


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
        return {
            "suggested_cid10_codes": self.suggested_cid10_codes,
            "primary_cid10": self.primary_cid10,
            "cid10_count": self.cid10_count,
        }


class SuggestCid10WorkerV2(BaseExternalTaskWorker):
    """Thin DMN-federated worker for CID-10 code suggestion.

    Delegates all business logic to companion DMN tables in cid10_suggestion/.
    """

    TOPIC = "revenue_cycle.coding.suggest_cid10"

    def __init__(self, dmn_service: FederatedDMNService | None = None, nlp_engine: Any = None, **kwargs: Any) -> None:
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

            # V2 pattern: dict input

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

        """Core execution logic."""        """Suggest CID-10 codes via DMN-driven keyword extraction.

        Task Variables (input):
            clinical_notes: str
            extracted_diagnoses: list[dict]
            encounter_class: str
            tenant_id: str

        Returns:
            suggested_cid10_codes: list[dict]
            primary_cid10: str
            cid10_count: int
        """
        ctx = get_required_tenant()
        inp = SuggestCid10Input(**task_variables)

        if not inp.clinical_notes and not inp.extracted_diagnoses:
            raise CodingException(
                _("Dados clínicos insuficientes para sugestão de CID-10"),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "suggesting_cid10_v2",
            notes_length=len(inp.clinical_notes),
            extracted_count=len(inp.extracted_diagnoses),
            tenant_id=ctx.tenant_id,
        )

        # Call companion DMN for confidence boosting
        boost_result = self._evaluate_dmn(
            "cid10_suggestion", "confidence_boosting",
            {
                "clinical_notes": inp.clinical_notes,
                "extracted_diagnoses": inp.extracted_diagnoses,
                "encounter_class": inp.encounter_class,
            }
        )

        suggestions = boost_result.get("suggestions", [])

        # Call companion DMN for format validation
        validation_result = self._evaluate_dmn(
            "cid10_suggestion", "format_validation",
            {"suggestions": suggestions}
        )

        valid_suggestions = validation_result.get("valid_suggestions", [])
        primary_cid10 = valid_suggestions[0]["code"] if valid_suggestions else ""

        output = SuggestCid10Output(
            suggested_cid10_codes=valid_suggestions,
            primary_cid10=primary_cid10,
            cid10_count=len(valid_suggestions),
        )

        self._logger.info(
            "cid10_suggestions_complete_v2",
            cid10_count=output.cid10_count,
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

def register_worker(dmn_service: FederatedDMNService | None = None) -> SuggestCid10WorkerV2:
    """Create and return a configured SuggestCid10WorkerV2 instance."""
    return SuggestCid10WorkerV2(dmn_service=dmn_service)
