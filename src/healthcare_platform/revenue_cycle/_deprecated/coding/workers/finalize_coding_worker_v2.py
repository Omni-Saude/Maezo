"""Finalize and lock coding on an encounter (thin worker).

CIB7 External Task Topic: coding.finalize_coding
BPMN Error Codes: CODING_NOT_APPROVED, FRAUD_BLOCK, CODING_ERROR
"""
from __future__ import annotations

import re
from typing import Any

from healthcare_platform.shared.domain.exceptions import BpmnErrorException
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.revenue_cycle.services.finalize_coding_service import (
    FinalizeCodingService,
)


class FinalizeCodingWorkerV2(BaseExternalTaskWorker):
    """Thin DMN-federated worker for coding finalization.

    Delegates all business logic to FinalizeCodingService.
    """

    TOPIC = "coding.finalize_coding"

    def __init__(
        self,
        dmn_service: FederatedDMNService | None = None,
        encounter_service: Any = None,
        **kwargs: Any
    ) -> None:
        super().__init__(dmn_service=dmn_service)
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.service = FinalizeCodingService(dmn_service=dmn_service)
        self.encounter_service = encounter_service

    async def execute(self, task_or_variables: Any) -> dict[str, Any]:
        """Execute worker with dict or mock_task (v1 compatibility)."""
        # V1 compatibility: handle mock_task objects
        if hasattr(task_or_variables, 'get_variable'):
            variables = self._extract_variables_from_mock_task(task_or_variables)
            try:
                result = await self.service.finalize(
                    variables,
                    get_required_tenant().tenant_id,
                    self.encounter_service,
                )
                await task_or_variables.complete(result)
                return result
            except BpmnErrorException as e:
                await task_or_variables.bpmn_error(e.error_code, str(e))
                raise
        else:
            # V2 pattern: dict input
            return await self.service.finalize(
                task_or_variables,
                get_required_tenant().tenant_id,
                self.encounter_service,
            )

    def _extract_variables_from_mock_task(self, mock_task: Any) -> dict[str, Any]:
        """Extract variables from v1 mock_task object."""
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

        # Code lists
        for key_pair in [('cid10_codes', 'validatedCid10'), ('tuss_codes', 'validatedTuss')]:
            if (val := get_val(key_pair[0], key_pair[1])) is not None:
                variables[key_pair[1]] = val

        # Other fields
        for field in ['codedBy', 'auditRecommendation', 'auditScore',
                      'complexityScore', 'complexityLevel', 'fraudRecommendation']:
            snake = re.sub(r'([a-z])([A-Z])', r'\1_\2', field).lower()
            if (val := get_val(snake, field)) is not None:
                variables[field] = val

        # Handle audit_status to auditRecommendation mapping
        if 'auditRecommendation' not in variables:
            audit_status = get_val('audit_status', 'auditStatus')
            variables['auditRecommendation'] = 'aprovar' if audit_status == 'approved' else 'revisar'

        # Handle fraud_risk_level to fraudRecommendation mapping
        if 'fraudRecommendation' not in variables:
            fraud_level = get_val('fraud_risk_level', 'fraudRiskLevel')
            variables['fraudRecommendation'] = 'clear' if fraud_level == 'low' else 'flag'

        return variables

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


def register_worker(dmn_service: FederatedDMNService | None = None) -> FinalizeCodingWorkerV2:
    """Create and return a configured FinalizeCodingWorkerV2 instance."""
    return FinalizeCodingWorkerV2(dmn_service=dmn_service)
