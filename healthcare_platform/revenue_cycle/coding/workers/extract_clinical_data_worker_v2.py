"""Extract clinical data from FHIR encounter for coding - V2 thin worker.
CIB7 External Task Topic: coding.extract_clinical_data
BPMN Error Codes: ENCOUNTER_NOT_FOUND, FHIR_SERVICE_ERROR
Companion DMN tables: data_extraction/encounter_class_mapping, primary_diagnosis_priority

Delegates FHIR fetching to ClinicalDataExtractionService.
"""
from __future__ import annotations
from typing import Any
from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.revenue_cycle.coding.services.clinical_data_extraction_service import ClinicalDataExtractionService


class ExtractClinicalDataWorkerV2(BaseExternalTaskWorker):
    """V2 thin worker: delegates extraction to ClinicalDataExtractionService + DMN."""
    TOPIC = "revenue_cycle.coding.extract_clinical_data"

    def __init__(self, fhir_client: FHIRClientProtocol | None = None, fhir_service: FHIRClientProtocol | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        client = fhir_client or fhir_service
        if client is None:
            raise ValueError("fhir_client or fhir_service is required")
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.service = ClinicalDataExtractionService(fhir_client=client)

    async def execute(self, task_or_variables: Any) -> dict[str, Any]:
        """Execute worker with dict or mock_task (v1 compatibility)."""
        if hasattr(task_or_variables, 'get_variable'):
            variables = self.service.extract_variables_from_mock_task(task_or_variables)
            try:
                result = await self._execute_impl(variables)
                await task_or_variables.complete(result)
                return result
            except BpmnErrorException as e:
                await task_or_variables.bpmn_error(e.error_code, str(e))
                raise
        else:
            return await self._execute_impl(task_or_variables)

    async def _execute_impl(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Core execution: validate input, fetch via service, evaluate DMN."""
        ctx = get_required_tenant()
        enc_id = task_variables.get("encounter_id", "")
        if not enc_id:
            raise CodingException(_("Entrada invalida: encounter_id e obrigatorio"), bpmn_error_code="CODING_ERROR")

        self._logger.info("extract_v2_started", encounter_id=enc_id, tenant_id=ctx.tenant_id)
        result = await self.service.extract_with_dmn(enc_id, ctx.tenant_id, self.dmn_service)
        self._logger.info("extract_v2_completed", encounter_id=enc_id, tenant_id=ctx.tenant_id)
        return result

    async def process_task(self, job: Any = None, variables: dict[str, Any] | None = None) -> Any:
        """V1 backward-compatible entry point for tests."""
        return await self.service.process_task_compat(self.execute, variables or {})


def register_worker(fhir_client: FHIRClientProtocol) -> ExtractClinicalDataWorkerV2:
    return ExtractClinicalDataWorkerV2(fhir_client=fhir_client)
