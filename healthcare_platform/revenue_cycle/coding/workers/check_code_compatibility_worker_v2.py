"""Check CID-10 / TUSS code compatibility - V2 thin worker.
CIB7 External Task Topic: coding.check_compatibility
BPMN Error Codes: INCOMPATIBLE_CODES, CODING_ERROR
ORPHAN WARNING: No companion DMN tables exist yet.
Companion DMN tables required: code_compatibility/incompatible_matrix, warning_pairs
"""
from __future__ import annotations
import re
from typing import Any
from pydantic import BaseModel, Field
from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException, IncompatibleCodes
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService

class IncompatibilityDetail(BaseModel):
    cid10: str
    tuss: str
    reason: str

class CheckCodeCompatibilityOutputV2(BaseModel):
    compatible: bool = True
    incompatibilities: list[IncompatibilityDetail] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def to_variables(self) -> dict[str, Any]:
        return {"compatible": self.compatible, "incompatibilities": [i.model_dump() for i in self.incompatibilities], "warnings": self.warnings}
class CheckCodeCompatibilityWorkerV2:
    """V2 thin worker: delegates compatibility checks to DMN tables. ORPHAN: No companion DMN tables exist yet."""
    TOPIC = "coding.check_compatibility"

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

        """Core execution logic."""
        ctx = get_required_tenant()
        cid10 = task_variables.get("validatedCid10", [])
        tuss = task_variables.get("validatedTuss", [])
        enc_id = task_variables.get("encounterId", "")

        if not cid10:
            raise CodingException(_("Entrada inválida: lista de códigos CID-10 vazia"), bpmn_error_code="CODING_ERROR")
        if not tuss:
            raise CodingException(_("Entrada inválida: lista de códigos TUSS vazia"), bpmn_error_code="CODING_ERROR")

        self._logger.info("compatibility_v2_started", encounter_id=enc_id, cid10_count=len(cid10), tuss_count=len(tuss), tenant_id=ctx.tenant_id)

        incomp_res = self._evaluate_dmn("code_compatibility/incompatible_matrix", {"cid10_codes": cid10, "tuss_codes": tuss})
        incomps = self._extract_incompatibilities(incomp_res, "BLOQUEAR")
        warn_res = self._evaluate_dmn("code_compatibility/warning_pairs", {"cid10_codes": cid10, "tuss_codes": tuss})
        warns = self._extract_warnings(warn_res, "REVISAR")

        compat = len(incomps) == 0
        output = CheckCodeCompatibilityOutputV2(compatible=compat, incompatibilities=incomps, warnings=warns)

        if not compat:
            self._logger.error("incompatible_codes_v2", encounter_id=enc_id, incompatibility_count=len(incomps), tenant_id=ctx.tenant_id)
            raise IncompatibleCodes(_("Códigos incompatíveis detectados: {count} incompatibilidade(s)").format(count=len(incomps)), details=output.to_variables())

        if warns:
            self._logger.warning("compatibility_warnings_v2", encounter_id=enc_id, warning_count=len(warns), tenant_id=ctx.tenant_id)

        self._logger.info("compatibility_v2_passed", encounter_id=enc_id, warning_count=len(warns), tenant_id=ctx.tenant_id)
        return output.to_variables()

    def _evaluate_dmn(self, table_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.dmn_service.evaluate(tenant_id=get_required_tenant().tenant_id, category='coding_audit', table_name=table_name, inputs=inputs)
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback (ORPHAN)", table=table_name, error=str(e))
            return {}

    def _extract_incompatibilities(self, dmn_result: dict[str, Any], block_value: str) -> list[IncompatibilityDetail]:
        """Extract incompatibilities from DMN result. Supports 3-output and 5-output schemas."""
        res = dmn_result.get("resultado", "")
        dec = dmn_result.get("Decisao", "")
        if res == block_value or dec == "Bloquear":
            return [IncompatibilityDetail(cid10=dmn_result.get("cid10", ""), tuss=dmn_result.get("tuss", ""), reason=dmn_result.get("acao" if res else "Justificativa", "Incompatible" if res else "Blocked by rule"))]
        return []

    def _extract_warnings(self, dmn_result: dict[str, Any], review_value: str) -> list[str]:
        """Extract warnings from DMN result. Supports 3-output and 5-output schemas."""
        res = dmn_result.get("resultado", "")
        dec = dmn_result.get("Decisao", "")
        if res == review_value:
            return [dmn_result.get("acao", "Review required")]
        if dec in ("Revisar", "Alertar"):
            return [dmn_result.get("Justificativa", "Review recommended")]
        return []

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
        except IncompatibleCodes as e:
            return _Result(success=False, error_code="INCOMPATIBLE_CODES", error_message=str(e), variables=e.details or {})
        except Exception as e:
            error_code = getattr(e, 'bpmn_error_code', getattr(e, 'error_code', None))
            return _Result(success=False, error_code=error_code, error_message=str(e))

def register_worker() -> CheckCodeCompatibilityWorkerV2:
    return CheckCodeCompatibilityWorkerV2()
