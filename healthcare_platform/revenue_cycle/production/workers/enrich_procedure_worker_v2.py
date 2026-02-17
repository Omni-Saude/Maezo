"""Enrich procedures with clinical context (Thin Delegation).

TOPIC: production.enrich_procedure

Delegates enrichment assembly to ProcedureEnrichmentService.
Worker handles: input validation, DMN evaluation, delegation.
"""

from __future__ import annotations
from typing import Optional
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.revenue_cycle.production.services.procedure_enrichment_service import ProcedureEnrichmentService


class EnrichProcedureWorker(BaseExternalTaskWorker):
    """Enriches procedures with clinical data. Thin worker - delegates to ProcedureEnrichmentService."""

    TOPIC = "production.enrich_procedure"
    DMN_DECISION_KEY = "diagnosis_requirement_adjudication"
    DMN_CATEGORY = "pricing"

    def __init__(self, fhir_client: Optional[FHIRClientProtocol] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.fhir_client = fhir_client
        self.service = ProcedureEnrichmentService(fhir_client=fhir_client)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            procedures = variables.get("captured_procedures", [])
            encounter_ref = variables.get("encounter_reference", "")
            diagnosis_codes = variables.get("diagnosis_codes", [])
            performers = variables.get("performer_references", [])

            if not procedures:
                return TaskResult.bpmn_error(error_code="CODING_ERROR", error_message="No procedures to enrich")

            self.logger.info(f"Enriching {len(procedures)} procedures", extra={"tenant_id": context.tenant_id})

            warnings = []
            for proc in procedures:
                code = proc.get("code", "")
                dmn_result = self.evaluate_dmn(context=context, decision_key=self.DMN_DECISION_KEY,
                    variables={"procedureCode": code, "hasDiagnosis": bool(diagnosis_codes),
                               "diagnosisCount": len(diagnosis_codes)}, category=self.DMN_CATEGORY)
                resultado, acao = dmn_result.get("resultado", "PROSSEGUIR"), dmn_result.get("acao", "")

                if resultado == "BLOQUEAR":
                    return TaskResult.bpmn_error(error_code="MISSING_DIAGNOSIS",
                        error_message=acao or f"Diagnosis required for {code}", variables={"blockedCode": code})
                if resultado == "REVISAR":
                    warnings.append(f"Review diagnosis for {code}: {acao}")

            result = self.service.enrich(procedures, diagnosis_codes, performers, encounter_ref)
            result["diagnosis_codes"] = diagnosis_codes
            result["enrichment_warnings"] = warnings
            return TaskResult.success(result)
        except Exception as e:
            self.logger.error(f"Procedure enrichment failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="CODING_ERROR", error_message=str(e))
