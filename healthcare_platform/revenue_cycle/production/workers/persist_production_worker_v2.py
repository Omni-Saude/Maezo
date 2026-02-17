"""Persist production data to FHIR store (Thin Delegation).

TOPIC: production.persist_production

Delegates FHIR Claim building to ProductionPersistenceService.
Worker handles: input validation, DMN evaluation, delegation.
"""

from __future__ import annotations
from typing import Optional
from uuid import uuid4
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.revenue_cycle.production.services.production_persistence_service import ProductionPersistenceService


class PersistProductionWorker(BaseExternalTaskWorker):
    """Persists production data. Thin worker - delegates to ProductionPersistenceService."""

    TOPIC = "revenue_cycle.production.record_production"
    DMN_DECISION_KEY = "persistence_validation_adjudication"
    DMN_CATEGORY = "pricing"

    def __init__(self, fhir_client: Optional[FHIRClientProtocol] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.fhir_client = fhir_client
        self.service = ProductionPersistenceService(fhir_client=fhir_client)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            procedures = variables.get("compatible_procedures", [])
            encounter_ref = variables.get("encounter_reference", "")
            patient_ref = variables.get("patient_reference", "")
            total_amount = variables.get("total_amount", "0.00")
            production_id = str(uuid4())

            dmn_result = self.evaluate_dmn(context=context, decision_key=self.DMN_DECISION_KEY,
                variables={"procedureCount": len(procedures), "totalAmount": total_amount,
                           "hasEncounterRef": bool(encounter_ref), "hasPatientRef": bool(patient_ref)},
                category=self.DMN_CATEGORY)
            resultado = dmn_result.get("resultado", "PROSSEGUIR")

            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(error_code="BILLING_ERROR",
                    error_message=dmn_result.get("acao", "Persistence blocked"),
                    variables={"production_id": production_id})

            self.logger.info(f"Persisting production: {len(procedures)} procedures, total={total_amount}",
                extra={"tenant_id": context.tenant_id, "production_id": production_id})

            result = self.service.persist(procedures, encounter_ref, patient_ref, total_amount, production_id)

            if resultado == "REVISAR":
                result["requiresReview"] = True
                result["charge_item_references"] = []

            return TaskResult.success(result)
        except Exception as e:
            self.logger.error(f"Production persistence failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="EXTERNAL_SERVICE_ERROR", error_message=str(e))
