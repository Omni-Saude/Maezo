"""Base class for v2 coding workers with v1 compatibility."""
from __future__ import annotations
from typing import Any
from healthcare_platform.shared.domain.exceptions import BpmnErrorException


class BaseV2Worker:
    """Base class providing v1 mock_task compatibility for v2 workers.

    Archetype: COMPLIANCE_VALIDATION
    """

    async def execute(self, task_variables: dict[str, Any] | Any) -> dict[str, Any]:
        """Execute worker with dict or mock_task (v1 compatibility)."""
        # V1 compatibility: handle mock_task objects
        if hasattr(task_variables, 'get_variable'):
            variables = self._extract_variables_from_mock_task(task_variables)
            try:
                result = await self._execute_impl(variables)
                await task_variables.complete(result)
                return result
            except BpmnErrorException as e:
                await task_variables.bpmn_error(e.error_code, str(e))
                raise
        else:
            # V2 pattern: dict input
            return await self._execute_impl(task_variables)

    def _extract_variables_from_mock_task(self, mock_task: Any) -> dict[str, Any]:
        """Extract variables from v1 mock_task object.

        Subclasses should override this to map their specific variables.
        This base implementation provides common mappings.
        """
        variables = {}

        # Common field mappings (camelCase and snake_case)
        common_fields = [
            ("encounterId", "encounter_id"),
            ("tenantId", "tenant_id"),
            ("patientId", "patient_id"),
            ("validatedCid10", "cid10_codes"),
            ("validatedTuss", "tuss_codes"),
            ("cid10Codes", "cid10_codes"),
            ("tussCodes", "tuss_codes"),
            ("suggestedCid10Codes", "suggested_cid10_codes"),
            ("suggestedTussCodes", "suggested_tuss_codes"),
            ("formatValidTuss", "format_valid_tuss"),
            ("clinicalNotes", "clinical_notes"),
            ("proceduresText", "procedures_text"),
            ("rulesApplied", "rules_applied"),
            ("codedBy", "coded_by"),
            ("auditThreshold", "audit_threshold"),
            ("auditStatus", "audit_status"),
            ("fraudRiskLevel", "fraud_risk_level"),
            ("patientAge", "patient_age"),
            ("comorbidities", "comorbidities"),
            ("encounterClass", "encounter_class"),
            ("codingRulesResult", "coding_rules_result"),
        ]

        for camel_case, snake_case in common_fields:
            # Try camelCase first, then snake_case
            value = mock_task.get_variable(camel_case)
            if value is None:
                value = mock_task.get_variable(snake_case)
            if value is not None:
                variables[camel_case] = value

        # Extract rules from coding_rules_result if it's a dict
        coding_result = variables.get("codingRulesResult")
        if isinstance(coding_result, dict) and "rulesApplied" not in variables:
            variables["rulesApplied"] = coding_result.get("rules", [])

        return variables

    async def _execute_impl(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Core execution logic - must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _execute_impl")
