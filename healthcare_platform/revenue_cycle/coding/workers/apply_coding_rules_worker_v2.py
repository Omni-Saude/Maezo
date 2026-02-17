"""Apply DMN coding rules to validated codes - V2 thin worker.
CIB7 External Task Topic: coding.apply_rules
BPMN Error Codes: CODING_RULE_VIOLATION, CODING_ERROR
ORPHAN WARNING: No companion DMN tables exist yet.
Companion DMN tables required: coding_rules/quantity_limits, bundling_validation, modifier_requirements, specialty_restrictions
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
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService

class ApplyCodingRulesOutputV2(BaseModel):
    rules_passed: bool = Field(True, alias="rulesPassed")
    rule_violations: list[dict[str, Any]] = Field(default_factory=list, alias="ruleViolations")
    modifiers_required: list[str] = Field(default_factory=list, alias="modifiersRequired")

    def to_variables(self) -> dict[str, Any]:
        return {"rulesPassed": self.rules_passed, "ruleViolations": self.rule_violations, "modifiersRequired": self.modifiers_required}
class ApplyCodingRulesWorkerV2:
    """V2 thin worker: delegates rule logic to DMN tables. ORPHAN: No companion DMN tables exist yet."""
    TOPIC = "coding.apply_rules"

    def __init__(self, dmn_service: FederatedDMNService | None = None, rules_engine: Any | None = None) -> None:
        """Initialize worker with optional dependency injection for testing.

        Args:
            dmn_service: Optional FederatedDMNService instance (for testing)
            rules_engine: Legacy parameter for v1 test compatibility (ignored)
        """
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

        """Core execution logic."""        """Execute coding rules worker.

        Args:
            task_variables: Either dict of variables (v2) or mock task object (v1 test compatibility)

        Returns:
            Dict of output variables
        """
        # V1 test compatibility: if task_variables is a mock task object, extract variables
        if hasattr(task_variables, 'get_variable'):
            # V1 pattern: extract from mock task
            ctx = get_required_tenant()
            cid10 = task_variables.get_variable("cid10_codes", task_variables.get_variable("validatedCid10", []))
            tuss = task_variables.get_variable("tuss_codes", task_variables.get_variable("validatedTuss", []))
            enc_cls = task_variables.get_variable("encounterClass", task_variables.get_variable("encounter_class", ""))
            enc_id = task_variables.get_variable("encounterId", task_variables.get_variable("encounter_id", ""))
            payer_id = task_variables.get_variable("payer_id", task_variables.get_variable("payerId", ""))
        else:
            # V2 pattern: task_variables is dict
            ctx = get_required_tenant()
            cid10 = task_variables.get("validatedCid10", task_variables.get("cid10_codes", []))
            tuss = task_variables.get("validatedTuss", task_variables.get("tuss_codes", []))
            enc_cls = task_variables.get("encounterClass", task_variables.get("encounter_class", ""))
            enc_id = task_variables.get("encounterId", task_variables.get("encounter_id", ""))

        if not cid10 or not tuss:
            raise CodingException(_("Entrada inválida para aplicação de regras de codificação: códigos CID-10 e TUSS são obrigatórios"), bpmn_error_code="CODING_ERROR")

        self._logger.info("coding_rules_v2_started", encounter_id=enc_id, encounter_class=enc_cls, tuss_count=len(tuss), cid10_count=len(cid10), tenant_id=ctx.tenant_id)

        violations, modifiers = [], []
        checks = [
            ("coding_rules/quantity_limits", {"tuss_codes": tuss, "encounter_class": enc_cls}),
            ("coding_rules/bundling_validation", {"tuss_codes": tuss}),
            ("coding_rules/specialty_restrictions", {"tuss_codes": tuss, "encounter_class": enc_cls}),
        ]
        for table, inputs in checks:
            violations.extend(self._extract_violations(self._evaluate_dmn(table, inputs), "PROSSEGUIR"))

        mod_res = self._evaluate_dmn("coding_rules/modifier_requirements", {"tuss_codes": tuss})
        modifiers = self._extract_modifiers(mod_res)

        has_errors = any(v.get("severity") == "ERROR" for v in violations)
        output = ApplyCodingRulesOutputV2(rulesPassed=not has_errors, ruleViolations=violations, modifiersRequired=modifiers)

        if has_errors:
            err_cnt = sum(1 for v in violations if v.get("severity") == "ERROR")
            self._logger.error("coding_rule_violations", encounter_id=enc_id, violation_count=len(violations), error_count=err_cnt, tenant_id=ctx.tenant_id)

            # V1 test compatibility: call task.bpmn_error if it's a mock task
            if hasattr(task_variables, 'bpmn_error'):
                await task_variables.bpmn_error("CODING_RULE_VIOLATION", _("Violação de regras de codificação: {count} erro(s) encontrado(s)").format(count=err_cnt))
            else:
                raise BpmnErrorException(error_code="CODING_RULE_VIOLATION", message=_("Violação de regras de codificação: {count} erro(s) encontrado(s)").format(count=err_cnt), details=output.to_variables())

        self._logger.info("coding_rules_v2_passed", encounter_id=enc_id, violation_count=len(violations), modifier_count=len(modifiers), tenant_id=ctx.tenant_id)

        # V1 test compatibility: call task.complete if it's a mock task
        if hasattr(task_variables, 'complete'):
            await task_variables.complete(output.to_variables())

        return output.to_variables()

    def _evaluate_dmn(self, table_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.dmn_service.evaluate(tenant_id=get_required_tenant().tenant_id, category='coding_audit', table_name=table_name, inputs=inputs)
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback (ORPHAN)", table=table_name, error=str(e))
            return {}

    def _extract_violations(self, dmn_result: dict[str, Any], success_value: str) -> list[dict[str, Any]]:
        """Extract violations from DMN result. Supports 3-output and 5-output schemas."""
        res = dmn_result.get("resultado", "")
        dec = dmn_result.get("Decisao", "")
        if res and res != success_value:
            return [{"rule_id": dmn_result.get("rule_id", "UNKNOWN"), "message": dmn_result.get("acao", "Rule violation detected"), "severity": "ERROR" if res == "BLOQUEAR" else "WARNING"}]
        if dec in ("Bloquear", "Alertar", "Revisar"):
            return [{"rule_id": dmn_result.get("rule_id", "LEGACY"), "message": dmn_result.get("Justificativa", dec), "severity": "ERROR" if dec == "Bloquear" else "WARNING"}]
        return []

    def _extract_modifiers(self, dmn_result: dict[str, Any]) -> list[str]:
        acao = dmn_result.get("acao", "")
        return [acao] if "modificador" in acao.lower() else []

def register_worker() -> ApplyCodingRulesWorkerV2:
    return ApplyCodingRulesWorkerV2()
