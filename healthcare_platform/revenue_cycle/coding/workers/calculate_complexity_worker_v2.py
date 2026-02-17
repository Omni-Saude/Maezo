"""Calculate clinical complexity score - V2 thin worker.
CIB7 External Task Topic: coding.calculate_complexity
BPMN Error Codes: CODING_ERROR
Companion DMN tables: complexity_scoring/diagnosis_count, age_factors, encounter_class_weight
"""
from __future__ import annotations
import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService

class CalculateComplexityOutputV2(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    complexity_score: int = Field(..., alias="complexityScore", ge=0)
    complexity_level: str = Field(..., alias="complexityLevel")
    complexity_factors: list[dict[str, Any]] = Field(default_factory=list, alias="complexityFactors")
    suggested_drg: str = Field(..., alias="suggestedDRG")

    def to_variables(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)
class CalculateComplexityWorkerV2:
    """V2 thin worker: delegates complexity calculation to DMN tables."""
    TOPIC = "coding.calculate_complexity"

    def __init__(self, **kwargs: Any) -> None:
        """Initialize worker with optional v1 compatibility params (ignored)."""
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()


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
        """Core execution logic - receives dict of variables."""
        ctx = get_required_tenant()
        enc_id = task_variables.get("encounterId", "")
        cid10 = task_variables.get("validatedCid10", [])
        tuss = task_variables.get("validatedTuss", [])
        enc_cls = task_variables.get("encounterClass", "")
        age = task_variables.get("patientAge", 0)
        comorbid = task_variables.get("comorbidities", [])

        if not enc_id or not enc_cls:
            raise CodingException(_("Dados de entrada inválidos para cálculo de complexidade"), bpmn_error_code="CODING_ERROR")

        self._logger.info("complexity_v2_started", encounter_id=enc_id, cid10_count=len(cid10), tuss_count=len(tuss), patient_age=age, tenant_id=ctx.tenant_id)

        factors, total = [], 0.0
        diag_res = self._evaluate_dmn("complexity_scoring/diagnosis_count", {"diagnosis_count": len(cid10), "comorbidity_count": len(comorbid)})
        diag_contrib = float(diag_res.get("contribution", len(cid10) * 0.5))
        factors.append({"factor": "diagnosis_count", "weight": 0.5, "contribution": round(diag_contrib, 2)})
        total += diag_contrib

        age_res = self._evaluate_dmn("complexity_scoring/age_factors", {"patient_age": age})
        age_fac = float(age_res.get("age_factor", 1.0))
        factors.append({"factor": "age_factor", "weight": age_fac, "contribution": round(age_fac, 2)})
        total += age_fac

        enc_res = self._evaluate_dmn("complexity_scoring/encounter_class_weight", {"encounter_class": enc_cls})
        enc_wt = float(enc_res.get("weight", 1.0))
        factors.append({"factor": "encounter_class", "weight": enc_wt, "contribution": round(enc_wt, 2)})
        total += enc_wt

        score = max(1, min(int(round(total)), 15))
        level_map = {3: ("LOW", "DRG-001"), 6: ("MODERATE", "DRG-002"), 9: ("HIGH", "DRG-003")}
        level, drg = next(((l, d) for thresh, (l, d) in level_map.items() if score <= thresh), ("VERY_HIGH", "DRG-004"))

        self._logger.info("complexity_v2_completed", encounter_id=enc_id, score=score, level=level, suggested_drg=drg, tenant_id=ctx.tenant_id)

        output = CalculateComplexityOutputV2(complexity_score=score, complexity_level=level, complexity_factors=factors, suggested_drg=drg)
        return output.to_variables()

    def _evaluate_dmn(self, table_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.dmn_service.evaluate(tenant_id=get_required_tenant().tenant_id, category='coding_audit', table_name=table_name, inputs=inputs)
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

def register_worker() -> CalculateComplexityWorkerV2:
    return CalculateComplexityWorkerV2()
