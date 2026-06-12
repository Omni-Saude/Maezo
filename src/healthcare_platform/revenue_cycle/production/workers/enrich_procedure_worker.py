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

    TOPIC = "revenue_cycle.enrich_procedure"
    DMN_DECISION_KEY = "diagnosis_requirement_adjudication"
    DMN_CATEGORY = "pricing"

    def __init__(self, fhir_client: Optional[FHIRClientProtocol] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.fhir_client = fhir_client
        self.service = ProcedureEnrichmentService(fhir_client=fhir_client)

    def execute(self, context: TaskContext) -> TaskResult:
        import json as _json

        variables = context.variables
        procedures = variables.get("captured_procedures", [])
        # Handle JSON string from previous task
        if isinstance(procedures, str):
            try:
                procedures = _json.loads(procedures)
            except (ValueError, TypeError):
                procedures = [{"code": variables.get("procedureCode", ""), "quantity": 1}]
        if not procedures:
            procedures = [{"code": variables.get("procedureCode", ""), "quantity": 1}]

        encounter_ref = variables.get("encounter_reference", "") or variables.get("encounterId", "")
        diagnosis_codes = variables.get("diagnosis_codes", [])
        performers = variables.get("performer_references", [])

        self.logger.info(f"Enriching {len(procedures)} procedures", extra={"tenant_id": context.tenant_id})

        warnings = []
        for proc in procedures:
            code = proc.get("code", "") if isinstance(proc, dict) else str(proc)
            dmn_result = self.evaluate_dmn(context=context, decision_key=self.DMN_DECISION_KEY,
                variables={"procedureCode": code, "hasDiagnosis": bool(diagnosis_codes),
                           "diagnosisCount": len(diagnosis_codes)}, category=self.DMN_CATEGORY)
            resultado = dmn_result.get("resultado", "PROSSEGUIR")
            if resultado == "REVISAR":
                warnings.append(f"Review diagnosis for {code}: {dmn_result.get('acao', '')}")

        # Try real enrichment; fallback to passthrough
        try:
            result = self.service.enrich(procedures, diagnosis_codes, performers, encounter_ref)
            enriched = result.get("enriched_procedures", procedures)
        except Exception as e:
            self.logger.warning(f"Enrichment service failed, using passthrough: {e}")
            enriched = procedures

        procedure_codes = [p.get("code", "") if isinstance(p, dict) else str(p) for p in procedures]
        return TaskResult.success({
            "completeData": enriched,
            "icdCodes": diagnosis_codes if diagnosis_codes else ["Z00.0"],
            "tussCodes": procedure_codes,
            "enrichment_warnings": warnings,
        })
