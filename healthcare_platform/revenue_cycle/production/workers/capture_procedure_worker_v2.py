"""Capture clinical procedures from ERP systems (Thin Delegation).

TOPIC: production.capture_procedure

Delegates ERP capture to ProcedureCaptureService.
Worker handles: input validation, DMN routing, delegation.
"""

from __future__ import annotations
from typing import Optional
from healthcare_platform.shared.integrations.tasy_client import TasyClientProtocol
from healthcare_platform.shared.integrations.mv_soul_client import MvSoulClientProtocol
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.revenue_cycle.production.services.procedure_capture_service import ProcedureCaptureService


class CaptureProcedureWorker(BaseExternalTaskWorker):
    """Captures procedures from ERP. Thin worker - delegates to ProcedureCaptureService."""

    TOPIC = "production.capture_procedure"
    DMN_DECISION_KEY = "erp_system_routing"
    DMN_CATEGORY = "pricing"

    def __init__(self, tasy_client: Optional[TasyClientProtocol] = None,
                 mv_soul_client: Optional[MvSoulClientProtocol] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tasy_client = tasy_client
        self.mv_soul_client = mv_soul_client
        self.service = ProcedureCaptureService(tasy_client=tasy_client, mv_soul_client=mv_soul_client)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            encounter_ref = variables.get("encounter_reference", "")

            if not encounter_ref:
                return TaskResult.bpmn_error(error_code="CODING_ERROR", error_message="Missing encounter_reference")

            encounter_id = encounter_ref.rsplit("/", 1)[-1]

            dmn_result = self.evaluate_dmn(context=context, decision_key=self.DMN_DECISION_KEY,
                variables={"tenantId": context.tenant_id}, category=self.DMN_CATEGORY)
            destino = dmn_result.get("destino", "tasy")
            prioridade = dmn_result.get("prioridade", "NORMAL")

            self.logger.info(f"Capturing procedures: ERP={destino}, encounter={encounter_id}",
                extra={"tenant_id": context.tenant_id, "priority": prioridade})

            captured = self.service.capture(destino, encounter_id)

            if not captured:
                return TaskResult.bpmn_error(error_code="CODING_ERROR",
                    error_message=f"No procedures found for encounter {encounter_id}")

            return TaskResult.success({"captured_procedures": captured, "erp_system": destino, "procedure_count": len(captured)})
        except Exception as e:
            self.logger.error(f"Procedure capture failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="EXTERNAL_SERVICE_ERROR", error_message=str(e))
